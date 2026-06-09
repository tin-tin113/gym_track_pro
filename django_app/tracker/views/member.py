from __future__ import annotations

import csv
import io
from datetime import timedelta
from types import SimpleNamespace
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.urls import reverse

import json
from tracker.models import Member, Trainer, TrainerAssignment, Attendance, FitnessMetric, Workout, GuideAssignment, DietAssignment, MealLog, MealPlan, WorkoutGuide, WorkoutTip, Subscription, WorkoutSet
from tracker.forms import MemberForm, WorkoutForm, MemberProfileForm
from .base import _require_roles, _require_member_access, _PaginationAdapter


def member_list_members(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	is_trainer = role == 'trainer'

	search = (request.GET.get('search') or '').strip()
	status = (request.GET.get('status') or 'all').strip()
	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = Member.objects.select_related('user').all().order_by('user__full_name', 'id')
	if is_trainer:
		qs = qs.filter(assigned_trainer=request.user)
	if search:
		qs = qs.filter(Q(user__full_name__icontains=search) | Q(user__email__icontains=search))

	today = timezone.localdate()
	if status == 'pending':
		qs = qs.filter(is_approved=False)
	elif status == 'active':
		qs = qs.filter(is_approved=True, is_active=True, membership_expiry_date__gte=today)
	elif status == 'expiring_soon':
		qs = qs.filter(
			is_approved=True,
			is_active=True,
			membership_expiry_date__gte=today,
			membership_expiry_date__lte=today + timedelta(days=7),
		)
	elif status == 'expired':
		qs = qs.filter(Q(is_approved=True) & (Q(is_active=False) | Q(membership_expiry_date__lt=today)))
	elif status == 'pending_renewal':
		qs = qs.filter(pending_renewal_plan__isnull=False).exclude(pending_renewal_plan='')
	else:
		status = 'all'

	if (request.GET.get('format') or '').lower() == 'csv':
		buf = io.StringIO()
		writer = csv.writer(buf)
		writer.writerow(['Full Name', 'Email', 'Phone Number', 'Member Tier', 'Membership Type', 'Start Date', 'Expiry Date', 'Status'])
		for member in qs:
			writer.writerow([
				member.user.full_name,
				member.user.email,
				member.phone_number,
				member.get_member_tier_display(),
				member.get_membership_type_display(),
				member.membership_start_date.isoformat() if member.membership_start_date else '',
				member.membership_expiry_date.isoformat() if member.membership_expiry_date else '',
				'Active' if member.is_membership_active() else 'Expired'
			])
		resp = HttpResponse(buf.getvalue(), content_type='text/csv')
		resp['Content-Disposition'] = 'attachment; filename="members_export.csv"'
		return resp

	paginator = Paginator(qs, 10)
	page_obj = paginator.get_page(page_number)
	pagination = _PaginationAdapter(paginator, page_obj)

	return render(
		request,
		"member/list.html",
		{
			"members": list(page_obj.object_list),
			"search": search,
			"status": status,
			"pagination": pagination,
		},
	)


def member_create_member(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		email = (request.POST.get('email') or '').strip().lower()
		membership_start_str = (request.POST.get('membership_start_date') or '').strip()
		membership_expiry_str = (request.POST.get('membership_expiry_date') or '').strip()

		if not full_name or not email or not membership_start_str or not membership_expiry_str:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.create_member')

		User = get_user_model()
		if User.objects.filter(email__iexact=email).exists():
			messages.error(request, 'A user with that email already exists.')
			return redirect('member.create_member')

		form = MemberForm(request.POST)
		if not form.is_valid():
			messages.error(request, 'Invalid date format or fields.')
			return redirect('member.create_member')

		base_username = (email.split('@', 1)[0] or 'member')[:150]
		username = base_username
		suffix = 1
		while User.objects.filter(username__iexact=username).exists():
			suffix += 1
			username = f"{base_username}{suffix}"[:150]

		default_password = 'P@ssw0rd'

		with transaction.atomic():
			user = User.objects.create_user(username=username, email=email, password=default_password)
			user.full_name = full_name
			user.role = User.Role.MEMBER
			user.is_active = True
			user.save(update_fields=['full_name', 'role', 'is_active'])

			member = form.save(commit=False)
			member.user = user
			member.is_approved = True
			member.approval_date = timezone.now()
			member.save()

		messages.success(request, f"Member created. Default password: {default_password}")
		return redirect('member.view_member', member_id=member.id)

	return render(request, "member/edit.html", {"member": None, "now": timezone.now()})


def member_detail(request: HttpRequest, member_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	is_trainer = role == 'trainer'

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	if is_trainer and member.assigned_trainer_id != request.user.id:
		messages.error(request, 'Access denied.')
		return redirect('member.list_members')

	trainer_assignment = (
		TrainerAssignment.objects.select_related('trainer')
		.filter(member=member, is_active=True)
		.order_by('-start_date', '-id')
		.first()
	)
	# Only show active trainers for new assignments
	trainers = Trainer.objects.select_related('user').filter(user__is_active=True).order_by('user__full_name', 'id')

	thirty_days_ago = timezone.now() - timedelta(days=30)
	attendance_qs = Attendance.objects.filter(member=member, check_in_time__gte=thirty_days_ago)
	agg = attendance_qs.aggregate(
		total_visits=Count('id'),
		avg_duration=Avg('duration_minutes'),
		total_duration=Sum('duration_minutes'),
	)
	attendance_stats = {
		"total_visits": agg.get('total_visits') or 0,
		"avg_duration": int(agg.get('avg_duration') or 0),
		"total_duration": int(agg.get('total_duration') or 0),
	}

	attendance_records = member.attendance_records.all().order_by('-check_in_time')

	latest_metrics = FitnessMetric.objects.filter(member=member).order_by('-metric_date', '-created_at', '-id').first()
	if latest_metrics is not None and latest_metrics.bmi is None and latest_metrics.weight and latest_metrics.height:
		height_m = latest_metrics.height / 100.0
		if height_m > 0:
			latest_metrics.bmi = round(latest_metrics.weight / (height_m * height_m), 2)
	if latest_metrics is not None and latest_metrics.bmi is None:
		latest_metrics = None

	return render(
		request,
		"member/detail.html",
		{
			"member": member,
			"trainer_assignment": trainer_assignment,
			"trainers": trainers,
			"attendance_stats": attendance_stats,
			"latest_metrics": latest_metrics,
			"attendance_records": attendance_records,
		},
	)


def member_edit(request: HttpRequest, member_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	is_trainer = role == 'trainer'

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	if is_trainer and member.assigned_trainer_id != request.user.id:
		messages.error(request, 'Access denied.')
		return redirect('member.list_members')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		membership_start_str = (request.POST.get('membership_start_date') or '').strip()
		membership_expiry_str = (request.POST.get('membership_expiry_date') or '').strip()

		if not full_name or not membership_start_str or not membership_expiry_str:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.edit_member', member_id=member.id)

		form = MemberForm(request.POST, instance=member)
		if form.is_valid():
			member.user.full_name = full_name
			member.user.save(update_fields=['full_name'])
			form.save()
			messages.success(request, 'Member updated.')
			return redirect('member.view_member', member_id=member.id)
		else:
			messages.error(request, 'Invalid input parameters.')
			return redirect('member.edit_member', member_id=member.id)

	return render(request, "member/edit.html", {"member": member, "now": timezone.now()})


@login_required
def member_assign_trainer(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	member = Member.objects.filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	trainer_id = (request.POST.get('trainer_id') or '').strip()
	User = get_user_model()

	with transaction.atomic():
		TrainerAssignment.objects.filter(member=member, is_active=True).update(is_active=False)
		if trainer_id:
			trainer_user = User.objects.filter(id=trainer_id, role=User.Role.TRAINER).first()
			if trainer_user is None:
				messages.error(request, 'Invalid trainer selected.')
				return redirect('member.view_member', member_id=member.id)
			member.assigned_trainer = trainer_user
			member.save(update_fields=['assigned_trainer'])
			today = timezone.localdate()
			TrainerAssignment.objects.create(
				trainer=trainer_user,
				member=member,
				assignment_date=today,
				start_date=today,
				assignment_type=TrainerAssignment.AssignmentType.PRIMARY,
				is_active=True,
			)
			messages.success(request, 'Trainer assigned.')
		else:
			member.assigned_trainer = None
			member.save(update_fields=['assigned_trainer'])
			messages.info(request, 'Trainer unassigned.')

	return redirect('member.view_member', member_id=member.id)


def member_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')

	member = getattr(request.user, 'member_profile', None)
	if getattr(request.user, 'role', None) != 'member':
		messages.error(request, 'Access denied.')
		return redirect('home')
	if member is None:
		messages.error(request, 'Member profile not found.')
		return redirect('home')
	if not member.is_approved:
		return redirect('auth.pending_status')

	today = timezone.localdate()
	start = timezone.make_aware(timezone.datetime.combine(today - timedelta(days=30), timezone.datetime.min.time()))

	attendance_count = Attendance.objects.filter(member=member, check_in_time__gte=start).count()
	recent_workouts = list(
		Workout.objects.filter(member=member)
		.order_by('-workout_date', '-id')[:5]
	)


	# Fetch timezone-aware attendance history over the last 14 days
	grid_start_datetime = timezone.make_aware(timezone.datetime.combine(today - timedelta(days=13), timezone.datetime.min.time()))
	check_in_datetimes = Attendance.objects.filter(
		member=member,
		check_in_time__gte=grid_start_datetime
	).values_list('check_in_time', flat=True)
	check_in_dates = {timezone.localdate(dt) for dt in check_in_datetimes}

	attendance_grid = []
	for i in range(13, -1, -1):
		date = today - timedelta(days=i)
		attendance_grid.append({
			"date": date,
			"day_name": date.strftime('%a'),
			"day_num": date.day,
			"checked_in": date in check_in_dates
		})

	# Calculate membership subscription countdown metrics
	days_total = 30
	days_left = 0
	progress_percent = 0
	is_expiring_soon = False

	if member.membership_start_date and member.membership_expiry_date:
		days_total = (member.membership_expiry_date - member.membership_start_date).days
		days_left = (member.membership_expiry_date - today).days
		if days_total > 0:
			progress_percent = int(max(0, min(100, (days_left / days_total) * 100)))
		else:
			progress_percent = 0
		is_expiring_soon = 0 <= days_left <= 7

	is_locked_out = False
	cooldown_end_date = None
	if member.consecutive_rejections >= 3 and member.last_rejection_date:
		cooldown_end = member.last_rejection_date + timedelta(days=30)
		if cooldown_end > timezone.now():
			is_locked_out = True
			cooldown_end_date = cooldown_end

	show_rejection_alert = (
		member.consecutive_rejections > 0 and
		member.last_rejection_date is not None and
		not member.pending_renewal_plan and
		not is_locked_out
	)

	return render(
		request,
		"member_dashboard/dashboard.html",
		{
			"attendance_count": attendance_count,
			"recent_workouts": recent_workouts,
			"attendance_grid": attendance_grid,
			"days_total": days_total,
			"days_left": max(0, days_left),
			"progress_percent": progress_percent,
			"is_expiring_soon": is_expiring_soon,
			"is_locked_out": is_locked_out,
			"cooldown_end_date": cooldown_end_date,
			"show_rejection_alert": show_rejection_alert,
			"last_rejection_date": member.last_rejection_date,
		},
	)


@login_required
def member_renew(request: HttpRequest) -> HttpResponse:
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method == 'POST':
		if member.consecutive_rejections >= 3:
			if member.last_rejection_date:
				one_month_ago = timezone.now() - timedelta(days=30)
				if member.last_rejection_date > one_month_ago:
					messages.error(
						request,
						'Your subscription renewal has been rejected 3 consecutive times. You must wait 1 month from the last rejection before applying again.'
					)
					return redirect('member.member_dashboard')
				else:
					member.consecutive_rejections = 0

		if member.pending_renewal_plan:
			messages.error(request, 'You already have a pending subscription renewal request.')
			return redirect('member.member_dashboard')

		plan_choice = (request.POST.get('plan') or '').strip().lower()
		
		valid_plans = {Member.MembershipType.MONTHLY, Member.MembershipType.QUARTERLY, Member.MembershipType.ANNUAL}
		if plan_choice not in valid_plans:
			messages.error(request, 'Invalid subscription plan selected.')
			return redirect('member.member_dashboard')

		member.pending_renewal_plan = plan_choice
		member.save(update_fields=['pending_renewal_plan', 'consecutive_rejections'])

		messages.success(
			request, 
			f'Renewal request submitted! Please pay for your {plan_choice.title()} subscription at the counter during your next visit to finalize activation.'
		)
	return redirect('member.member_dashboard')


@login_required
def member_approve_renewal(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	member = Member.objects.filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	# If trainer, check if this member is assigned to them
	if getattr(request.user, 'role', None) == 'trainer' and member.assigned_trainer_id != request.user.id:
		messages.error(request, 'Access denied.')
		return redirect('member.list_members')

	if request.method == 'POST':
		plan = member.pending_renewal_plan
		if not plan:
			messages.error(request, 'No pending renewal request found for this member.')
			return redirect('member.view_member', member_id=member.id)

		days_to_add = 0
		if plan == Member.MembershipType.MONTHLY:
			days_to_add = 30
		elif plan == Member.MembershipType.QUARTERLY:
			days_to_add = 90
		elif plan == Member.MembershipType.ANNUAL:
			days_to_add = 365

		today = timezone.localdate()
		same_active_sub = Subscription.objects.filter(
			member=member,
			subscription_type=plan,
			is_active=True,
			expiry_date__gte=today
		).order_by('-expiry_date').first()

		if same_active_sub:
			start_ref = same_active_sub.expiry_date
		else:
			start_ref = today

		expiry_date = start_ref + timedelta(days=days_to_add)

		Subscription.objects.create(
			member=member,
			subscription_type=plan,
			start_date=start_ref,
			expiry_date=expiry_date,
			is_active=True
		)

		member.update_membership_from_subscriptions()
		member.pending_renewal_plan = None
		member.is_active = True
		member.consecutive_rejections = 0
		member.last_rejection_date = None
		member.save(update_fields=['membership_start_date', 'membership_expiry_date', 'membership_type', 'pending_renewal_plan', 'is_active', 'consecutive_rejections', 'last_rejection_date'])

		messages.success(request, f'Counter payment confirmed! {plan.title()} subscription has been activated (Expires {member.membership_expiry_date}).')
	
	ref = request.META.get('HTTP_REFERER')
	if ref:
		return redirect(ref)
	return redirect('member.view_member', member_id=member.id)


@login_required
def member_reject_renewal(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	member = Member.objects.filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	# If trainer, check if this member is assigned to them
	if getattr(request.user, 'role', None) == 'trainer' and member.assigned_trainer_id != request.user.id:
		messages.error(request, 'Access denied.')
		return redirect('member.list_members')

	if request.method == 'POST':
		plan = member.pending_renewal_plan
		if not plan:
			messages.error(request, 'No pending renewal request found for this member.')
			return redirect('member.view_member', member_id=member.id)

		member.consecutive_rejections = (member.consecutive_rejections or 0) + 1
		member.last_rejection_date = timezone.now()
		member.pending_renewal_plan = None
		member.save(update_fields=['consecutive_rejections', 'last_rejection_date', 'pending_renewal_plan'])

		messages.info(request, f'Subscription renewal request rejected. This member now has {member.consecutive_rejections} consecutive rejection(s).')
	
	ref = request.META.get('HTTP_REFERER')
	if ref:
		return redirect(ref)
	return redirect('member.view_member', member_id=member.id)


def member_profile(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')
	return render(request, "member_dashboard/profile.html", {"member": member})


def member_profile_edit(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		email = (request.POST.get('email') or '').strip().lower()

		if not full_name or not email:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.edit_member_profile')

		User = get_user_model()
		if User.objects.filter(email__iexact=email).exclude(id=request.user.id).exists():
			messages.error(request, 'That email is already in use.')
			return redirect('member.edit_member_profile')

		form = MemberProfileForm(request.POST, instance=member)
		if form.is_valid():
			request.user.full_name = full_name
			request.user.email = email
			request.user.save(update_fields=['full_name', 'email'])
			form.save()
			messages.success(request, 'Profile updated.')
			return redirect('member.member_profile')
		else:
			messages.error(request, 'Invalid date of birth or fields.')
			return redirect('member.edit_member_profile')

	return render(request, "member_dashboard/profile_edit.html", {"member": member})


def member_workouts(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	search_query = (request.GET.get('search') or '').strip()
	category_filter = (request.GET.get('category') or '').strip()
	muscle_group_filter = (request.GET.get('muscle_group') or '').strip()
	date_from = (request.GET.get('date_from') or '').strip()
	date_to = (request.GET.get('date_to') or '').strip()

	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = Workout.objects.select_related('trainer').filter(member=member)

	if search_query:
		qs = qs.filter(exercise_name__icontains=search_query)
	if category_filter:
		qs = qs.filter(exercise_category=category_filter)
	if muscle_group_filter:
		qs = qs.filter(muscle_group=muscle_group_filter)
	if date_from:
		qs = qs.filter(workout_date__gte=date_from)
	if date_to:
		qs = qs.filter(workout_date__lte=date_to)

	qs = qs.order_by('-workout_date', '-id')
	paginator = Paginator(qs, 10)
	page_obj = paginator.get_page(page_number)
	pagination = _PaginationAdapter(paginator, page_obj)

	return render(
		request,
		"member_dashboard/workouts.html",
		{
			"workouts": list(page_obj.object_list),
			"pagination": pagination,
			"search_query": search_query,
			"category_filter": category_filter,
			"muscle_group_filter": muscle_group_filter,
			"date_from": date_from,
			"date_to": date_to,
			"muscle_groups": Workout.MuscleGroup.choices,
		},
	)


def _save_workout_sets(workout, sets_data_str):
	if workout.exercise_category != 'Strength':
		workout.sets_list.all().delete()
		return

	if not sets_data_str:
		return
	try:
		sets_data = json.loads(sets_data_str)
		if not isinstance(sets_data, list):
			return
		
		valid_sets = [s for s in sets_data if isinstance(s, dict) and 'reps' in s and 'weight' in s]
		
		# Always clear existing sets first
		workout.sets_list.all().delete()
		
		if not valid_sets:
			return

		# Update workout summary fields
		workout.sets = len(valid_sets)
		workout.reps = int(max(s.get('reps') or 0 for s in valid_sets))
		workout.weight = float(max(s.get('weight') or 0.0 for s in valid_sets))
		workout.save(update_fields=['sets', 'reps', 'weight'])

		# --- PR Detection ---
		# Compute the member's all-time best weight and 1RM for this exercise
		# from WorkoutSets in other workouts (not the current one being saved).
		from django.db.models import Max
		prior_sets = WorkoutSet.objects.filter(
			workout__member=workout.member,
			workout__exercise_name__iexact=workout.exercise_name,
			is_completed=True,
		).exclude(workout_id=workout.id)

		# Aggregate best weight from prior sets
		prior_best_weight = prior_sets.aggregate(best=Max('weight'))['best'] or 0.0

		# Compute best prior estimated 1RM in Python (weight * (1 + reps/30))
		prior_best_1rm = 0.0
		for ps in prior_sets.values('weight', 'reps'):
			w, r = ps.get('weight') or 0.0, ps.get('reps') or 0
			if r and w:
				est = w * (1 + r / 30.0)
				if est > prior_best_1rm:
					prior_best_1rm = est

		# Track the running best within *this* save session
		session_best_weight = prior_best_weight
		session_best_1rm = prior_best_1rm

		for item in valid_sets:
			weight = float(item.get('weight') or 0.0)
			reps = int(item.get('reps') or 0)
			is_completed = bool(item.get('is_completed') or item.get('done') or False)

			is_pr = False
			if is_completed and weight and reps:
				est_1rm = weight * (1 + reps / 30.0)
				if weight > session_best_weight or est_1rm > session_best_1rm:
					is_pr = True
					# Update running session bests so only the first new-record
					# set is flagged per session (avoid tagging every subsequent set)
					if weight > session_best_weight:
						session_best_weight = weight
					if est_1rm > session_best_1rm:
						session_best_1rm = est_1rm

			WorkoutSet.objects.create(
				workout=workout,
				set_number=int(item.get('set_number') or 1),
				reps=reps,
				weight=weight,
				set_type=item.get('set_type') or 'working',
				is_completed=is_completed,
				is_pr=is_pr,
			)
	except Exception as e:
		print("Error saving workout sets:", e)


def member_workout_form(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	guide_id_str = request.GET.get('guide_id')
	tip_index_str = request.GET.get('tip_index', '0')
	clone_id_str = request.GET.get('clone_id')
	
	guide = None
	guide_assignment = None
	tip_index = 0
	tips = []
	current_tip = None
	clone_workout = None
	sets_json = "[]"
	
	if guide_id_str:
		try:
			guide_id = int(guide_id_str)
			tip_index = int(tip_index_str)
			guide_assignment = GuideAssignment.objects.filter(
				member=member, guide_id=guide_id, is_active=True, is_completed=False
			).first()
			if guide_assignment:
				guide = guide_assignment.guide
				tips = list(guide.tips.order_by('order', 'id'))
				if 0 <= tip_index < len(tips):
					current_tip = tips[tip_index]
		except Exception as e:
			print("Error reading guide assignment:", e)

	if clone_id_str:
		try:
			clone_workout = Workout.objects.filter(id=int(clone_id_str), member=member).first()
			if clone_workout:
				sets_list = list(clone_workout.sets_list.all().order_by('set_number'))
				sets_data = [
					{
						'set_number': s.set_number,
						'weight': s.weight,
						'reps': s.reps,
						'is_completed': False,
						'is_pr': False,
					}
					for s in sets_list
				]
				sets_json = json.dumps(sets_data)
		except Exception as e:
			print("Error reading clone workout:", e)

	if request.method == 'POST':
		workout_date_str = (request.POST.get('workout_date') or '').strip()
		exercise_name = (request.POST.get('exercise_name') or '').strip()
		exercise_category = (request.POST.get('exercise_category') or '').strip()

		if not workout_date_str or not exercise_name or not exercise_category:
			messages.error(request, 'Please fill in all required fields.')
			return redirect(request.get_full_path())

		form = WorkoutForm(request.POST)
		if form.is_valid():
			workout = form.save(commit=False)
			workout.member = member
			if guide:
				workout.guide = guide
				workout.guide_assignment = guide_assignment
			workout.save()
			_save_workout_sets(workout, request.POST.get('sets_data'))
			
			if guide_assignment and tips:
				next_index = tip_index + 1
				if next_index < len(tips):
					messages.success(
						request, 
						f'Exercise logged. Next up: "{tips[next_index].exercise_name}".'
					)
					return redirect(reverse('member.create_workout') + f"?guide_id={guide.id}&tip_index={next_index}")
				else:
					# Complete the guide
					guide_assignment.is_completed = True
					guide_assignment.completion_date = timezone.now()
					guide_assignment.save(update_fields=['is_completed', 'completion_date', 'updated_at'])
					messages.success(
						request, 
						f'Congratulations! You have completed all exercises in the "{guide.name}" routine!'
					)
					return redirect('member.member_programs')
			else:
				messages.success(request, 'Workout logged.')
				return redirect('member.list_workouts')
		else:
			messages.error(request, 'Invalid data fields.')
			return redirect(request.get_full_path())

	past_exercises = list(Workout.objects.filter(member=member).values_list('exercise_name', flat=True).distinct().order_by('exercise_name'))

	prefilled_workout = None
	if current_tip:
		prefilled_workout = {
			'exercise_name': current_tip.exercise_name,
			'exercise_category': current_tip.tip_category,
		}
	elif clone_workout:
		prefilled_workout = {
			'exercise_name': clone_workout.exercise_name,
			'exercise_category': clone_workout.exercise_category,
			'muscle_group': clone_workout.muscle_group,
			'sets': clone_workout.sets,
			'reps': clone_workout.reps,
			'weight': clone_workout.weight,
			'duration_minutes': clone_workout.duration_minutes,
			'distance_km': clone_workout.distance_km,
			'intensity': clone_workout.intensity,
			'notes': clone_workout.notes,
			'workout_date': timezone.localdate().strftime('%Y-%m-%d'),  # Prefills with today's date
		}
	else:
		init_name = request.GET.get('exercise_name', '')
		init_category = request.GET.get('exercise_category', '')
		if init_name or init_category:
			prefilled_workout = {
				'exercise_name': init_name,
				'exercise_category': init_category,
			}

	return render(
		request, 
		"member_dashboard/workout_form.html", 
		{
			"workout": prefilled_workout,
			"past_exercises": past_exercises,
			"muscle_groups": Workout.MuscleGroup.choices,
			"sets_json": sets_json,
			"guide": guide,
			"tip_index": tip_index,
			"total_exercises": len(tips),
			"current_exercise_num": tip_index + 1 if tips else 0,
		}
	)


def member_edit_workout(request: HttpRequest, workout_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	workout = Workout.objects.filter(id=workout_id, member=member).first()
	if workout is None:
		messages.error(request, 'Workout not found.')
		return redirect('member.list_workouts')
	if workout.trainer_id:
		messages.error(request, 'This workout is trainer-assigned and read-only.')
		return redirect('member.list_workouts')

	if request.method == 'POST':
		workout_date_str = (request.POST.get('workout_date') or '').strip()
		exercise_name = (request.POST.get('exercise_name') or '').strip()
		exercise_category = (request.POST.get('exercise_category') or '').strip()

		if not workout_date_str or not exercise_name or not exercise_category:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.edit_workout', workout_id=workout.id)

		form = WorkoutForm(request.POST, instance=workout)
		if form.is_valid():
			workout = form.save()
			_save_workout_sets(workout, request.POST.get('sets_data'))
			messages.success(request, 'Workout updated.')
			return redirect('member.list_workouts')
		else:
			messages.error(request, 'Invalid workout fields.')
			return redirect('member.edit_workout', workout_id=workout.id)

	past_exercises = list(Workout.objects.filter(member=member).values_list('exercise_name', flat=True).distinct().order_by('exercise_name'))

	sets_list = list(workout.sets_list.all().order_by('set_number'))
	sets_data = [
		{
			'set_number': s.set_number,
			'weight': s.weight,
			'reps': s.reps,
			'is_completed': s.is_completed,
			'is_pr': s.is_pr,
			'trainer_notes': s.trainer_notes,
		}
		for s in sets_list
	]
	sets_json = json.dumps(sets_data)

	return render(
		request, 
		"member_dashboard/workout_form.html", 
		{
			"workout": workout,
			"past_exercises": past_exercises,
			"muscle_groups": Workout.MuscleGroup.choices,
			"sets_json": sets_json,
		}
	)


def member_delete_workout(request: HttpRequest, workout_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	workout = Workout.objects.filter(id=workout_id, member=member).first()
	if workout is None:
		messages.error(request, 'Workout not found.')
		return redirect('member.list_workouts')
	if workout.trainer_id:
		messages.error(request, 'This workout is trainer-assigned and cannot be deleted.')
		return redirect('member.list_workouts')
	if request.method != 'POST':
		return redirect('member.list_workouts')

	workout.delete()
	messages.info(request, 'Workout deleted.')
	return redirect('member.list_workouts')


def member_exercise_history(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	exercise_name = (request.GET.get('exercise') or '').strip()
	if not exercise_name:
		messages.error(request, 'No exercise specified.')
		return redirect('member.list_workouts')

	# Fetch all workouts of the member for this exercise (ordered by date)
	workouts = list(
		Workout.objects.filter(member=member, exercise_name__iexact=exercise_name)
		.order_by('workout_date', 'id')
	)

	if not workouts:
		messages.error(request, f"No workout history found for '{exercise_name}'.")
		return redirect('member.list_workouts')

	category = workouts[0].exercise_category

	max_weight_so_far = 0.0
	max_1rm_so_far = 0.0
	max_distance_so_far = 0.0
	max_duration_so_far = 0

	enhanced_workouts = []
	for w in workouts:
		estimated_1rm = 0.0
		is_weight_pr = False
		is_1rm_pr = False
		is_distance_pr = False
		is_duration_pr = False

		if w.exercise_category == 'Strength' and w.reps and w.weight:
			estimated_1rm = round(w.weight * (1 + w.reps / 30.0), 1)
			
			if w.weight > max_weight_so_far:
				max_weight_so_far = w.weight
				is_weight_pr = True
			
			if estimated_1rm > max_1rm_so_far:
				max_1rm_so_far = estimated_1rm
				is_1rm_pr = True
		elif w.exercise_category == 'Cardio':
			if w.distance_km and w.distance_km > max_distance_so_far:
				max_distance_so_far = w.distance_km
				is_distance_pr = True
			if w.duration_minutes and w.duration_minutes > max_duration_so_far:
				max_duration_so_far = w.duration_minutes
				is_duration_pr = True

		enhanced_workouts.append({
			'id': w.id,
			'workout_date': w.workout_date,
			'sets': w.sets,
			'reps': w.reps,
			'weight': w.weight,
			'duration_minutes': w.duration_minutes,
			'distance_km': w.distance_km,
			'intensity': w.intensity,
			'notes': w.notes,
			'trainer_id': w.trainer_id,
			'estimated_1rm': estimated_1rm,
			'is_weight_pr': is_weight_pr,
			'is_1rm_pr': is_1rm_pr,
			'is_distance_pr': is_distance_pr,
			'is_duration_pr': is_duration_pr,
		})

	# Reverse for display (newest first)
	display_workouts = list(reversed(enhanced_workouts))

	# Data for progress charts (chronological order)
	chart_dates = [w['workout_date'].strftime('%b %d, %Y') for w in enhanced_workouts]
	chart_weights = [w['weight'] or 0.0 for w in enhanced_workouts]
	chart_1rms = [w['estimated_1rm'] for w in enhanced_workouts]
	chart_durations = [w['duration_minutes'] or 0 for w in enhanced_workouts]
	chart_distances = [w['distance_km'] or 0.0 for w in enhanced_workouts]

	return render(
		request,
		"member_dashboard/exercise_history.html",
		{
			"exercise_name": exercise_name,
			"category": category,
			"workouts": display_workouts,
			"chart_dates": chart_dates,
			"chart_weights": chart_weights,
			"chart_1rms": chart_1rms,
			"chart_durations": chart_durations,
			"chart_distances": chart_distances,
			"max_weight": max_weight_so_far,
			"max_1rm": max_1rm_so_far,
			"max_distance": max_distance_so_far,
			"max_duration": max_duration_so_far,
		},
	)




def member_programs(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	active_guides = list(
		GuideAssignment.objects.select_related('guide')
		.filter(member=member, is_active=True, is_completed=False)
		.order_by('-assignment_date', '-id')
	)
	completed_guides = list(
		GuideAssignment.objects.select_related('guide')
		.filter(member=member, is_completed=True)
		.order_by('-completion_date', '-id')[:12]
	)

	current_diet = (
		DietAssignment.objects.select_related('diet_plan')
		.filter(member=member, is_active=True)
		.order_by('-assignment_date', '-id')
		.first()
	)

	recent_workouts = list(Workout.objects.filter(member=member).order_by('-workout_date', '-id')[:10])
	stats = {
		"active_guides": len(active_guides),
		"completed_guides": len(completed_guides),
		"current_diet": current_diet is not None,
		"recent_workouts": len(recent_workouts),
	}

	return render(
		request,
		"member_dashboard/programs.html",
		{
			"active_guides": active_guides,
			"completed_guides": completed_guides,
			"current_diet": current_diet,
			"recent_workouts": recent_workouts,
			"stats": stats,
		},
	)


def member_current_diet(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	today = timezone.localdate()
	diet_assignment = (
		DietAssignment.objects.select_related('diet_plan')
		.filter(member=member, is_active=True)
		.order_by('-assignment_date', '-id')
		.first()
	)
	diet_plan = diet_assignment.diet_plan if diet_assignment else None

	meal_logs_today = list(
		MealLog.objects.filter(member=member, meal_date=today).order_by('-created_at', '-id')
	)
	agg = MealLog.objects.filter(member=member, meal_date=today).aggregate(
		calories=Sum('calories_actual'),
		protein_g=Sum('protein_g'),
		carbs_g=Sum('carbs_g'),
		fats_g=Sum('fats_g'),
	)
	daily_totals = SimpleNamespace(
		calories=agg.get('calories'),
		protein_g=agg.get('protein_g'),
		carbs_g=agg.get('carbs_g'),
		fats_g=agg.get('fats_g'),
	)

	return render(
		request,
		"member_dashboard/diet/current.html",
		{
			"diet_assignment": diet_assignment,
			"diet_plan": diet_plan,
			"daily_totals": daily_totals,
			"meal_logs_today": meal_logs_today,
			"estimated_burn": None,
		},
	)


def member_log_meal(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	diet_assignment = (
		DietAssignment.objects.select_related('diet_plan')
		.filter(member=member, is_active=True)
		.order_by('-assignment_date', '-id')
		.first()
	)
	diet_plan = diet_assignment.diet_plan if diet_assignment else None
	suggested_meals = list(MealPlan.objects.filter(diet_plan=diet_plan).order_by('day_name', 'meal_type', 'id')[:25]) if diet_plan else []

	if request.method == 'POST':
		meal_date_str = (request.POST.get('meal_date') or '').strip()
		meal_type = (request.POST.get('meal_type') or '').strip()
		meal_name = (request.POST.get('meal_name') or '').strip()
		calories_str = (request.POST.get('calories_actual') or '').strip()
		protein_str = (request.POST.get('protein_g') or '').strip()
		carbs_str = (request.POST.get('carbs_g') or '').strip()
		fats_str = (request.POST.get('fats_g') or '').strip()
		notes = (request.POST.get('notes') or '')[:500].strip()

		if not meal_date_str or not meal_type or not meal_name or not calories_str:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.log_meal')
		try:
			meal_date = timezone.datetime.fromisoformat(meal_date_str).date()
		except ValueError:
			messages.error(request, 'Invalid meal date.')
			return redirect('member.log_meal')
		try:
			calories_actual = int(calories_str)
		except ValueError:
			messages.error(request, 'Invalid calories value.')
			return redirect('member.log_meal')

		def _to_float(val: str):
			return float(val) if val else None

		MealLog.objects.create(
			member=member,
			diet_assignment=diet_assignment,
			meal_date=meal_date,
			meal_type=meal_type,
			meal_name=meal_name,
			calories_actual=calories_actual,
			protein_g=_to_float(protein_str),
			carbs_g=_to_float(carbs_str),
			fats_g=_to_float(fats_str),
			notes=notes,
		)
		messages.success(request, 'Meal logged.')
		return redirect('member.current_diet')

	return render(
		request,
		"member_dashboard/diet/log_meal.html",
		{
			"diet_assignment": diet_assignment,
			"diet_plan": diet_plan,
			"suggested_meals": suggested_meals,
			"today": timezone.localdate().isoformat(),
		},
	)


def member_diet_progress(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	diet_assignment = (
		DietAssignment.objects.select_related('diet_plan')
		.filter(member=member, is_active=True)
		.order_by('-assignment_date', '-id')
		.first()
	)
	if not diet_assignment or not diet_assignment.diet_plan or not diet_assignment.diet_plan.daily_calories:
		return render(
			request,
			"member_dashboard/diet/progress.html",
			{"diet_assignment": diet_assignment, "adherence_score": 0, "avg_weekly_calories": 0},
		)

	today = timezone.localdate()
	start = today - timedelta(days=30)
	logs = (
		MealLog.objects.filter(member=member, meal_date__gte=start, meal_date__lte=today)
		.values('meal_date')
		.annotate(total=Sum('calories_actual'))
	)
	target = diet_assignment.diet_plan.daily_calories or 0
	within = 0
	total_days = 0
	for row in logs:
		if row['total'] is None:
			continue
		total_days += 1
		if target > 0 and abs(row['total'] - target) <= (0.1 * target):
			within += 1

	adherence_score = int((within / total_days) * 100) if total_days else 0
	start_week = today - timedelta(days=7)
	avg_weekly = MealLog.objects.filter(member=member, meal_date__gte=start_week, meal_date__lte=today).aggregate(
		avg=Avg('calories_actual')
	).get('avg')
	avg_weekly_calories = int(avg_weekly or 0)

	return render(
		request,
		"member_dashboard/diet/progress.html",
		{
			"diet_assignment": diet_assignment,
			"adherence_score": adherence_score,
			"avg_weekly_calories": avg_weekly_calories,
		},
	)


def member_diet_history(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	assignments = list(
		DietAssignment.objects.select_related('diet_plan')
		.filter(member=member)
		.order_by('-assignment_date', '-id')
	)
	for a in assignments:
		if a.start_date is None:
			a.start_date = a.assignment_date
	return render(request, "member_dashboard/diet/history.html", {"assignments": assignments})


def member_guides_library(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = getattr(request.user, 'member_profile', None)
	if not request.user.is_authenticated or getattr(request.user, 'role', None) != 'member' or member is None:
		if getattr(request.user, 'role', None) == 'member' and member is None:
			member = None
		else:
			messages.error(request, 'Access denied.')
			return redirect('home')

	all_guides = WorkoutGuide.objects.filter(status=WorkoutGuide.Status.APPROVED).order_by('category', 'name', 'id')
	assigned_programs = GuideAssignment.objects.filter(member=member, is_active=True).select_related('guide').order_by('-assignment_date')

	return render(request, "member_dashboard/guides_library.html", {
		"guides": all_guides,
		"assigned_programs": assigned_programs,
	})


def member_view_assigned_guide(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	guide = WorkoutGuide.objects.filter(id=guide_id).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('member.member_programs')

	assignment = (
		GuideAssignment.objects.select_related('guide')
		.filter(member=member, guide=guide, is_active=True)
		.order_by('-assignment_date', '-id')
		.first()
	)

	if not assignment and guide.status != WorkoutGuide.Status.APPROVED:
		messages.error(request, 'This guide is not yet approved.')
		return redirect('member.member_programs')

	progress = assignment.calculate_progress() if assignment else 0
	tips = list(WorkoutTip.objects.filter(guide=guide).order_by('order', 'id'))
	logged_workouts = list(Workout.objects.filter(member=member, guide=guide).order_by('-workout_date', '-id')[:20]) if assignment else []

	grouped_tips = {}
	for tip in tips:
		exercise = tip.exercise_name or 'General'
		if exercise not in grouped_tips:
			grouped_tips[exercise] = []
		grouped_tips[exercise].append(tip)

	return render(
		request,
		"member_dashboard/guide_detail.html",
		{
			"guide": guide,
			"assignment": assignment,
			"progress": progress,
			"tips": tips,
			"grouped_tips": grouped_tips,
			"logged_workouts": logged_workouts,
		},
	)


def member_complete_guide(request: HttpRequest, assignment_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if request.method != 'POST':
		return redirect('member.member_programs')

	member = _require_member_access(request)
	if member is None:
		messages.error(request, 'Access denied.')
		return redirect('home')

	assignment = GuideAssignment.objects.filter(id=assignment_id, member=member, is_active=True).first()
	if assignment is None:
		messages.error(request, 'Guide assignment not found.')
		return redirect('member.member_programs')

	try:
		with transaction.atomic():
			assignment.is_completed = True
			assignment.completion_date = timezone.now()
			assignment.save(update_fields=['is_completed', 'completion_date', 'updated_at'])
		messages.success(request, f'Congratulations! You have completed "{assignment.guide.name}"!')
	except Exception as e:
		messages.error(request, f'Error completing guide: {str(e)}')

	return redirect('member.member_programs')


def member_change_password(request: HttpRequest, member_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	if request.method == 'POST':
		password = (request.POST.get('password') or '').strip()
		confirm_password = (request.POST.get('confirm_password') or '').strip()

		if not password or not confirm_password:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.view_member', member_id=member.id)

		if len(password) < 6:
			messages.error(request, 'Password must be at least 6 characters.')
			return redirect('member.view_member', member_id=member.id)

		if password != confirm_password:
			messages.error(request, 'Passwords do not match.')
			return redirect('member.view_member', member_id=member.id)

		member.user.set_password(password)
		member.user.save(update_fields=['password'])
		messages.success(request, f"Password updated successfully for {member.user.full_name}.")
		return redirect('member.view_member', member_id=member.id)

	return redirect('member.view_member', member_id=member.id)


@login_required
def start_assigned_guide_session(request: HttpRequest, assignment_id: int) -> HttpResponse:
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	assignment = GuideAssignment.objects.filter(id=assignment_id, member=member, is_active=True).first()
	if assignment is None:
		messages.error(request, 'Guide assignment not found.')
		return redirect('member.member_programs')

	return redirect(reverse('member.create_workout') + f"?guide_id={assignment.guide_id}&tip_index=0")
