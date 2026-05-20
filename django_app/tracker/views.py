from __future__ import annotations

import csv
import io
import base64
from io import BytesIO
from datetime import timedelta
import secrets
from typing import Any
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

import qrcode

from .models import (
	Attendance,
	DietAssignment,
	DietPlan,
	FitnessMetric,
	GuideAssignment,
	MealLog,
	MealPlan,
	Member,
	Trainer,
	TrainerAssignment,
	Workout,
	WorkoutGuide,
	WorkoutTip,
)


def _require_roles(request: HttpRequest, roles: set[str]) -> bool:
	if not request.user.is_authenticated:
		return False
	return getattr(request.user, 'role', None) in roles


def _require_member_access(request: HttpRequest) -> Member | None:
	"""Return member profile if current user is an approved member; otherwise None."""
	if not request.user.is_authenticated:
		return None
	if getattr(request.user, 'role', None) != 'member':
		return None
	member = getattr(request.user, 'member_profile', None)
	if member is None:
		return None
	if not member.is_approved:
		return None
	return member


class _PaginationAdapter:
	def __init__(self, paginator: Paginator, page_obj):
		self.pages = paginator.num_pages
		self.page = page_obj.number
		self.total = paginator.count
		self.has_prev = page_obj.has_previous()
		self.prev_num = page_obj.previous_page_number() if self.has_prev else None
		self.has_next = page_obj.has_next()
		self.next_num = page_obj.next_page_number() if self.has_next else None

	def iter_pages(
		self,
		left_edge: int = 2,
		left_current: int = 2,
		right_current: int = 2,
		right_edge: int = 2,
	):
		last = 0
		for num in range(1, self.pages + 1):
			if (
				num <= left_edge
				or (self.page - left_current - 1 < num < self.page + right_current)
				or num > self.pages - right_edge
			):
				if last + 1 != num:
					yield None
				yield num
				last = num


class _PaginationItemsAdapter(_PaginationAdapter):
	"""Flask-style pagination object with .items for templates."""

	def __init__(self, paginator: Paginator, page_obj, items: list[Any]):
		super().__init__(paginator, page_obj)
		self.items = items


def _qr_data_uri(payload: str) -> str:
	img = qrcode.make(payload)
	buf = BytesIO()
	img.save(buf, format='PNG')
	b64 = base64.b64encode(buf.getvalue()).decode('ascii')
	return f"data:image/png;base64,{b64}"


def home(request: HttpRequest) -> HttpResponse:
	if not (getattr(request, "user", None) is not None and request.user.is_authenticated):
		return render(request, 'landing.html')

	role = getattr(request.user, 'role', 'member')
	if role == 'admin':
		return redirect('admin.dashboard')
	if role == 'trainer':
		return redirect('trainer.dashboard')
	if role == 'staff':
		return redirect('staff.dashboard')

	member = getattr(request.user, 'member_profile', None)
	if role == 'member' and member is not None and not member.is_approved:
		return redirect('auth.pending_status')
	return redirect('member.member_dashboard')


# --- Auth ---

def auth_login(request: HttpRequest) -> HttpResponse:
	if request.user.is_authenticated:
		return redirect('home')

	if request.method == 'POST':
		identifier = (request.POST.get('email') or request.POST.get('username') or '').strip()
		password = request.POST.get('password') or ''

		user = None
		if identifier:
			User = get_user_model()
			user = User.objects.filter(email__iexact=identifier).first() or User.objects.filter(username__iexact=identifier).first()

		auth_user = authenticate(request, username=(user.username if user else identifier), password=password)
		if auth_user is not None:
			login(request, auth_user)
			messages.success(request, 'Logged in successfully.')

			member = getattr(auth_user, 'member_profile', None)
			if auth_user.role == 'member' and member is not None and not member.is_approved:
				return redirect('auth.pending_status')
			return redirect('home')

		messages.error(request, 'Invalid credentials.')
		return redirect('auth.login')

	return render(request, "auth/login.html")


def auth_logout(request: HttpRequest) -> HttpResponse:
	# Template compatibility: some pages POST logout, base nav may GET.
	logout(request)
	messages.info(request, 'Logged out.')
	return redirect('auth.login')


@login_required
def auth_profile(request: HttpRequest) -> HttpResponse:
	return render(
		request,
		"auth/profile.html",
		{
			"member": getattr(request.user, 'member_profile', None),
			"trainer": getattr(request.user, 'trainer_profile', None),
		},
	)


