from __future__ import annotations

from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from tracker.models import Member, Trainer
from .base import _require_roles, _safe_next_redirect


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

		# Check if user exists but account is deactivated
		if user and not user.is_active:
			messages.error(request, 'Your account has been deactivated. Please contact the administrator.')
		else:
			messages.error(request, 'Invalid username or password.')
		return redirect('auth.login')

	return render(request, "auth/login.html")


def auth_logout(request: HttpRequest) -> HttpResponse:
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
		confirm_password = request.POST.get('confirm_password') or request.POST.get('password_confirm') or ''
		plan_choice = (request.POST.get('plan') or 'monthly').strip().lower()

		if not full_name or not email or not password:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('auth.signup')
		if len(password) < 6:
			messages.error(request, 'Password must be at least 6 characters.')
			return redirect('auth.signup')
		if password != confirm_password:
			messages.error(request, 'Passwords do not match.')
			return redirect('auth.signup')

		valid_plans = {Member.MembershipType.MONTHLY, Member.MembershipType.QUARTERLY, Member.MembershipType.ANNUAL}
		if plan_choice not in valid_plans:
			plan_choice = 'monthly'

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
			days_to_add = 30
			if plan_choice == Member.MembershipType.QUARTERLY:
				days_to_add = 90
			elif plan_choice == Member.MembershipType.ANNUAL:
				days_to_add = 365

			Member.objects.create(
				user=user,
				membership_start_date=today,
				membership_expiry_date=today + timedelta(days=days_to_add),
				membership_type=plan_choice,
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
		confirm_password = request.POST.get('confirm_password') or request.POST.get('password_confirm') or ''

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
			if role in {User.Role.STAFF, User.Role.ADMIN}:
				new_user.is_staff = True
			new_user.save(update_fields=['full_name', 'role', 'is_active', 'is_staff'])

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
		confirm_password = request.POST.get('confirm_password') or request.POST.get('password_confirm') or ''

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
