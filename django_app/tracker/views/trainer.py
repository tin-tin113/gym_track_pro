from __future__ import annotations

import secrets
from datetime import timedelta, datetime
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

from tracker.models import (
	Member,
	Trainer,
	TrainerAssignment,
	Attendance,
	FitnessMetric,
	Workout,
	WorkoutGuide,
	WorkoutTip,
	GuideAssignment,
	DietPlan,
	MealPlan,
	DietAssignment,
	GuestVisit,
)
from .base import _require_roles, _PaginationAdapter, _PaginationItemsAdapter, _validate_date_range


# --- Helpers ---

def _require_trainer_or_admin(request: HttpRequest) -> bool:
	role = getattr(request.user, 'role', None)
	return bool(request.user.is_authenticated and role in {'trainer', 'admin'})


def _can_view_member_as_trainer(request: HttpRequest, member: Member) -> bool:
	role = getattr(request.user, 'role', None)
	if role == 'admin':
		return True
	if role == 'trainer':
		return member.assigned_trainer_id == request.user.id
	return False


# --- Admin Dashboard & Approvals ---

def admin_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	today = timezone.localdate()
	stats = {
		"total_members": Member.objects.count(),
		"active_members": Member.objects.filter(
			is_approved=True,
			is_active=True,
			membership_expiry_date__gte=today,
		).count(),
		"total_trainers": Trainer.objects.count(),
		"total_users": get_user_model().objects.count(),
	}

	expiring_members = list(
		Member.objects.filter(
			is_approved=True,
			is_active=True,
			membership_expiry_date__gte=today,
			membership_expiry_date__lte=today + timedelta(days=7),
		).select_related('user')
	)

	return render(request, "admin/dashboard.html", {"stats": stats, "expiring_members": expiring_members})


@login_required
def admin_pending_approvals(request: HttpRequest) -> HttpResponse:
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	search = (request.GET.get('search') or '').strip()
	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = Member.objects.select_related('user').filter(is_approved=False).order_by('-created_at', '-id')
	if search:
		qs = qs.filter(Q(user__full_name__icontains=search) | Q(user__email__icontains=search))

	paginator = Paginator(qs, 10)
	page_obj = paginator.get_page(page_number)
	pagination = _PaginationAdapter(paginator, page_obj)

	pending_renewals = list(
		Member.objects.select_related('user')
		.filter(pending_renewal_plan__isnull=False)
		.order_by('-updated_at')
	)

	return render(
		request,
		"admin/pending_approvals.html",
		{
			"pending_members": list(page_obj.object_list),
			"search": search,
			"pagination": pagination,
			"pending_renewals": pending_renewals,
		},
	)


