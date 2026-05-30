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

from tracker.models import Member, Trainer, TrainerAssignment, Attendance, FitnessMetric, Workout, GuideAssignment, DietAssignment, MealLog, MealPlan, WorkoutGuide, WorkoutTip
from tracker.forms import MemberForm, WorkoutForm
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
	else:
		status = 'all'

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

		default_password = 'GymTrack2026!'

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


def member_import_csv(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method == 'POST':
		csv_file = request.FILES.get('csv_file')
		if not csv_file:
			messages.error(request, 'Please choose a CSV file.')
			return redirect('member.import_csv')

		User = get_user_model()
		imported = 0
		skipped = 0
		errors: list[dict[str, Any]] = []
		default_password = 'GymTrack2026!'

		try:
			text = io.TextIOWrapper(csv_file.file, encoding='utf-8')
			reader = csv.DictReader(text)
			for idx, row in enumerate(reader, start=2):
				try:
					full_name = (row.get('full_name') or '').strip()
					email = (row.get('email') or '').strip().lower()
					membership_start = (row.get('membership_start_date') or '').strip()
					membership_expiry = (row.get('membership_expiry_date') or '').strip()

					if not full_name or not email or not membership_start or not membership_expiry:
						errors.append({"row": idx, "error": "Missing required fields"})
						skipped += 1
						continue
					if User.objects.filter(email__iexact=email).exists():
						skipped += 1
						continue

					try:
						membership_start_date = timezone.datetime.fromisoformat(membership_start).date()
						membership_expiry_date = timezone.datetime.fromisoformat(membership_expiry).date()
					except ValueError:
						errors.append({"row": idx, "error": "Invalid membership date(s)"})
						skipped += 1
						continue

					phone_number = (row.get('phone_number') or '').strip()
					gender = (row.get('gender') or '').strip()
					dob_str = (row.get('date_of_birth') or '').strip()
					date_of_birth = None
					if dob_str:
						try:
							date_of_birth = timezone.datetime.fromisoformat(dob_str).date()
						except ValueError:
							errors.append({"row": idx, "error": "Invalid date_of_birth"})
							skipped += 1
							continue

					membership_type = (row.get('membership_type') or 'monthly').strip() or 'monthly'

					base_username = (email.split('@', 1)[0] or 'member')[:150]
					username = base_username
					suffix = 1
					while User.objects.filter(username__iexact=username).exists():
						suffix += 1
						username = f"{base_username}{suffix}"[:150]

					with transaction.atomic():
						user = User.objects.create_user(username=username, email=email, password=default_password)
						user.full_name = full_name
						user.role = User.Role.MEMBER
						user.is_active = True
						user.save(update_fields=['full_name', 'role', 'is_active'])

						Member.objects.create(
							user=user,
							phone_number=phone_number,
							gender=gender,
							date_of_birth=date_of_birth,
							membership_type=membership_type,
							membership_start_date=membership_start_date,
							membership_expiry_date=membership_expiry_date,
							is_active=True,
							is_approved=True,
							approval_date=timezone.now(),
						)

					imported += 1
				except Exception as exc:
					errors.append({"row": idx, "error": str(exc)})
					skipped += 1

		except Exception as exc:
			messages.error(request, f"Failed to read CSV: {exc}")
			return redirect('member.import_csv')

		import_result = {
			"imported": imported,
			"skipped": skipped,
			"errors": errors,
		}
		return render(request, "member/import.html", {"import_result": import_result})

	return render(request, "member/import.html")


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

	return render(
		request,
		"member_dashboard/dashboard.html",
		{
			"attendance_count": attendance_count,
			"recent_workouts": recent_workouts,
		},
	)


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

		form = MemberForm(request.POST, instance=member)
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

	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = Workout.objects.select_related('trainer').filter(member=member).order_by('-workout_date', '-id')
	paginator = Paginator(qs, 10)
	page_obj = paginator.get_page(page_number)
	pagination = _PaginationAdapter(paginator, page_obj)

	return render(
		request,
		"member_dashboard/workouts.html",
		{
			"workouts": list(page_obj.object_list),
			"pagination": pagination,
		},
	)


def member_workout_form(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method == 'POST':
		workout_date_str = (request.POST.get('workout_date') or '').strip()
		exercise_name = (request.POST.get('exercise_name') or '').strip()
		exercise_category = (request.POST.get('exercise_category') or '').strip()

		if not workout_date_str or not exercise_name or not exercise_category:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.create_workout')

		form = WorkoutForm(request.POST)
		if form.is_valid():
			workout = form.save(commit=False)
			workout.member = member
			workout.save()
			messages.success(request, 'Workout logged.')
			return redirect('member.list_workouts')
		else:
			messages.error(request, 'Invalid data fields.')
			return redirect('member.create_workout')

	return render(request, "member_dashboard/workout_form.html", {"workout": None})


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
			form.save()
			messages.success(request, 'Workout updated.')
			return redirect('member.list_workouts')
		else:
			messages.error(request, 'Invalid workout fields.')
			return redirect('member.edit_workout', workout_id=workout.id)

	return render(request, "member_dashboard/workout_form.html", {"workout": workout})


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
