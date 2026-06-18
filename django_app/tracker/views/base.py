from __future__ import annotations

import base64
from functools import wraps
from io import BytesIO
from typing import Any
from datetime import datetime, timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
import qrcode

from tracker.models import Member

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


def _validate_date_range(start_str: str, end_str: str) -> tuple[datetime | None, datetime | None, str | None]:
	"""
	Validate date range inputs in YYYY-MM-DD format.
	Returns (start_date, end_date, error_message) tuple.
	error_message is None if validation succeeds.
	"""
	start_date = None
	end_date = None
	error_msg = None

	try:
		if start_str:
			start_date = datetime.strptime(start_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
		if end_str:
			end_date = datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)

		if start_date and end_date and end_date <= start_date:
			error_msg = 'End date must be after start date.'

	except (ValueError, TypeError):
		error_msg = 'Invalid date format. Please use YYYY-MM-DD format.'

	return start_date, end_date, error_msg


def _sort_meals(meals: list[Any]) -> list[Any]:
	"""Sort a list of meals chronologically by weekday, then by meal type order, then by ID."""
	meal_order = {
		'Breakfast': 0,
		'Morning Snack': 1,
		'Lunch': 2,
		'Afternoon Snack': 3,
		'Pre-Workout': 4,
		'Post-Workout': 5,
		'Dinner': 6,
		'Evening Snack': 7,
		'Other': 8
	}
	days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
	meals.sort(key=lambda m: (
		days.index(m.day_name) if m.day_name in days else 9,
		meal_order.get(m.meal_type, 9),
		m.id
	))
	return meals


def _safe_next_redirect(request: HttpRequest, default_route_name: str) -> HttpResponse:
	"""Redirect to a user-provided next path if it's a safe relative path."""
	next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()
	if next_url.startswith('/') and not next_url.startswith('//'):
		return redirect(next_url)
	return redirect(default_route_name)


def require_active(view_func):
	"""
	Decorator that ensures user is both logged in AND has an active account.

	Purpose: Additional protection for critical staff/trainer views.
	The middleware provides primary protection, but this decorator can be used
	for specific sensitive views as an extra layer of security.
	"""
	@wraps(view_func)
	@login_required
	def wrapper(request, *args, **kwargs):
		if not request.user.is_active:
			messages.error(request, 'Your account has been deactivated. Please contact the administrator.')
			return redirect('auth.login')
		return view_func(request, *args, **kwargs)
	return wrapper


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


from django.http import JsonResponse

def api_health(request: HttpRequest) -> JsonResponse:
	return JsonResponse({"status": "ok"})