def admin_pending_guides(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = (
		WorkoutGuide.objects.select_related('trainer')
		.filter(status=WorkoutGuide.Status.PENDING)
		.order_by('-created_at', '-id')
	)
	paginator = Paginator(qs, 10)
	page_obj = paginator.get_page(page_number)
	guides = _PaginationItemsAdapter(paginator, page_obj, list(page_obj.object_list))
	return render(request, "admin/guides/pending.html", {"guides": guides})


def admin_all_guides(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	status = (request.GET.get('status') or '').strip().lower()
	allowed = {
		WorkoutGuide.Status.APPROVED,
		WorkoutGuide.Status.PENDING,
		WorkoutGuide.Status.REJECTED,
		WorkoutGuide.Status.DRAFT,
	}
	qs = WorkoutGuide.objects.select_related('trainer').all().order_by('-created_at', '-id')
	if status and status in allowed:
		qs = qs.filter(status=status)

	items = list(qs[:200])
	guides = SimpleNamespace(items=items)
	return render(request, "admin/guides/all.html", {"guides": guides, "status": status})


def admin_review_guide(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	guide = WorkoutGuide.objects.prefetch_related('tips').select_related('trainer').filter(id=guide_id).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('admin.pending_guides')

	tips = list(guide.tips.all().order_by('order', 'id'))
	approve_url = reverse('admin.approve_guide', kwargs={'guide_id': guide.id})
	reject_url = reverse('admin.reject_guide', kwargs={'guide_id': guide.id})

	return render(request, 'admin/guides/review.html', {
		'guide': guide,
		'tips': tips,
		'approve_url': approve_url,
		'reject_url': reject_url,
	})


def admin_approve_guide(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')
	if request.method != 'POST':
		return redirect('admin.review_guide', guide_id=guide_id)

	guide = WorkoutGuide.objects.filter(id=guide_id).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('admin.pending_guides')

	guide.status = WorkoutGuide.Status.APPROVED
	guide.rejection_reason = ''
	guide.save(update_fields=['status', 'rejection_reason', 'updated_at'])
	messages.success(request, 'Guide approved.')
	return redirect('admin.pending_guides')


def admin_reject_guide(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')
	if request.method != 'POST':
		return redirect('admin.review_guide', guide_id=guide_id)

	reason = (request.POST.get('reason') or '').strip()
	if not reason:
		messages.error(request, 'Rejection reason is required.')
		return redirect('admin.review_guide', guide_id=guide_id)

	guide = WorkoutGuide.objects.filter(id=guide_id).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('admin.pending_guides')

	guide.status = WorkoutGuide.Status.REJECTED
	guide.rejection_reason = reason
	guide.save(update_fields=['status', 'rejection_reason', 'updated_at'])
	messages.info(request, 'Guide rejected.')
	return redirect('admin.pending_guides')


@login_required
def admin_approve_member(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	member.is_approved = True
	member.approval_date = timezone.now()

	today = timezone.localdate()
	member.membership_start_date = today
	days_to_add = 30
	if member.membership_type == Member.MembershipType.QUARTERLY:
		days_to_add = 90
	elif member.membership_type == Member.MembershipType.ANNUAL:
		days_to_add = 365
	member.membership_expiry_date = today + timedelta(days=days_to_add)

	member.save(update_fields=['is_approved', 'approval_date', 'membership_start_date', 'membership_expiry_date'])
	messages.success(request, f"Approved member: {member.user.full_name}")
	return redirect('member.list_members')


@login_required
def admin_reject_member(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	with transaction.atomic():
		user = member.user
		member.delete()
		user.delete()

	messages.info(request, 'Member rejected and removed.')
	return redirect('member.list_members')


# --- Staff Management ---

def staff_list(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	search = (request.GET.get('search') or '').strip()
	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	User = get_user_model()
	# Separate active and inactive staff
	qs_active = User.objects.filter(role=User.Role.STAFF, is_active=True).order_by('full_name', 'id')
	qs_inactive = User.objects.filter(role=User.Role.STAFF, is_active=False).order_by('full_name', 'id')

	if search:
		qs_active = qs_active.filter(Q(full_name__icontains=search) | Q(email__icontains=search) | Q(username__icontains=search))
		qs_inactive = qs_inactive.filter(Q(full_name__icontains=search) | Q(email__icontains=search) | Q(username__icontains=search))

	# Combine for pagination
	all_staff = list(qs_active) + list(qs_inactive)
	paginator = Paginator(all_staff, 10)
	page_obj = paginator.get_page(page_number)
	pagination = _PaginationAdapter(paginator, page_obj)

	return render(
		request,
		"staff/list.html",
		{
			"staff": list(page_obj.object_list),
			"search": search,
			"pagination": pagination,
		},
	)


def staff_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Staff access required.')
		return redirect('home')

	today = timezone.localdate()
	start_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	end_of_day = start_of_day + timedelta(days=1)

	# 1. Performance Indicator Counters
	active_members_count = Member.objects.filter(
		is_approved=True,
		is_active=True,
		membership_expiry_date__gte=today
	).count()

	today_checkins_count = Attendance.objects.filter(
		check_in_time__gte=start_of_day,
		check_in_time__lt=end_of_day
	).count()

	pending_approvals_count = Member.objects.filter(is_approved=False).count()

	today_guests_count = GuestVisit.objects.filter(visit_date=today).count()

	stats = SimpleNamespace(
		active_members=active_members_count,
		today_checkins=today_checkins_count,
		pending_approvals=pending_approvals_count,
		today_guests=today_guests_count,
	)

	# 2. Live Queues
	# 5 most recent pending approvals
	pending_members = list(
		Member.objects.select_related('user')
		.filter(is_approved=False)
		.order_by('-created_at', '-id')[:5]
	)

	# 5 most recent checked in members today
	recent_checkins = list(
		Attendance.objects.select_related('member__user')
		.filter(check_in_time__gte=start_of_day, check_in_time__lt=end_of_day)
		.order_by('-check_in_time', '-id')[:5]
	)

	expiring_members = list(
		Member.objects.filter(
			is_approved=True,
			is_active=True,
			membership_expiry_date__gte=today,
			membership_expiry_date__lte=today + timedelta(days=7),
		).select_related('user')
	)

	return render(
		request,
		'staff/dashboard.html',
		{
			'stats': stats,
			'pending_members': pending_members,
			'recent_checkins': recent_checkins,
			'expiring_members': expiring_members,
		}
	)



def staff_create_staff(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		email = (request.POST.get('email') or '').strip().lower()
		if not full_name or not email:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('staff.create_staff')

		User = get_user_model()
		if User.objects.filter(email__iexact=email).exists():
			messages.error(request, 'A user with that email already exists.')
			return redirect('staff.create_staff')

		base_username = (email.split('@', 1)[0] or 'staff')[:150]
		username = base_username
		suffix = 1
		while User.objects.filter(username__iexact=username).exists():
			suffix += 1
			username = f"{base_username}{suffix}"[:150]

		setup_token = secrets.token_urlsafe(32)
		setup_expiry = timezone.now() + timedelta(hours=24)

		with transaction.atomic():
			user = User.objects.create_user(username=username, email=email, password=secrets.token_urlsafe(16))
			user.full_name = full_name
			user.role = User.Role.STAFF
			user.is_active = True
			user.is_staff = True
			user.setup_token = setup_token
			user.setup_token_expiry = setup_expiry
			user.save(
				update_fields=[
					'full_name',
					'role',
					'is_active',
					'is_staff',
					'setup_token',
					'setup_token_expiry',
				]
			)

		setup_link = request.build_absolute_uri(reverse('auth.setup_password') + f"?token={setup_token}")
		messages.success(request, f"Staff member created. Setup link (expires in 24h): {setup_link}")
		return redirect('staff.edit_staff', staff_id=user.id)

	return render(request, 'staff/edit.html', {'staff_user': None})


def staff_edit_staff(request: HttpRequest, staff_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	User = get_user_model()
	staff_user = User.objects.filter(id=staff_id, role=User.Role.STAFF).first()
	if staff_user is None:
		messages.error(request, 'Staff member not found.')
		return redirect('staff.list_staff')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		if not full_name:
			messages.error(request, 'Full name is required.')
			return redirect('staff.edit_staff', staff_id=staff_user.id)
		staff_user.full_name = full_name
		staff_user.save(update_fields=['full_name'])
		messages.success(request, 'Staff member updated.')
		return redirect('staff.edit_staff', staff_id=staff_user.id)

	return render(request, 'staff/edit.html', {'staff_user': staff_user})


def staff_delete_staff(request: HttpRequest, staff_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')
	if request.method != 'POST':
		return redirect('staff.list_staff')

	User = get_user_model()
	staff_user = User.objects.filter(id=staff_id, role=User.Role.STAFF).first()
	if staff_user is None:
		messages.error(request, 'Staff member not found.')
		return redirect('staff.list_staff')

	staff_user.is_active = False
	staff_user.save(update_fields=['is_active'])

	# Invalidate all existing sessions for this user
	from django.contrib.sessions.models import Session
	for session in Session.objects.all():
		session_data = session.get_decoded()
		if session_data.get('_auth_user_id') == str(staff_user.id):
			session.delete()

	messages.info(request, f'Staff member "{staff_user.full_name}" deactivated.')
	return redirect('staff.list_staff')


def staff_reactivate_staff(request: HttpRequest, staff_id: int) -> HttpResponse:
	"""Reactivate a deactivated staff account."""
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')
	if request.method != 'POST':
		return redirect('staff.list_staff')

	User = get_user_model()
	staff_user = User.objects.filter(id=staff_id, role=User.Role.STAFF).first()
	if staff_user is None:
		messages.error(request, 'Staff member not found.')
		return redirect('staff.list_staff')

	staff_user.is_active = True
	staff_user.save(update_fields=['is_active'])
	messages.success(request, f'Staff member "{staff_user.full_name}" reactivated.')
	return redirect('staff.list_staff')


# --- Trainer Dashboard ---

def trainer_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')

	role = getattr(request.user, 'role', None)
	if role not in {'trainer', 'admin'}:
		messages.error(request, 'Access denied.')
		return redirect('home')

	current_user_is_trainer = role == 'trainer'
	trainer = getattr(request.user, 'trainer_profile', None) if current_user_is_trainer else None

	today = timezone.localdate()
	start_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	end_of_day = start_of_day + timedelta(days=1)
	start_30 = timezone.make_aware(timezone.datetime.combine(today - timedelta(days=30), timezone.datetime.min.time()))

	member_qs = Member.objects.select_related('user').filter(is_active=True, is_approved=True)
	if current_user_is_trainer:
		member_qs = member_qs.filter(assigned_trainer=request.user)

	members = list(member_qs.order_by('user__full_name', 'id')[:50])
	assigned_member_ids = [m.id for m in members]

	active_today = Attendance.objects.filter(
		member_id__in=assigned_member_ids,
		check_in_time__gte=start_of_day,
		check_in_time__lt=end_of_day,
	).values('member_id').distinct().count() if assigned_member_ids else 0

	recent_checkins = Attendance.objects.filter(
		member_id__in=assigned_member_ids,
		check_in_time__gte=start_30,
	).count() if assigned_member_ids else 0

	active_30_ids = set(
		Attendance.objects.filter(member_id__in=assigned_member_ids, check_in_time__gte=start_30)
		.values_list('member_id', flat=True)
		.distinct()
	) if assigned_member_ids else set()
	inactive_30plus = sum(1 for m in members if m.id not in active_30_ids)

	stats = SimpleNamespace(
		assigned_members=len(members),
		active_today=active_today,
		recent_checkins=recent_checkins,
		inactive_30plus=inactive_30plus,
	)

	return render(
		request,
		"trainer/dashboard.html",
		{
			"stats": stats,
			"trainer": trainer,
			"members": members,
			"current_user_is_trainer": current_user_is_trainer,
		},
	)


def trainer_members(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')

	role = getattr(request.user, 'role', None)
	if role not in {'trainer', 'admin'}:
		messages.error(request, 'Access denied.')
		return redirect('home')

	current_user_is_trainer = role == 'trainer'
	qs = Member.objects.select_related('user').filter(is_active=True, is_approved=True)
	if current_user_is_trainer:
		qs = qs.filter(assigned_trainer=request.user)
	else:
		qs = qs.order_by('user__full_name', 'id')[:10]

	members = list(qs)
	member_ids = [m.id for m in members]

	start_30 = timezone.now() - timedelta(days=30)
	attendance_rows = (
		Attendance.objects.filter(member_id__in=member_ids, check_in_time__gte=start_30)
		.values('member_id')
		.annotate(total_visits=Count('id'), avg_duration=Avg('duration_minutes'))
	) if member_ids else []
	attendance_map = {r['member_id']: r for r in attendance_rows}

	member_data = []
	for m in members:
		row = attendance_map.get(m.id) or {}
		stats = SimpleNamespace(
			total_visits=int(row.get('total_visits') or 0),
			avg_duration=int((row.get('avg_duration') or 0) or 0),
		)
		member_data.append(
			SimpleNamespace(
				member=m,
				stats=stats,
				days_since_visit=m.days_since_last_visit(),
			)
		)

	return render(
		request,
		"trainer/members.html",
		{
			"members": member_data,
			"current_user_is_trainer": current_user_is_trainer,
		},
	)


def trainer_list(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	search = (request.GET.get('search') or '').strip()
	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	# Separate active and inactive trainers
	qs_active = Trainer.objects.select_related('user').filter(user__is_active=True).order_by('user__full_name', 'id')
	qs_inactive = Trainer.objects.select_related('user').filter(user__is_active=False).order_by('user__full_name', 'id')

	if search:
		qs_active = qs_active.filter(Q(user__full_name__icontains=search) | Q(user__email__icontains=search))
		qs_inactive = qs_inactive.filter(Q(user__full_name__icontains=search) | Q(user__email__icontains=search))

	# Combine for pagination
	all_trainers = list(qs_active) + list(qs_inactive)
	paginator = Paginator(all_trainers, 10)
	page_obj = paginator.get_page(page_number)
	pagination = _PaginationAdapter(paginator, page_obj)

	now = timezone.now()
	trainer_rows = list(page_obj.object_list)

	trainers = []
	for t in trainer_rows:
		member_count = Member.objects.filter(assigned_trainer=t.user, is_active=True, is_approved=True).count()
		at_capacity = member_count >= (t.max_clients or 0)

		setup_status = 'active'
		setup_link = ''
		setup_token_expiry = None
		if t.user.setup_token:
			setup_token_expiry = t.user.setup_token_expiry
			if setup_token_expiry and setup_token_expiry < now:
				setup_status = 'expired'
			else:
				setup_status = 'pending'
			setup_link = request.build_absolute_uri(reverse('auth.setup_password') + f"?token={t.user.setup_token}")

		trainers.append(
			SimpleNamespace(
				trainer=t,
				member_count=member_count,
				at_capacity=at_capacity,
				setup_status=setup_status,
				setup_token_expiry=setup_token_expiry,
				setup_link=setup_link,
			)
		)

	return render(
		request,
		"trainer/list.html",
		{
			"trainers": trainers,
			"search": search,
			"pagination": pagination,
			"now": now,
		},
	)


# --- Trainer Guides ---

def trainer_guides(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')

	role = getattr(request.user, 'role', None)
	if role not in {'trainer', 'admin'}:
		messages.error(request, 'Access denied.')
		return redirect('home')

	status = (request.GET.get('status') or '').strip().lower()
	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = WorkoutGuide.objects.all().order_by('-created_at', '-id')
	if role == 'trainer':
		qs = qs.filter(trainer=request.user)
	if status in {'draft', 'pending', 'approved', 'rejected'}:
		qs = qs.filter(status=status)

	paginator = Paginator(qs, 10)
	page_obj = paginator.get_page(page_number)
	items = list(page_obj.object_list)
	guides = _PaginationItemsAdapter(paginator, page_obj, items)

	return render(request, "trainer/guides/list.html", {"guides": guides, "status": status})


def trainer_browse_guides(request: HttpRequest) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	items = list(WorkoutGuide.objects.filter(status=WorkoutGuide.Status.APPROVED).order_by('category', 'name', 'id'))
	guides = SimpleNamespace(items=items)
	return render(request, 'trainer/guides/library.html', {'guides': guides})


def trainer_create_guide(request: HttpRequest) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'trainer':
		messages.error(request, 'Trainer access required.')
		return redirect('trainer.list_guides')

	if request.method == 'POST':
		name = (request.POST.get('name') or '').strip()
		description = (request.POST.get('description') or '').strip()
		category = (request.POST.get('category') or '').strip()
		difficulty_level = (request.POST.get('difficulty_level') or '').strip() or 'Intermediate'
		duration_weeks_str = (request.POST.get('duration_weeks') or '').strip()
		target_goals = (request.POST.get('target_goals') or '').strip()
		equipment_needed = (request.POST.get('equipment_needed') or '').strip()

		if not name or not category or not difficulty_level:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('trainer.create_guide')
		duration_weeks = None
		if duration_weeks_str:
			try:
				duration_weeks = int(duration_weeks_str)
			except ValueError:
				messages.error(request, 'Invalid duration.')
				return redirect('trainer.create_guide')

		guide = WorkoutGuide.objects.create(
			name=name,
			description=description,
			category=category,
			difficulty_level=difficulty_level,
			duration_weeks=duration_weeks,
			target_goals=target_goals,
			equipment_needed=equipment_needed,
			trainer=request.user,
			status=WorkoutGuide.Status.DRAFT,
		)
		# Handle optional image upload
		if 'image' in request.FILES:
			guide.image = request.FILES['image']
			guide.save(update_fields=['image'])
		messages.success(request, 'Guide created (draft).')
		return redirect('trainer.edit_guide', guide_id=guide.id)

	return render(request, 'trainer/guides/form.html', {'guide': None})


def trainer_edit_guide(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'trainer':
		messages.error(request, 'Trainer access required.')
		return redirect('trainer.list_guides')

	guide = WorkoutGuide.objects.filter(id=guide_id, trainer=request.user).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('trainer.list_guides')
	if guide.status not in {WorkoutGuide.Status.DRAFT, WorkoutGuide.Status.REJECTED}:
		messages.error(request, 'Only draft or rejected guides can be edited.')
		return redirect('trainer.view_guide', guide_id=guide.id)

	if request.method == 'POST':
		name = (request.POST.get('name') or '').strip()
		description = (request.POST.get('description') or '').strip()
		category = (request.POST.get('category') or '').strip()
		difficulty_level = (request.POST.get('difficulty_level') or '').strip() or guide.difficulty_level
		duration_weeks_str = (request.POST.get('duration_weeks') or '').strip()
		target_goals = (request.POST.get('target_goals') or '').strip()
		equipment_needed = (request.POST.get('equipment_needed') or '').strip()

		if not name or not category or not difficulty_level:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('trainer.edit_guide', guide_id=guide.id)
		duration_weeks = None
		if duration_weeks_str:
			try:
				duration_weeks = int(duration_weeks_str)
			except ValueError:
				messages.error(request, 'Invalid duration.')
				return redirect('trainer.edit_guide', guide_id=guide.id)

		guide.name = name
		guide.description = description
		guide.category = category
		guide.difficulty_level = difficulty_level
		guide.duration_weeks = duration_weeks
		guide.target_goals = target_goals
		guide.equipment_needed = equipment_needed
		# Handle image upload — delete old file if a new one is provided
		if 'image' in request.FILES:
			if guide.image:
				try:
					guide.image.delete(save=False)
				except Exception:
					pass
			guide.image = request.FILES['image']
		guide.save()
		messages.success(request, 'Guide updated.')
		return redirect('trainer.edit_guide', guide_id=guide.id)

	tips = list(guide.tips.all().order_by('exercise_name', 'id'))
	return render(request, 'trainer/guides/form.html', {'guide': guide, 'tips': tips})


def trainer_view_guide(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	guide = WorkoutGuide.objects.filter(id=guide_id).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('trainer.list_guides')
	return render(request, 'trainer/guides/detail.html', {'guide': guide})


def trainer_delete_guide(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if request.method != 'POST':
		return redirect('trainer.list_guides')
	if getattr(request.user, 'role', None) != 'trainer':
		messages.error(request, 'Trainer access required.')
		return redirect('trainer.list_guides')

	guide = WorkoutGuide.objects.filter(id=guide_id, trainer=request.user).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('trainer.list_guides')
	if guide.status not in {WorkoutGuide.Status.DRAFT, WorkoutGuide.Status.REJECTED}:
		messages.error(request, 'Only draft or rejected guides can be deleted.')
		return redirect('trainer.list_guides')

	guide.delete()
	messages.info(request, 'Guide deleted.')
	return redirect('trainer.list_guides')


def trainer_submit_guide(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if request.method != 'POST':
		return redirect('trainer.list_guides')
	if getattr(request.user, 'role', None) != 'trainer':
		messages.error(request, 'Trainer access required.')
		return redirect('trainer.list_guides')

	guide = WorkoutGuide.objects.filter(id=guide_id, trainer=request.user).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('trainer.list_guides')
	if guide.status != WorkoutGuide.Status.DRAFT:
		messages.info(request, 'Guide is not a draft.')
		return redirect('trainer.list_guides')

	guide.status = WorkoutGuide.Status.PENDING
	guide.save(update_fields=['status'])
	messages.success(request, 'Guide submitted for approval.')
	return redirect('trainer.list_guides')


def trainer_add_guide_tip(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if request.method != 'POST':
		return redirect('trainer.edit_guide', guide_id=guide_id)
	if getattr(request.user, 'role', None) != 'trainer':
		messages.error(request, 'Trainer access required.')
		return redirect('trainer.list_guides')

	guide = WorkoutGuide.objects.filter(id=guide_id, trainer=request.user).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('trainer.list_guides')

	exercise_name = (request.POST.get('exercise_name') or '').strip()
	tip_category = (request.POST.get('tip_category') or '').strip()
	content = (request.POST.get('content') or '').strip()
	if not exercise_name or not tip_category or not content:
		messages.error(request, 'Please fill in all required fields.')
		return redirect('trainer.edit_guide', guide_id=guide.id)

	WorkoutTip.objects.create(guide=guide, exercise_name=exercise_name, tip_category=tip_category, content=content)
	messages.success(request, 'Tip added.')
	return redirect('trainer.edit_guide', guide_id=guide.id)


def trainer_delete_guide_tip(request: HttpRequest, guide_id: int, tip_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if request.method != 'POST':
		return redirect('trainer.edit_guide', guide_id=guide_id)
	if getattr(request.user, 'role', None) != 'trainer':
		messages.error(request, 'Trainer access required.')
		return redirect('trainer.list_guides')

	guide = WorkoutGuide.objects.filter(id=guide_id, trainer=request.user).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('trainer.list_guides')

	WorkoutTip.objects.filter(id=tip_id, guide=guide).delete()
	messages.info(request, 'Tip deleted.')
	return redirect('trainer.edit_guide', guide_id=guide.id)


def trainer_member_guides(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	assignments = list(
		GuideAssignment.objects.select_related('guide')
		.filter(member=member, is_active=True)
		.order_by('-assignment_date', '-id')
	)
	return render(request, 'trainer/guides/member_guides.html', {'member': member, 'assignments': assignments})


def trainer_assign_guide_to_member(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	guides = list(WorkoutGuide.objects.filter(status=WorkoutGuide.Status.APPROVED).order_by('category', 'name', 'id'))
	if request.method == 'POST':
		guide_id = (request.POST.get('guide_id') or '').strip()
		notes = (request.POST.get('notes') or '')[:1000].strip()
		start_date_str = (request.POST.get('start_date') or '').strip()
		target_completion_str = (request.POST.get('target_completion_date') or '').strip()

		guide = WorkoutGuide.objects.filter(id=guide_id, status=WorkoutGuide.Status.APPROVED).first() if guide_id else None
		if guide is None:
			messages.error(request, 'Please select a valid guide.')
			return redirect('trainer.assign_guide_to_member', member_id=member.id)

		start_date, target_completion_date, date_error = _validate_date_range(start_date_str, target_completion_str)
		if date_error:
			messages.error(request, date_error)
			return redirect('trainer.assign_guide_to_member', member_id=member.id)

		try:
			with transaction.atomic():
				GuideAssignment.objects.create(
					guide=guide,
					member=member,
					trainer=request.user,
					notes=notes,
					is_active=True,
					start_date=start_date,
					target_completion_date=target_completion_date
				)
			message = f'Guide "{guide.name}" assigned to {member.user.full_name}.'
			if start_date and target_completion_date:
				duration_days = (target_completion_date.date() - start_date.date()).days
				message += f' | Duration: {duration_days} days'
			messages.success(request, message)
			return redirect('trainer.member_guides', member_id=member.id)
		except Exception as e:
			messages.error(request, f'Error assigning guide: {str(e)}')
			return redirect('trainer.assign_guide_to_member', member_id=member.id)

	return render(request, 'trainer/guides/assign_member.html', {'member': member, 'guides': guides})


def trainer_unassign_guide(request: HttpRequest, member_id: int, guide_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if request.method != 'POST':
		return redirect('trainer.member_guides', member_id=member_id)
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	GuideAssignment.objects.filter(member=member, guide_id=guide_id, is_active=True).update(is_active=False)
	messages.info(request, 'Guide unassigned.')
	return redirect('trainer.member_guides', member_id=member.id)


def trainer_complete_member_guide(request: HttpRequest, assignment_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if request.method != 'POST':
		messages.error(request, 'Invalid request method.')
		return redirect('home')

	if not _require_roles(request, {'trainer', 'admin'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	assignment = GuideAssignment.objects.select_related('member', 'guide').filter(id=assignment_id).first()
	if assignment is None:
		messages.error(request, 'Guide assignment not found.')
		return redirect('home')

	if not _can_view_member_as_trainer(request, assignment.member):
		messages.error(request, 'Access denied.')
		return redirect('home')

	try:
		with transaction.atomic():
			assignment.is_completed = True
			assignment.completion_date = timezone.now()
			assignment.save(update_fields=['is_completed', 'completion_date', 'updated_at'])
		messages.success(request, f'Guide "{assignment.guide.name}" marked as completed for {assignment.member.user.full_name}')
	except Exception as e:
		messages.error(request, f'Error completing guide: {str(e)}')

	return redirect('trainer.member_guides', member_id=assignment.member.id)


# --- Trainer Diets ---

def trainer_diets(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')

	role = getattr(request.user, 'role', None)
	if role not in {'trainer', 'admin'}:
		messages.error(request, 'Access denied.')
		return redirect('home')

	plan_type = (request.GET.get('type') or '').strip()
	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = DietPlan.objects.filter(is_active=True).order_by('name', 'id')
	if plan_type:
		qs = qs.filter(diet_type=plan_type)

	paginator = Paginator(qs, 9)
	page_obj = paginator.get_page(page_number)
	plans = _PaginationItemsAdapter(paginator, page_obj, list(page_obj.object_list))

	return render(request, "trainer/diet/list.html", {"plans": plans, "plan_type": plan_type})


def trainer_create_diet_plan(request: HttpRequest) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method == 'POST':
		name = (request.POST.get('name') or '').strip()
		description = (request.POST.get('description') or '').strip()
		diet_type = (request.POST.get('diet_type') or 'balanced').strip()
		daily_calories_str = (request.POST.get('daily_calories') or '').strip()
		notes = (request.POST.get('notes') or '')[:1000].strip()

		protein_pct = float(request.POST.get('macro_ratio_protein') or '30')
		carbs_pct = float(request.POST.get('macro_ratio_carbs') or '45')
		fats_pct = float(request.POST.get('macro_ratio_fats') or '25')

		if not name or not daily_calories_str:
			messages.error(request, 'Name and Calorie Target are required.')
			return redirect('trainer.create_diet_plan')

		try:
			daily_calories = int(daily_calories_str)
		except ValueError:
			messages.error(request, 'Daily calories must be a whole number.')
			return redirect('trainer.create_diet_plan')

		if abs((protein_pct + carbs_pct + fats_pct) - 100.0) > 0.01:
			messages.error(request, 'Macro percentages must sum to 100%.')
			return redirect('trainer.create_diet_plan')

		plan = DietPlan.objects.create(
			name=name,
			description=description,
			diet_type=diet_type,
			daily_calories=daily_calories,
			macro_ratio_protein=protein_pct / 100.0,
			macro_ratio_carbs=carbs_pct / 100.0,
			macro_ratio_fats=fats_pct / 100.0,
			notes=notes,
			created_by=request.user,
			is_active=True,
		)
		messages.success(request, f'Diet plan "{plan.name}" created.')
		return redirect('trainer.view_diet_plan', plan_id=plan.id)

	return render(request, 'trainer/diet/form.html', {'plan': None})


def trainer_edit_diet_plan(request: HttpRequest, plan_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		messages.error(request, 'Access denied.')
		return redirect('home')

	plan = DietPlan.objects.filter(id=plan_id).first()
	if plan is None:
		messages.error(request, 'Diet plan not found.')
		return redirect('trainer.list_diet_plans')

	if request.method == 'POST':
		name = (request.POST.get('name') or '').strip()
		description = (request.POST.get('description') or '').strip()
		diet_type = (request.POST.get('diet_type') or 'balanced').strip()
		daily_calories_str = (request.POST.get('daily_calories') or '').strip()
		notes = (request.POST.get('notes') or '')[:1000].strip()

		protein_pct = float(request.POST.get('macro_ratio_protein') or '30')
		carbs_pct = float(request.POST.get('macro_ratio_carbs') or '45')
		fats_pct = float(request.POST.get('macro_ratio_fats') or '25')

		if not name or not daily_calories_str:
			messages.error(request, 'Name and Calorie Target are required.')
			return redirect('trainer.edit_diet_plan', plan_id=plan.id)

		try:
			daily_calories = int(daily_calories_str)
		except ValueError:
			messages.error(request, 'Daily calories must be a whole number.')
			return redirect('trainer.edit_diet_plan', plan_id=plan.id)

		if abs((protein_pct + carbs_pct + fats_pct) - 100.0) > 0.01:
			messages.error(request, 'Macro percentages must sum to 100%.')
			return redirect('trainer.edit_diet_plan', plan_id=plan.id)

		plan.name = name
		plan.description = description
		plan.diet_type = diet_type
		plan.daily_calories = daily_calories
		plan.macro_ratio_protein = protein_pct / 100.0
		plan.macro_ratio_carbs = carbs_pct / 100.0
		plan.macro_ratio_fats = fats_pct / 100.0
		plan.notes = notes
		plan.save()

		messages.success(request, f'Diet plan "{plan.name}" updated.')
		return redirect('trainer.view_diet_plan', plan_id=plan.id)

	return render(request, 'trainer/diet/form.html', {'plan': plan})


def trainer_delete_diet_plan(request: HttpRequest, plan_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method != 'POST':
		return redirect('trainer.view_diet_plan', plan_id=plan_id)

	plan = DietPlan.objects.filter(id=plan_id).first()
	if plan is None:
		messages.error(request, 'Diet plan not found.')
		return redirect('trainer.list_diet_plans')

	plan.is_active = False
	plan.save()
	messages.info(request, f'Diet plan "{plan.name}" deactivated/deleted.')
	return redirect('trainer.list_diet_plans')


def trainer_add_meal(request: HttpRequest, plan_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		messages.error(request, 'Access denied.')
		return redirect('home')

	plan = DietPlan.objects.filter(id=plan_id).first()
	if plan is None:
		messages.error(request, 'Diet plan not found.')
		return redirect('trainer.list_diet_plans')

	if request.method == 'POST':
		meal_name = (request.POST.get('meal_name') or '').strip()
		meal_type = (request.POST.get('meal_type') or 'Breakfast').strip()
		day_name = (request.POST.get('day_name') or 'Monday').strip()
		calories_str = (request.POST.get('calories') or '').strip()
		protein_g_str = (request.POST.get('protein_g') or '').strip()
		carbs_g_str = (request.POST.get('carbs_g') or '').strip()
		fats_g_str = (request.POST.get('fats_g') or '').strip()
		notes = (request.POST.get('notes') or '')[:500].strip()

		if not meal_name:
			messages.error(request, 'Meal Name is required.')
			return redirect('trainer.view_diet_plan', plan_id=plan.id)

		def _parse_int(val):
			try:
				return int(val) if val else None
			except ValueError:
				return None

		def _parse_float(val):
			try:
				return float(val) if val else None
			except ValueError:
				return None

		MealPlan.objects.create(
			diet_plan=plan,
			day_name=day_name,
			meal_type=meal_type,
			meal_name=meal_name,
			calories=_parse_int(calories_str),
			protein_g=_parse_float(protein_g_str),
			carbs_g=_parse_float(carbs_g_str),
			fats_g=_parse_float(fats_g_str),
			notes=notes,
		)
		messages.success(request, f'Meal "{meal_name}" added to plan.')

	return redirect('trainer.view_diet_plan', plan_id=plan.id)


def trainer_delete_meal(request: HttpRequest, plan_id: int, meal_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method != 'POST':
		return redirect('trainer.view_diet_plan', plan_id=plan_id)

	MealPlan.objects.filter(id=meal_id, diet_plan_id=plan_id).delete()
	messages.info(request, 'Meal deleted from plan.')
	return redirect('trainer.view_diet_plan', plan_id=plan_id)


def trainer_view_diet_plan(request: HttpRequest, plan_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	plan = DietPlan.objects.filter(id=plan_id).first()
	if plan is None:
		messages.error(request, 'Diet plan not found.')
		return redirect('trainer.list_diet_plans')
	meals = list(MealPlan.objects.filter(diet_plan=plan).order_by('day_name', 'meal_type', 'id'))
	return render(request, 'trainer/diet/detail.html', {'plan': plan, 'meals': meals})


def trainer_member_diet(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	diet_assignment = DietAssignment.objects.select_related('diet_plan').filter(member=member, is_active=True).order_by('-assignment_date', '-id').first()
	return render(request, 'trainer/diet/member_diet.html', {'member': member, 'diet_assignment': diet_assignment})


def trainer_assign_diet_to_member(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	plans = list(DietPlan.objects.filter(is_active=True).order_by('name', 'id'))
	if request.method == 'POST':
		plan_id = (request.POST.get('diet_plan_id') or '').strip()
		notes = (request.POST.get('notes') or '')[:1000].strip()
		start_date_str = (request.POST.get('start_date') or '').strip()
		target_end_str = (request.POST.get('target_end_date') or '').strip()

		plan = DietPlan.objects.filter(id=plan_id, is_active=True).first() if plan_id else None
		if plan is None:
			messages.error(request, 'Please select a valid diet plan.')
			return redirect('trainer.assign_diet_to_member', member_id=member.id)

		start_date, target_end_date, date_error = _validate_date_range(start_date_str, target_end_str)
		if date_error:
			messages.error(request, date_error)
			return redirect('trainer.assign_diet_to_member', member_id=member.id)

		try:
			with transaction.atomic():
				previous_diet = DietAssignment.objects.filter(member=member, is_active=True).first()
				previous_diet_name = f'"{previous_diet.diet_plan.name}"' if previous_diet else 'None'

				DietAssignment.objects.filter(member=member, is_active=True).update(is_active=False)

				DietAssignment.objects.create(
					diet_plan=plan,
					member=member,
					trainer=request.user,
					notes=notes,
					is_active=True,
					start_date=start_date,
					target_end_date=target_end_date
				)

			message = f'Diet plan "{plan.name}" assigned.'
			if previous_diet:
				message += f' (Replaced: {previous_diet_name})'
			if start_date and target_end_date:
				message += f' | Duration: {(target_end_date.date() - start_date.date()).days} days'
			messages.success(request, message)

		except Exception as e:
			messages.error(request, f'Error assigning diet: {str(e)}')
			return redirect('trainer.assign_diet_to_member', member_id=member.id)

		return redirect('trainer.member_diet', member_id=member.id)

	return render(request, 'trainer/diet/assign_member.html', {'member': member, 'plans': plans})


def trainer_remove_member_diet(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if request.method != 'POST':
		return redirect('trainer.member_diet', member_id=member_id)
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	DietAssignment.objects.filter(member=member, is_active=True).update(is_active=False)
	messages.info(request, 'Diet removed.')
	return redirect('trainer.member_diet', member_id=member.id)


def trainer_member_progress(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	start_30 = timezone.now() - timedelta(days=30)
	att_qs = Attendance.objects.filter(member=member, check_in_time__gte=start_30)
	attendance_stats = SimpleNamespace(
		total_visits=att_qs.count(),
		avg_duration=int(att_qs.aggregate(avg=Avg('duration_minutes')).get('avg') or 0),
		total_duration=int(att_qs.aggregate(total=Sum('duration_minutes')).get('total') or 0),
	)

	latest_metric = FitnessMetric.objects.filter(member=member).order_by('-metric_date', '-id').first()
	metrics = list(FitnessMetric.objects.filter(member=member).order_by('-metric_date', '-id')[:25])

	weight_trend = None
	start_90 = timezone.localdate() - timedelta(days=90)
	trend_qs = FitnessMetric.objects.filter(member=member, metric_date__gte=start_90).exclude(weight__isnull=True).order_by('metric_date', 'id')
	first = trend_qs.first()
	last = trend_qs.last()
	if first and last and first.weight is not None and last.weight is not None:
		change = float(last.weight) - float(first.weight)
		percent = (change / float(first.weight) * 100) if float(first.weight) else 0.0
		trend = 'flat'
		if change > 0.2:
			trend = 'up'
		elif change < -0.2:
			trend = 'down'
		weight_trend = SimpleNamespace(
			start_weight=float(first.weight),
			current_weight=float(last.weight),
			weight_change=round(change, 2),
			percent_change=round(percent, 1),
			trend=trend,
		)

	return render(
		request,
		"trainer/member_progress.html",
		{
			"member": member,
			"attendance_stats": attendance_stats,
			"latest_metric": latest_metric,
			"weight_trend": weight_trend,
			"metrics": metrics,
		},
	)


def trainer_member_workouts(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = Workout.objects.filter(member=member).select_related('trainer').order_by('-workout_date', '-id')
	paginator = Paginator(qs, 15)
	page_obj = paginator.get_page(page_number)
	pagination = _PaginationAdapter(paginator, page_obj)

	return render(
		request,
		"trainer/member_workouts.html",
		{
			"member": member,
			"workouts": list(page_obj.object_list),
			"pagination": pagination,
		},
	)


def trainer_assign_workout(request: HttpRequest, member_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	if request.method == 'POST':
		workout_date_str = (request.POST.get('workout_date') or '').strip()
		exercise_name = (request.POST.get('exercise_name') or '').strip()
		exercise_category = (request.POST.get('exercise_category') or '').strip()
		intensity = (request.POST.get('intensity') or Workout.Intensity.MODERATE).strip()
		notes = (request.POST.get('notes') or '')[:500].strip()

		if not workout_date_str or not exercise_name or not exercise_category:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('trainer.assign_workout', member_id=member.id)
		try:
			workout_date = timezone.datetime.fromisoformat(workout_date_str).date()
		except ValueError:
			messages.error(request, 'Invalid workout date.')
			return redirect('trainer.assign_workout', member_id=member.id)

		def _to_int(val: str | None):
			v = (val or '').strip()
			return int(v) if v else None

		def _to_float(val: str | None):
			v = (val or '').strip()
			return float(v) if v else None

		Workout.objects.create(
			member=member,
			workout_date=workout_date,
			exercise_name=exercise_name,
			exercise_category=exercise_category,
			sets=_to_int(request.POST.get('sets')),
			reps=_to_int(request.POST.get('reps')),
			weight=_to_float(request.POST.get('weight')),
			duration_minutes=_to_int(request.POST.get('duration_minutes')),
			distance_km=_to_float(request.POST.get('distance_km')),
			intensity=intensity,
			notes=notes,
			trainer=request.user,
			assigned_date=timezone.now(),
		)
		messages.success(request, 'Workout assigned.')
		return redirect('trainer.member_workouts', member_id=member.id)

	return render(request, "trainer/assign_workout_form.html", {"member": member, "workout": None})


def trainer_edit_assigned_workout(request: HttpRequest, member_id: int, workout_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	workout = Workout.objects.filter(id=workout_id, member=member, trainer__isnull=False).first()
	if workout is None:
		messages.error(request, 'Assigned workout not found.')
		return redirect('trainer.member_workouts', member_id=member.id)

	if request.method == 'POST':
		workout_date_str = (request.POST.get('workout_date') or '').strip()
		exercise_name = (request.POST.get('exercise_name') or '').strip()
		exercise_category = (request.POST.get('exercise_category') or '').strip()
		intensity = (request.POST.get('intensity') or Workout.Intensity.MODERATE).strip()
		notes = (request.POST.get('notes') or '')[:500].strip()

		if not workout_date_str or not exercise_name or not exercise_category:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('trainer.edit_assigned_workout', member_id=member.id, workout_id=workout.id)
		try:
			workout_date = timezone.datetime.fromisoformat(workout_date_str).date()
		except ValueError:
			messages.error(request, 'Invalid workout date.')
			return redirect('trainer.edit_assigned_workout', member_id=member.id, workout_id=workout.id)

		def _to_int(val: str | None):
			v = (val or '').strip()
			return int(v) if v else None

		def _to_float(val: str | None):
			v = (val or '').strip()
			return float(v) if v else None

		workout.workout_date = workout_date
		workout.exercise_name = exercise_name
		workout.exercise_category = exercise_category
		workout.sets = _to_int(request.POST.get('sets'))
		workout.reps = _to_int(request.POST.get('reps'))
		workout.weight = _to_float(request.POST.get('weight'))
		workout.duration_minutes = _to_int(request.POST.get('duration_minutes'))
		workout.distance_km = _to_float(request.POST.get('distance_km'))
		workout.intensity = intensity
		workout.notes = notes
		workout.save()

		messages.success(request, 'Assigned workout updated.')
		return redirect('trainer.member_workouts', member_id=member.id)

	return render(request, "trainer/assign_workout_form.html", {"member": member, "workout": workout})


def trainer_delete_assigned_workout(request: HttpRequest, member_id: int, workout_id: int) -> HttpResponse:
	if not _require_trainer_or_admin(request):
		return redirect('auth.login')
	if request.method != 'POST':
		return redirect('trainer.member_workouts', member_id=member_id)

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('trainer.members')
	if not _can_view_member_as_trainer(request, member):
		messages.error(request, 'Access denied.')
		return redirect('trainer.members')

	workout = Workout.objects.filter(id=workout_id, member=member, trainer__isnull=False).first()
	if workout is None:
		messages.error(request, 'Assigned workout not found.')
		return redirect('trainer.member_workouts', member_id=member.id)

	workout.delete()
	messages.info(request, 'Assigned workout deleted.')
	return redirect('trainer.member_workouts', member_id=member.id)


# --- Trainer management (admin) ---

def trainer_create_trainer(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		email = (request.POST.get('email') or '').strip().lower()
		phone_number = (request.POST.get('phone_number') or '').strip()
		max_clients_str = (request.POST.get('max_clients') or '').strip()
		specialization = (request.POST.get('specialization') or '').strip()
		certifications = (request.POST.get('certifications') or '').strip()
		bio = (request.POST.get('bio') or '').strip()

		if not full_name or not email:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('trainer.create_trainer')
		try:
			max_clients = int(max_clients_str or '10')
		except ValueError:
			messages.error(request, 'Invalid max clients value.')
			return redirect('trainer.create_trainer')

		User = get_user_model()
		if User.objects.filter(email__iexact=email).exists():
			messages.error(request, 'A user with that email already exists.')
			return redirect('trainer.create_trainer')

		base_username = (email.split('@', 1)[0] or 'trainer')[:150]
		username = base_username
		suffix = 1
		while User.objects.filter(username__iexact=username).exists():
			suffix += 1
			username = f"{base_username}{suffix}"[:150]

		setup_token = secrets.token_urlsafe(32)
		setup_expiry = timezone.now() + timedelta(hours=24)

		with transaction.atomic():
			user = User.objects.create_user(username=username, email=email, password=secrets.token_urlsafe(16))
			user.full_name = full_name
			user.role = User.Role.TRAINER
			user.is_active = True
			user.setup_token = setup_token
			user.setup_token_expiry = setup_expiry
			user.save(update_fields=['full_name', 'role', 'is_active', 'setup_token', 'setup_token_expiry'])

			trainer = Trainer.objects.create(
				user=user,
				phone_number=phone_number,
				max_clients=max_clients,
				specialization=specialization,
				certifications=certifications,
				bio=bio,
			)

		setup_link = request.build_absolute_uri(reverse('auth.setup_password') + f"?token={setup_token}")
		messages.success(request, 'Trainer created. Copy the setup link from the page.')
		return redirect('trainer.edit_trainer', trainer_id=trainer.id)

	return render(request, 'trainer/edit.html', {'trainer': None})


def trainer_edit_trainer(request: HttpRequest, trainer_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	trainer = Trainer.objects.select_related('user').filter(id=trainer_id).first()
	if trainer is None:
		messages.error(request, 'Trainer not found.')
		return redirect('trainer.list_trainers')

	if request.method == 'POST' and (request.POST.get('full_name') is not None):
		full_name = (request.POST.get('full_name') or '').strip()
		phone_number = (request.POST.get('phone_number') or '').strip()
		max_clients_str = (request.POST.get('max_clients') or '').strip()
		specialization = (request.POST.get('specialization') or '').strip()
		certifications = (request.POST.get('certifications') or '').strip()
		bio = (request.POST.get('bio') or '').strip()

		if not full_name:
			messages.error(request, 'Full name is required.')
			return redirect('trainer.edit_trainer', trainer_id=trainer.id)
		try:
			max_clients = int(max_clients_str or str(trainer.max_clients or 10))
		except ValueError:
			messages.error(request, 'Invalid max clients value.')
			return redirect('trainer.edit_trainer', trainer_id=trainer.id)

		trainer.user.full_name = full_name
		trainer.user.save(update_fields=['full_name'])

		trainer.phone_number = phone_number
		trainer.max_clients = max_clients
		trainer.specialization = specialization
		trainer.certifications = certifications
		trainer.bio = bio
		trainer.save(update_fields=['phone_number', 'max_clients', 'specialization', 'certifications', 'bio'])

		messages.success(request, 'Trainer updated.')
		return redirect('trainer.edit_trainer', trainer_id=trainer.id)

	now = timezone.now()
	has_setup_token = bool(trainer.user.setup_token)
	setup_token_expiry = trainer.user.setup_token_expiry
	is_setup_valid = bool(has_setup_token and setup_token_expiry and setup_token_expiry >= now)
	is_setup_expired = bool(has_setup_token and setup_token_expiry and setup_token_expiry < now)
	setup_link = request.build_absolute_uri(reverse('auth.setup_password') + f"?token={trainer.user.setup_token}") if has_setup_token else ''

	return render(
		request,
		'trainer/edit.html',
		{
			'trainer': trainer,
			'has_setup_token': has_setup_token,
			'is_setup_valid': is_setup_valid,
			'is_setup_expired': is_setup_expired,
			'setup_link': setup_link,
			'setup_token_expiry': setup_token_expiry,
		},
	)


def trainer_resend_setup_link(request: HttpRequest, trainer_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')
	if request.method != 'POST':
		return redirect('trainer.edit_trainer', trainer_id=trainer_id)

	trainer = Trainer.objects.select_related('user').filter(id=trainer_id).first()
	if trainer is None:
		messages.error(request, 'Trainer not found.')
		return redirect('trainer.list_trainers')

	trainer.user.setup_token = secrets.token_urlsafe(32)
	trainer.user.setup_token_expiry = timezone.now() + timedelta(hours=24)
	trainer.user.save(update_fields=['setup_token', 'setup_token_expiry'])
	messages.success(request, 'Setup link regenerated.')
	return redirect('trainer.edit_trainer', trainer_id=trainer.id)


def trainer_delete_trainer(request: HttpRequest, trainer_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')
	if request.method != 'POST':
		return redirect('trainer.list_trainers')

	trainer = Trainer.objects.select_related('user').filter(id=trainer_id).first()
	if trainer is None:
		messages.error(request, 'Trainer not found.')
		return redirect('trainer.list_trainers')

	# Count assigned members before deactivation
	member_count = Member.objects.filter(assigned_trainer=trainer.user, is_active=True, is_approved=True).count()

	trainer.user.is_active = False
	trainer.user.save(update_fields=['is_active'])

	# Invalidate all existing sessions for this user
	from django.contrib.sessions.models import Session
	for session in Session.objects.all():
		session_data = session.get_decoded()
		if session_data.get('_auth_user_id') == str(trainer.user.id):
			session.delete()

	# Show detailed message with member count
	if member_count > 0:
		messages.warning(request, f'Trainer "{trainer.user.full_name}" deactivated. {member_count} member(s) remain assigned—consider reassigning them.')
	else:
		messages.info(request, f'Trainer "{trainer.user.full_name}" deactivated.')

	return redirect('trainer.list_trainers')


def trainer_reactivate_trainer(request: HttpRequest, trainer_id: int) -> HttpResponse:
	"""Reactivate a deactivated trainer account."""
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')
	if request.method != 'POST':
		return redirect('trainer.list_trainers')

	trainer = Trainer.objects.select_related('user').filter(id=trainer_id).first()
	if trainer is None:
		messages.error(request, 'Trainer not found.')
		return redirect('trainer.list_trainers')

	trainer.user.is_active = True
	trainer.user.save(update_fields=['is_active'])
	messages.success(request, f'Trainer "{trainer.user.full_name}" reactivated.')
	return redirect('trainer.list_trainers')


def trainer_manage_assignments(request: HttpRequest, trainer_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	trainer = Trainer.objects.select_related('user').filter(id=trainer_id).first()
	if trainer is None:
		messages.error(request, 'Trainer not found.')
		return redirect('trainer.list_trainers')

	if request.method == 'POST':
		member_id = (request.POST.get('member_id') or '').strip()
		action = (request.POST.get('action') or '').strip()
		member = Member.objects.select_related('user').filter(id=member_id).first() if member_id else None
		if member is None:
			messages.error(request, 'Member not found.')
			return redirect('trainer.manage_assignments', trainer_id=trainer.id)

		if action == 'unassign':
			TrainerAssignment.objects.filter(member=member, is_active=True).update(is_active=False)
			member.assigned_trainer = None
			member.save(update_fields=['assigned_trainer'])
			messages.info(request, 'Member unassigned.')
		elif action == 'assign':
			current_count = Member.objects.filter(assigned_trainer=trainer.user, is_active=True, is_approved=True).count()
			if current_count >= (trainer.max_clients or 0):
				messages.error(request, 'Trainer is at maximum capacity.')
				return redirect('trainer.manage_assignments', trainer_id=trainer.id)

			TrainerAssignment.objects.filter(member=member, is_active=True).update(is_active=False)
			member.assigned_trainer = trainer.user
			member.save(update_fields=['assigned_trainer'])
			today = timezone.localdate()
			TrainerAssignment.objects.create(
				trainer=trainer.user,
				member=member,
				assignment_date=today,
				start_date=today,
				assignment_type=TrainerAssignment.AssignmentType.PRIMARY,
				is_active=True,
			)
			messages.success(request, 'Member assigned.')
		else:
			messages.error(request, 'Invalid action.')

		return redirect('trainer.manage_assignments', trainer_id=trainer.id)

	assignments = list(
		TrainerAssignment.objects.select_related('member', 'member__user')
		.filter(trainer=trainer.user, is_active=True)
		.order_by('member__user__full_name', 'id')
	)

	assigned_member_ids = [a.member_id for a in assignments]
	unassigned_members = list(
		Member.objects.select_related('user')
		.filter(is_active=True, is_approved=True, assigned_trainer__isnull=True)
		.order_by('user__full_name', 'id')
	)

	return render(
		request,
		"trainer/assignments.html",
		{
			"trainer": trainer,
			"assignments": assignments,
			"unassigned_members": unassigned_members,
		},
	)