def auth_signup(request: HttpRequest) -> HttpResponse:
	if request.user.is_authenticated:
		return redirect('home')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		email = (request.POST.get('email') or '').strip().lower()
		password = request.POST.get('password') or ''
		confirm_password = request.POST.get('confirm_password') or ''

		if not full_name or not email or not password:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('auth.signup')
		if len(password) < 6:
			messages.error(request, 'Password must be at least 6 characters.')
			return redirect('auth.signup')
		if password != confirm_password:
			messages.error(request, 'Passwords do not match.')
			return redirect('auth.signup')

		User = get_user_model()
		if User.objects.filter(email__iexact=email).exists():
			messages.error(request, 'An account with that email already exists.')
			return redirect('auth.login')

		base_username = (email.split('@', 1)[0] or 'member')[:150]
		username = base_username
		suffix = 1
		while User.objects.filter(username__iexact=username).exists():
			suffix += 1
			candidate = f"{base_username}{suffix}"
			username = candidate[:150]

		with transaction.atomic():
			user = User.objects.create_user(
				username=username,
				email=email,
				password=password,
			)
			user.full_name = full_name
			user.role = User.Role.MEMBER
			user.is_active = True
			user.save(update_fields=['full_name', 'role', 'is_active'])

			today = timezone.localdate()
			Member.objects.create(
				user=user,
				membership_start_date=today,
				membership_expiry_date=today + timedelta(days=30),
				membership_type=Member.MembershipType.MONTHLY,
				is_active=True,
				is_approved=False,
			)

		login(request, user)
		messages.success(request, 'Account created. Awaiting admin approval.')
		return redirect('auth.pending_status')

	return render(request, "auth/signup.html")


def auth_register(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		messages.error(request, 'Please log in first.')
		return redirect('auth.login')
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		username = (request.POST.get('username') or '').strip()
		email = (request.POST.get('email') or '').strip().lower()
		role = (request.POST.get('role') or 'member').strip()
		password = request.POST.get('password') or ''
		confirm_password = request.POST.get('confirm_password') or ''

		if not full_name or not username or not email or not password:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('auth.register')
		if len(password) < 6:
			messages.error(request, 'Password must be at least 6 characters.')
			return redirect('auth.register')
		if password != confirm_password:
			messages.error(request, 'Passwords do not match.')
			return redirect('auth.register')

		User = get_user_model()
		if User.objects.filter(username__iexact=username).exists():
			messages.error(request, 'That username is already taken.')
			return redirect('auth.register')
		if User.objects.filter(email__iexact=email).exists():
			messages.error(request, 'That email is already in use.')
			return redirect('auth.register')

		valid_roles = {c[0] for c in getattr(User, 'Role').choices}
		if role not in valid_roles:
			messages.error(request, 'Invalid role selected.')
			return redirect('auth.register')

		with transaction.atomic():
			new_user = User.objects.create_user(username=username, email=email, password=password)
			new_user.full_name = full_name
			new_user.role = role
			new_user.is_active = True
			new_user.save(update_fields=['full_name', 'role', 'is_active'])

			if role == User.Role.TRAINER:
				Trainer.objects.create(user=new_user)
			elif role == User.Role.MEMBER:
				today = timezone.localdate()
				Member.objects.create(
					user=new_user,
					membership_start_date=today,
					membership_expiry_date=today + timedelta(days=30),
					membership_type=Member.MembershipType.MONTHLY,
					is_active=True,
					is_approved=True,
					approval_date=timezone.now(),
				)

		messages.success(request, f"Created {role} user: {username}")
		return redirect('admin.dashboard')

	return render(request, "auth/register.html")


def auth_pending_status(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')

	member = getattr(request.user, 'member_profile', None)
	if getattr(request.user, 'role', None) != 'member':
		messages.info(request, 'Pending approval applies to member accounts only.')
		return redirect('home')
	if member is None:
		# Safety net for legacy data.
		today = timezone.localdate()
		member = Member.objects.create(
			user=request.user,
			membership_start_date=today,
			membership_expiry_date=today + timedelta(days=30),
			membership_type=Member.MembershipType.MONTHLY,
			is_active=True,
			is_approved=False,
		)
	if member.is_approved:
		return redirect('home')
	return render(request, "auth/pending_status.html", {"member": member})


def auth_setup_password(request: HttpRequest) -> HttpResponse:
	User = get_user_model()
	setup_token = (request.GET.get('token') or '').strip()
	user = None
	if setup_token:
		user = User.objects.filter(setup_token=setup_token).first()

	if request.method == 'POST':
		password = request.POST.get('password') or ''
		confirm_password = request.POST.get('confirm_password') or ''

		if user is None:
			messages.error(request, 'Invalid or expired setup link.')
			return redirect('auth.login')
		if user.setup_token_expiry and user.setup_token_expiry < timezone.now():
			messages.error(request, 'This setup link has expired. Contact your administrator.')
			return redirect('auth.login')
		if len(password) < 6:
			messages.error(request, 'Password must be at least 6 characters.')
			return redirect(request.path + f"?token={setup_token}")
		if password != confirm_password:
			messages.error(request, 'Passwords do not match.')
			return redirect(request.path + f"?token={setup_token}")

		user.set_password(password)
		user.setup_token = None
		user.setup_token_expiry = None
		user.is_active = True
		user.save(update_fields=['password', 'setup_token', 'setup_token_expiry', 'is_active'])

		login(request, user)
		messages.success(request, 'Password set successfully.')
		return redirect('home')

	if user is None:
		messages.error(request, 'Invalid or expired setup link.')
		return redirect('auth.login')
	if user.setup_token_expiry and user.setup_token_expiry < timezone.now():
		messages.error(request, 'This setup link has expired. Contact your administrator.')
		return redirect('auth.login')

	return render(request, "auth/setup_password.html")


# --- Admin/Staff ---

def admin_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
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

	return render(request, "admin/dashboard.html", {"stats": stats})


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

	return render(
		request,
		"admin/pending_approvals.html",
		{
			"pending_members": list(page_obj.object_list),
			"search": search,
			"pagination": pagination,
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

	# Prefetch tips via related name - template can access via guide.tips.all
	tips = list(guide.tips.all().order_by('order', 'id'))
	return render(request, 'admin/guides/review.html', {'guide': guide, 'tips': tips})


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
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
		return redirect('home')
	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	member.is_approved = True
	member.approval_date = timezone.now()
	member.save(update_fields=['is_approved', 'approval_date'])
	messages.success(request, f"Approved member: {member.user.full_name}")
	return redirect('member.list_members')


@login_required
def admin_reject_member(request: HttpRequest, member_id: int) -> HttpResponse:
	if getattr(request.user, 'role', None) != 'admin':
		messages.error(request, 'Admin access required.')
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


# --- Members ---

def member_list_members(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	search = (request.GET.get('search') or '').strip()
	status = (request.GET.get('status') or 'all').strip()
	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = Member.objects.select_related('user').all().order_by('user__full_name', 'id')
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
		phone_number = (request.POST.get('phone_number') or '').strip()
		date_of_birth_str = (request.POST.get('date_of_birth') or '').strip()
		gender = (request.POST.get('gender') or '').strip()
		membership_type = (request.POST.get('membership_type') or 'monthly').strip()
		membership_start_str = (request.POST.get('membership_start_date') or '').strip()
		membership_expiry_str = (request.POST.get('membership_expiry_date') or '').strip()
		notes = (request.POST.get('notes') or '').strip()

		if not full_name or not email or not membership_start_str or not membership_expiry_str:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.create_member')

		try:
			date_of_birth = timezone.datetime.fromisoformat(date_of_birth_str).date() if date_of_birth_str else None
			membership_start = timezone.datetime.fromisoformat(membership_start_str).date()
			membership_expiry = timezone.datetime.fromisoformat(membership_expiry_str).date()
		except ValueError:
			messages.error(request, 'Invalid date format.')
			return redirect('member.create_member')

		User = get_user_model()
		if User.objects.filter(email__iexact=email).exists():
			messages.error(request, 'A user with that email already exists.')
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

			member = Member.objects.create(
				user=user,
				phone_number=phone_number,
				date_of_birth=date_of_birth,
				gender=gender,
				membership_type=membership_type,
				membership_start_date=membership_start,
				membership_expiry_date=membership_expiry,
				notes=notes,
				is_active=True,
				is_approved=True,
				approval_date=timezone.now(),
			)

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
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	trainer_assignment = (
		TrainerAssignment.objects.select_related('trainer')
		.filter(member=member, is_active=True)
		.order_by('-start_date', '-id')
		.first()
	)
	trainers = Trainer.objects.select_related('user').all().order_by('user__full_name', 'id')

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
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('member.list_members')

	if request.method == 'POST':
		full_name = (request.POST.get('full_name') or '').strip()
		phone_number = (request.POST.get('phone_number') or '').strip()
		date_of_birth_str = (request.POST.get('date_of_birth') or '').strip()
		gender = (request.POST.get('gender') or '').strip()
		membership_type = (request.POST.get('membership_type') or member.membership_type).strip()
		membership_start_str = (request.POST.get('membership_start_date') or '').strip()
		membership_expiry_str = (request.POST.get('membership_expiry_date') or '').strip()
		notes = (request.POST.get('notes') or '').strip()

		if not full_name or not membership_start_str or not membership_expiry_str:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.edit_member', member_id=member.id)

		try:
			date_of_birth = timezone.datetime.fromisoformat(date_of_birth_str).date() if date_of_birth_str else None
			membership_start = timezone.datetime.fromisoformat(membership_start_str).date()
			membership_expiry = timezone.datetime.fromisoformat(membership_expiry_str).date()
		except ValueError:
			messages.error(request, 'Invalid date format.')
			return redirect('member.edit_member', member_id=member.id)

		member.user.full_name = full_name
		member.user.save(update_fields=['full_name'])

		member.phone_number = phone_number
		member.date_of_birth = date_of_birth
		member.gender = gender
		member.membership_type = membership_type
		member.membership_start_date = membership_start
		member.membership_expiry_date = membership_expiry
		member.notes = notes
		member.save()

		messages.success(request, 'Member updated.')
		return redirect('member.view_member', member_id=member.id)

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


# --- Member Dashboard ---

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
		phone_number = (request.POST.get('phone_number') or '').strip()
		gender = (request.POST.get('gender') or '').strip()
		dob_str = (request.POST.get('date_of_birth') or '').strip()
		date_of_birth = None
		if dob_str:
			try:
				date_of_birth = timezone.datetime.fromisoformat(dob_str).date()
			except ValueError:
				messages.error(request, 'Invalid date of birth.')
				return redirect('member.edit_member_profile')

		if not full_name or not email:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.edit_member_profile')

		User = get_user_model()
		if User.objects.filter(email__iexact=email).exclude(id=request.user.id).exists():
			messages.error(request, 'That email is already in use.')
			return redirect('member.edit_member_profile')

		request.user.full_name = full_name
		request.user.email = email
		request.user.save(update_fields=['full_name', 'email'])

		member.phone_number = phone_number
		member.gender = gender
		member.date_of_birth = date_of_birth
		member.save(update_fields=['phone_number', 'gender', 'date_of_birth'])

		messages.success(request, 'Profile updated.')
		return redirect('member.member_profile')

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
		intensity = (request.POST.get('intensity') or Workout.Intensity.MODERATE).strip()
		notes = (request.POST.get('notes') or '').strip()

		if not workout_date_str or not exercise_name or not exercise_category:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.create_workout')
		try:
			workout_date = timezone.datetime.fromisoformat(workout_date_str).date()
		except ValueError:
			messages.error(request, 'Invalid workout date.')
			return redirect('member.create_workout')

		def _to_int(val: str | None):
			v = (val or '').strip()
			return int(v) if v else None

		def _to_float(val: str | None):
			v = (val or '').strip()
			return float(v) if v else None

		workout = Workout.objects.create(
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
		)

		messages.success(request, 'Workout logged.')
		return redirect('member.list_workouts')

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
		intensity = (request.POST.get('intensity') or Workout.Intensity.MODERATE).strip()
		notes = (request.POST.get('notes') or '').strip()

		if not workout_date_str or not exercise_name or not exercise_category:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('member.edit_workout', workout_id=workout.id)
		try:
			workout_date = timezone.datetime.fromisoformat(workout_date_str).date()
		except ValueError:
			messages.error(request, 'Invalid workout date.')
			return redirect('member.edit_workout', workout_id=workout.id)

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

		messages.success(request, 'Workout updated.')
		return redirect('member.list_workouts')

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
		notes = (request.POST.get('notes') or '').strip()

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
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')

	items = list(WorkoutGuide.objects.filter(status=WorkoutGuide.Status.APPROVED).order_by('category', 'name', 'id'))
	guides = SimpleNamespace(items=items)
	return render(request, "member_dashboard/guides_library.html", {"guides": guides})


def member_request_guide_assignment(request: HttpRequest, guide_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	member = _require_member_access(request)
	if member is None:
		if getattr(request.user, 'role', None) == 'member':
			return redirect('auth.pending_status')
		messages.error(request, 'Access denied.')
		return redirect('home')
	if request.method != 'POST':
		return redirect('member.browse_guides_library')

	guide = WorkoutGuide.objects.filter(id=guide_id).first()
	if guide is None:
		messages.error(request, 'Guide not found.')
		return redirect('member.browse_guides_library')

	# No dedicated "request" model exists yet; acknowledge the action.
	messages.success(request, 'Request submitted. Your trainer will review it.')
	return redirect('member.browse_guides_library')


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

	# If no assignment, only allow viewing if guide is approved
	if not assignment and guide.status != WorkoutGuide.Status.APPROVED:
		messages.error(request, 'This guide is not yet approved.')
		return redirect('member.member_programs')

	progress = assignment.calculate_progress() if assignment else 0
	tips = list(WorkoutTip.objects.filter(guide=guide).order_by('order', 'id'))
	logged_workouts = list(Workout.objects.filter(member=member, guide=guide).order_by('-workout_date', '-id')[:20]) if assignment else []

	return render(
		request,
		"member_dashboard/guide_detail.html",
		{
			"guide": guide,
			"assignment": assignment,
			"progress": progress,
			"tips": tips,
			"logged_workouts": logged_workouts,
		},
	)


# --- Attendance ---

def attendance_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	today = timezone.localdate()
	start_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	end_of_day = start_of_day + timedelta(days=1)

	members = list(
		Member.objects.select_related('user')
		.filter(is_active=True, is_approved=True)
		.order_by('user__full_name', 'id')
	)

	active_members = list(
		Attendance.objects.select_related('member', 'member__user')
		.filter(check_in_time__gte=start_of_day, check_in_time__lt=end_of_day, check_out_time__isnull=True)
		.order_by('-check_in_time')
	)

	completed_sessions = list(
		Attendance.objects.select_related('member', 'member__user')
		.filter(check_out_time__gte=start_of_day, check_out_time__lt=end_of_day)
		.order_by('-check_out_time')[:15]
	)

	qr_payload = f"GymTrackPro Attendance Check-In {today.isoformat()}"
	qr_image = _qr_data_uri(qr_payload)
	countdown = {"minutes": 23, "seconds": 59}

	return render(
		request,
		"attendance/dashboard.html",
		{
			"qr_image": qr_image,
			"countdown": countdown,
			"members": members,
			"active_members": active_members,
			"completed_sessions": completed_sessions,
		},
	)


def attendance_check_in(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	members = list(
		Member.objects.select_related('user')
		.filter(is_active=True, is_approved=True)
		.order_by('user__full_name', 'id')
	)

	if request.method == 'POST':
		member_id = (request.POST.get('member_id') or '').strip()
		member = Member.objects.select_related('user').filter(id=member_id).first() if member_id else None
		if member is None:
			messages.error(request, 'Please select a valid member.')
			return redirect('attendance_routes.check_in')

		# Prevent duplicate active sessions
		already_active = Attendance.objects.filter(member=member, check_out_time__isnull=True).exists()
		if already_active:
			messages.info(request, f"{member.user.full_name} is already checked in.")
			return redirect('attendance_routes.dashboard')

		Attendance.objects.create(member=member, check_in_time=timezone.now())
		messages.success(request, f"Checked in: {member.user.full_name}")
		return redirect('attendance_routes.dashboard')

	today = timezone.localdate()
	qr_payload = f"GymTrackPro Attendance Check-In {today.isoformat()}"
	qr_image = _qr_data_uri(qr_payload)
	countdown = {"minutes": 23, "seconds": 59}
	return render(request, "attendance/check_in.html", {"qr_image": qr_image, "countdown": countdown, "members": members})


def attendance_history(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	members = list(
		Member.objects.select_related('user')
		.filter(is_active=True, is_approved=True)
		.order_by('user__full_name', 'id')
	)

	selected_member_id = request.GET.get('member_id') or ''
	selected_date = (request.GET.get('date') or '').strip()
	try:
		page_number = int(request.GET.get('page') or '1')
	except ValueError:
		page_number = 1

	qs = Attendance.objects.select_related('member', 'member__user').all().order_by('-check_in_time', '-id')
	if selected_member_id:
		qs = qs.filter(member_id=selected_member_id)
	if selected_date:
		try:
			day = timezone.datetime.fromisoformat(selected_date).date()
			start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
			end = start + timedelta(days=1)
			qs = qs.filter(check_in_time__gte=start, check_in_time__lt=end)
		except ValueError:
			messages.error(request, 'Invalid date filter.')
			return redirect('attendance_routes.history')

	paginator = Paginator(qs, 15)
	page_obj = paginator.get_page(page_number)
	pagination = _PaginationAdapter(paginator, page_obj)

	selected_member_int = int(selected_member_id) if selected_member_id.isdigit() else None
	return render(
		request,
		"attendance/history.html",
		{
			"members": members,
			"attendance_records": list(page_obj.object_list),
			"pagination": pagination,
			"selected_member_id": selected_member_int,
			"selected_date": selected_date,
		},
	)


def attendance_stats(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	now = timezone.now()
	today = timezone.localdate()
	start_today = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	start_week = now - timedelta(days=7)
	start_month = now - timedelta(days=30)

	stats = {
		"today_checkins": Attendance.objects.filter(check_in_time__gte=start_today).count(),
		"week_checkins": Attendance.objects.filter(check_in_time__gte=start_week).count(),
		"month_checkins": Attendance.objects.filter(check_in_time__gte=start_month).count(),
	}

	# Inactive members: no check-in in last 30 days
	active_member_ids = set(
		Attendance.objects.filter(check_in_time__gte=start_month).values_list('member_id', flat=True).distinct()
	)
	inactive_qs = (
		Member.objects.select_related('user')
		.filter(is_active=True, is_approved=True)
		.exclude(id__in=active_member_ids)
		.order_by('user__full_name', 'id')
	)
	stats["inactive_members"] = inactive_qs.count()
	stats["inactive_members_list"] = list(inactive_qs[:10])

	return render(request, "attendance/stats.html", {"stats": stats})


@login_required
def attendance_check_out(request: HttpRequest, attendance_id: int) -> HttpResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	record = Attendance.objects.select_related('member', 'member__user').filter(id=attendance_id).first()
	if record is None:
		messages.error(request, 'Attendance record not found.')
		return redirect('attendance_routes.history')
	if record.check_out_time:
		messages.info(request, 'Already checked out.')
		return redirect('attendance_routes.history')

	now_dt = timezone.now()
	record.check_out_time = now_dt
	duration = int((now_dt - record.check_in_time).total_seconds() // 60)
	record.duration_minutes = max(duration, 0)
	record.save(update_fields=['check_out_time', 'duration_minutes'])
	messages.success(request, f"Checked out: {record.member.user.full_name}")
	return redirect('attendance_routes.history')


@login_required
def attendance_api_active_today(request: HttpRequest) -> JsonResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		return JsonResponse({"success": False, "error": "Access denied"}, status=403)

	today = timezone.localdate()
	start_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	end_of_day = start_of_day + timedelta(days=1)

	active_qs = (
		Attendance.objects.select_related('member', 'member__user')
		.filter(check_in_time__gte=start_of_day, check_in_time__lt=end_of_day, check_out_time__isnull=True)
		.order_by('-check_in_time')
	)

	now_dt = timezone.now()
	active_members = []
	for rec in active_qs:
		duration_so_far = int((now_dt - rec.check_in_time).total_seconds() // 60)
		active_members.append(
			{
				"id": rec.id,
				"member_name": rec.member.user.full_name,
				"check_in_time": rec.check_in_time.isoformat(),
				"duration_so_far": max(duration_so_far, 0),
			}
		)

	return JsonResponse({"success": True, "active_members": active_members})


@login_required
@csrf_exempt
def attendance_api_check_out(request: HttpRequest, attendance_id: int) -> JsonResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		return JsonResponse({"success": False, "error": "Access denied"}, status=403)
	if request.method != 'POST':
		return JsonResponse({"success": False, "error": "POST required"}, status=405)

	record = Attendance.objects.select_related('member', 'member__user').filter(id=attendance_id).first()
	if record is None:
		return JsonResponse({"success": False, "error": "Record not found"}, status=404)
	if record.check_out_time:
		return JsonResponse({"success": True, "message": "Already checked out"})

	now_dt = timezone.now()
	record.check_out_time = now_dt
	duration = int((now_dt - record.check_in_time).total_seconds() // 60)
	record.duration_minutes = max(duration, 0)
	record.save(update_fields=['check_out_time', 'duration_minutes'])
	return JsonResponse({"success": True, "message": f"Checked out: {record.member.user.full_name}"})


@login_required
def attendance_api_stats(request: HttpRequest) -> JsonResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		return JsonResponse({"success": False, "error": "Access denied"}, status=403)

	today = timezone.localdate()
	start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	end = start + timedelta(days=1)

	qs = Attendance.objects.filter(check_in_time__gte=start, check_in_time__lt=end)
	# Build 24-hour buckets
	buckets = {f"{h:02d}": 0 for h in range(24)}
	for dt in qs.values_list('check_in_time', flat=True):
		buckets[f"{dt.hour:02d}"] += 1
	return JsonResponse(buckets)


# --- Fitness ---

def fitness_metrics(request: HttpRequest) -> HttpResponse:
	return render(request, "fitness/metrics.html")


# --- Trainer ---

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

	# Inactive 30+ days (no check-ins in 30 days)
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

	qs = Trainer.objects.select_related('user').all().order_by('user__full_name', 'id')
	if search:
		qs = qs.filter(Q(user__full_name__icontains=search) | Q(user__email__icontains=search))

	paginator = Paginator(qs, 10)
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

	return render(request, "trainer/guides/list.html", {"guides": guides})


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

	return render(request, "trainer/diet/list.html", {"plans": plans})


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
		notes = (request.POST.get('notes') or '').strip()

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
		notes = (request.POST.get('notes') or '').strip()

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

	trainer.user.is_active = False
	trainer.user.save(update_fields=['is_active'])
	messages.info(request, 'Trainer deactivated.')
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
		.filter(is_active=True, is_approved=True)
		.exclude(id__in=assigned_member_ids)
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


# --- Guides CRUD / assignment ---

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
		guide.save()
		messages.success(request, 'Guide updated.')
		return redirect('trainer.edit_guide', guide_id=guide.id)

	# Template expects guide.tips
	setattr(guide, 'tips', list(guide.tips.all().order_by('exercise_name', 'id')))
	return render(request, 'trainer/guides/form.html', {'guide': guide})


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
		notes = (request.POST.get('notes') or '').strip()
		start_date_str = (request.POST.get('start_date') or '').strip()
		target_completion_str = (request.POST.get('target_completion_date') or '').strip()

		guide = WorkoutGuide.objects.filter(id=guide_id, status=WorkoutGuide.Status.APPROVED).first() if guide_id else None
		if guide is None:
			messages.error(request, 'Please select a valid guide.')
			return redirect('trainer.assign_guide_to_member', member_id=member.id)

		# Parse dates if provided
		from datetime import datetime
		start_date = None
		target_completion_date = None
		try:
			if start_date_str:
				start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
			if target_completion_str:
				target_completion_date = datetime.strptime(target_completion_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
		except (ValueError, TypeError):
			messages.warning(request, 'Invalid date format. Dates will be left empty.')

		GuideAssignment.objects.create(
			guide=guide,
			member=member,
			trainer=request.user,
			notes=notes,
			is_active=True,
			start_date=start_date,
			target_completion_date=target_completion_date
		)
		messages.success(request, 'Guide assigned.')
		return redirect('trainer.member_guides', member_id=member.id)

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


# --- Diets / assignment ---

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
		notes = (request.POST.get('notes') or '').strip()
		start_date_str = (request.POST.get('start_date') or '').strip()
		target_end_str = (request.POST.get('target_end_date') or '').strip()

		plan = DietPlan.objects.filter(id=plan_id, is_active=True).first() if plan_id else None
		if plan is None:
			messages.error(request, 'Please select a valid diet plan.')
			return redirect('trainer.assign_diet_to_member', member_id=member.id)

		# Parse dates if provided
		from datetime import datetime
		start_date = None
		target_end_date = None
		try:
			if start_date_str:
				start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
			if target_end_str:
				target_end_date = datetime.strptime(target_end_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
		except (ValueError, TypeError):
			messages.warning(request, 'Invalid date format. Dates will be left empty.')

		with transaction.atomic():
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
		messages.success(request, 'Diet assigned.')
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


# --- Staff ---

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
	qs = User.objects.filter(role=User.Role.STAFF).order_by('full_name', 'id')
	if search:
		qs = qs.filter(Q(full_name__icontains=search) | Q(email__icontains=search) | Q(username__icontains=search))

	paginator = Paginator(qs, 10)
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
	if getattr(request.user, 'role', None) != 'staff':
		messages.error(request, 'Staff access required.')
		return redirect('home')
	return render(request, 'staff/dashboard.html')


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
			# Many templates gate staff UI on is_staff.
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
	messages.info(request, 'Staff member deactivated.')
	return redirect('staff.list_staff')


# --- Reports ---

def reports_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	try:
		days = int(request.GET.get('days') or '7')
	except ValueError:
		days = 7
	if days not in {7, 30, 90}:
		days = 7

	now_dt = timezone.now()
	today = timezone.localdate()
	window_start = now_dt - timedelta(days=days)

	# Membership stats
	total_members = Member.objects.filter(is_approved=True, is_active=True, membership_expiry_date__gte=today).count()
	expiring_soon = Member.objects.filter(
		is_approved=True,
		is_active=True,
		membership_expiry_date__gte=today,
		membership_expiry_date__lte=today + timedelta(days=7),
	).count()
	expired = Member.objects.filter(is_approved=True).filter(Q(is_active=False) | Q(membership_expiry_date__lt=today)).count()

	# Attendance stats
	active_today = Attendance.objects.filter(check_in_time__date=today).count()
	total_visits = Attendance.objects.filter(check_in_time__gte=window_start).count()
	avg_daily_visits = round((total_visits / float(days)) if days else 0.0, 1)

	# Fitness stats
	fitness_participants = (
		FitnessMetric.objects.values_list('member_id', flat=True).distinct().count()
		if FitnessMetric.objects.exists()
		else 0
	)

	# Top attendance in window
	rows = list(
		Attendance.objects.filter(check_in_time__gte=window_start)
		.values('member_id', 'member__user__full_name')
		.annotate(visits=Count('id'))
		.order_by('-visits')[:10]
	)
	member_visits_base = [(r['member_id'], r['member__user__full_name'] or '', int(r['visits'] or 0)) for r in rows]
	member_visits = list(enumerate(member_visits_base, start=1))

	return render(
		request,
		"reports/dashboard.html",
		{
			"days": days,
			"total_members": total_members,
			"active_today": active_today,
			"total_visits": total_visits,
			"avg_daily_visits": avg_daily_visits,
			"expiring_soon": expiring_soon,
			"expired": expired,
			"fitness_participants": fitness_participants,
			"member_visits": member_visits,
		},
	)


def reports_daily_attendance(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	today = timezone.localdate()
	start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	end = start + timedelta(days=1)

	qs = (
		Attendance.objects.select_related('member', 'member__user')
		.filter(check_in_time__gte=start, check_in_time__lt=end)
		.order_by('-check_in_time', '-id')
	)
	records = list(qs)
	total_visits = len(records)
	still_checked_in = sum(1 for r in records if r.check_out_time is None)
	now_dt = timezone.now()

	if (request.GET.get('format') or '').lower() == 'csv':
		buf = io.StringIO()
		writer = csv.writer(buf)
		writer.writerow(['Member Name', 'Email', 'Check-in', 'Check-out', 'Duration (min)', 'Status'])
		for r in records:
			check_in = r.check_in_time
			check_out = r.check_out_time
			if check_in and check_out:
				duration = int((check_out - check_in).total_seconds() // 60)
				status = 'Completed'
			elif check_in and not check_out:
				duration = int((now_dt - check_in).total_seconds() // 60)
				status = 'In Gym'
			else:
				duration = ''
				status = ''
			writer.writerow(
				[
					r.member.user.full_name,
					r.member.user.email,
					check_in.isoformat() if check_in else '',
					check_out.isoformat() if check_out else '',
					max(duration, 0) if duration != '' else '',
					status,
				]
			)

		resp = HttpResponse(buf.getvalue(), content_type='text/csv')
		resp['Content-Disposition'] = f'attachment; filename="daily_attendance_{today.isoformat()}.csv"'
		return resp

	return render(
		request,
		"reports/daily_attendance.html",
		{
			"today": today,
			"now": now_dt,
			"records": records,
			"total_visits": total_visits,
			"still_checked_in": still_checked_in,
		},
	)


def reports_attendance_report(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	now_dt = timezone.now()
	members = list(Member.objects.select_related('user').order_by('user__full_name', 'id'))
	member_obj = None
	records: list[Attendance] = []
	start_date = ''
	end_date = ''

	if request.method == 'POST':
		member_id = (request.POST.get('member_id') or '').strip()
		start_date = (request.POST.get('start_date') or '').strip()
		end_date = (request.POST.get('end_date') or '').strip()
		fmt = (request.POST.get('format') or 'html').strip().lower()

		try:
			start_day = timezone.datetime.fromisoformat(start_date).date() if start_date else (timezone.localdate() - timedelta(days=30))
		except ValueError:
			messages.error(request, 'Invalid start date.')
			return redirect('reports.attendance_report')
		try:
			end_day = timezone.datetime.fromisoformat(end_date).date() if end_date else timezone.localdate()
		except ValueError:
			messages.error(request, 'Invalid end date.')
			return redirect('reports.attendance_report')

		start_dt = timezone.make_aware(timezone.datetime.combine(start_day, timezone.datetime.min.time()))
		end_dt = timezone.make_aware(timezone.datetime.combine(end_day, timezone.datetime.max.time()))

		qs = Attendance.objects.select_related('member', 'member__user').filter(check_in_time__gte=start_dt, check_in_time__lte=end_dt).order_by('-check_in_time', '-id')
		if member_id and member_id.isdigit():
			member_obj = Member.objects.select_related('user').filter(id=int(member_id)).first()
			if member_obj:
				qs = qs.filter(member=member_obj)

		records = list(qs)
		# Fill duration_minutes for display when missing
		for r in records:
			if r.duration_minutes is None and r.check_in_time and r.check_out_time:
				r.duration_minutes = int((r.check_out_time - r.check_in_time).total_seconds() // 60)

		if fmt == 'csv':
			buf = io.StringIO()
			writer = csv.writer(buf)
			writer.writerow(['Member Name', 'Email', 'Date', 'Check-in', 'Check-out', 'Duration (min)'])
			for r in records:
				writer.writerow(
					[
						r.member.user.full_name,
						r.member.user.email,
						r.check_in_time.date().isoformat() if r.check_in_time else '',
						r.check_in_time.strftime('%H:%M') if r.check_in_time else '',
						r.check_out_time.strftime('%H:%M') if r.check_out_time else '',
						r.duration_minutes or '',
					]
				)
			resp = HttpResponse(buf.getvalue(), content_type='text/csv')
			resp['Content-Disposition'] = 'attachment; filename="attendance_report.csv"'
			return resp

	return render(
		request,
		"reports/attendance_report.html",
		{
			"members": members,
			"member": member_obj,
			"records": records,
			"start_date": start_date,
			"end_date": end_date,
			"now": now_dt,
		},
	)


def reports_fitness_report(request: HttpRequest, member_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('reports.dashboard')

	metrics = list(FitnessMetric.objects.filter(member=member).order_by('-metric_date', '-id'))
	weight_trend = None
	bmi_trend = None
	if len(metrics) >= 2:
		latest = metrics[0]
		oldest = metrics[-1]
		if latest.weight is not None and oldest.weight is not None and oldest.weight != 0:
			change = round(latest.weight - oldest.weight, 2)
			pct = round((change / oldest.weight) * 100.0, 1)
			weight_trend = {"weight_change": change, "percent_change": pct}
		if latest.bmi is not None and oldest.bmi is not None:
			bmi_trend = {"start_bmi": round(oldest.bmi, 2), "end_bmi": round(latest.bmi, 2), "change": round(latest.bmi - oldest.bmi, 2)}

	return render(
		request,
		"reports/fitness_report.html",
		{
			"member": member,
			"metrics": metrics,
			"weight_trend": weight_trend,
			"bmi_trend": bmi_trend,
			"now": timezone.localdate(),
		},
	)


def reports_fitness_export(request: HttpRequest, member_id: int) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('reports.dashboard')

	metrics = list(FitnessMetric.objects.filter(member=member).order_by('-metric_date', '-id'))
	buf = io.StringIO()
	writer = csv.writer(buf)
	writer.writerow(['Date', 'Weight (kg)', 'Height (cm)', 'BMI', 'Chest', 'Waist', 'Hips', 'Bicep', 'Thigh', 'Body Fat %', 'Muscle Mass', 'Notes'])
	for m in metrics:
		writer.writerow(
			[
				m.metric_date.isoformat() if m.metric_date else '',
				m.weight if m.weight is not None else '',
				m.height if m.height is not None else '',
				m.bmi if m.bmi is not None else '',
				m.chest if m.chest is not None else '',
				m.waist if m.waist is not None else '',
				m.hips if m.hips is not None else '',
				m.bicep if m.bicep is not None else '',
				m.thigh if m.thigh is not None else '',
				m.body_fat_percentage if m.body_fat_percentage is not None else '',
				m.muscle_mass if m.muscle_mass is not None else '',
				m.notes or '',
			]
		)
	resp = HttpResponse(buf.getvalue(), content_type='text/csv')
	resp['Content-Disposition'] = f'attachment; filename="fitness_report_{member.id}.csv"'
	return resp


def api_health(request: HttpRequest) -> JsonResponse:
	return JsonResponse({"status": "ok"})
