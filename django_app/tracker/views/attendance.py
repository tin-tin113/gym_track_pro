from __future__ import annotations

import csv
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from django.urls import reverse
from tracker.models import Member, Attendance, GuestVisit
from tracker.forms import GuestVisitForm
from .base import _require_roles, _safe_next_redirect, _PaginationAdapter, _qr_data_uri


def _auto_checkout_old_sessions() -> None:
	from datetime import timedelta
	from django.utils import timezone
	from tracker.models import Attendance

	now_dt = timezone.now()
	four_hours_ago = now_dt - timedelta(hours=4)
	open_sessions = Attendance.objects.filter(check_out_time__isnull=True, check_in_time__lt=four_hours_ago)
	for session in open_sessions:
		session.check_out_time = session.check_in_time + timedelta(hours=2) # default 2 hour stay
		session.duration_minutes = 120
		session.save(update_fields=['check_out_time', 'duration_minutes'])


def attendance_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	_auto_checkout_old_sessions()

	today = timezone.localdate()
	start_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	end_of_day = start_of_day + timedelta(days=1)

	members = list(
		Member.objects.select_related('user')
		.filter(is_active=True, is_approved=True)
		.order_by('user__full_name', 'id')
	)

	all_sessions = list(
		Attendance.objects.select_related('member', 'member__user')
		.filter(
			Q(check_out_time__isnull=True) |
			Q(check_out_time__gte=start_of_day, check_out_time__lt=end_of_day)
		)
		.order_by('-check_in_time')
	)

	qr_payload = f"GymTrackPro Attendance Check-In {today.isoformat()}"
	qr_image = _qr_data_uri(qr_payload)
	countdown = {"minutes": 23, "seconds": 59}

	active_count = sum(1 for s in all_sessions if s.check_out_time is None)

	# Fetch Guest pass stats for today
	guests_today = list(GuestVisit.objects.filter(visit_date=today).order_by('-created_at', '-id'))
	guest_count = len(guests_today)
	guest_revenue = sum(g.amount_paid for g in guests_today)

	return render(
		request,
		"attendance/dashboard.html",
		{
			"qr_image": qr_image,
			"countdown": countdown,
			"members": members,
			"all_sessions": all_sessions,
			"active_count": active_count,
			"guests_today": guests_today,
			"guest_count": guest_count,
			"guest_revenue": guest_revenue,
		},
	)


def attendance_check_in(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	_auto_checkout_old_sessions()

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
			return _safe_next_redirect(request, 'attendance_routes.check_in')

		if not member.is_membership_active():
			messages.error(request, f"Cannot check in: {member.user.full_name}'s membership has expired or is inactive.")
			return _safe_next_redirect(request, 'attendance_routes.check_in')

		already_active = Attendance.objects.filter(member=member, check_out_time__isnull=True).exists()
		if already_active:
			messages.info(request, f"{member.user.full_name} is already checked in.")
			return _safe_next_redirect(request, 'attendance_routes.dashboard')

		today = timezone.localdate()
		already_today = Attendance.objects.filter(member=member, check_in_time__date=today).exists()
		if already_today:
			messages.info(request, f"{member.user.full_name} has already been checked in today — use Undo if this was a mistake.")
			return _safe_next_redirect(request, 'attendance_routes.dashboard')

		Attendance.objects.create(member=member, check_in_time=timezone.now())
		messages.success(request, f"Checked in: {member.user.full_name}")
		return _safe_next_redirect(request, 'attendance_routes.dashboard')

	today = timezone.localdate()
	qr_payload = f"GymTrackPro Attendance Check-In {today.isoformat()}"
	qr_image = _qr_data_uri(qr_payload)
	countdown = {"minutes": 23, "seconds": 59}
	guest_form = GuestVisitForm()

	checked_in_today_ids = Attendance.objects.filter(
		check_in_time__date=today
	).values_list('member_id', flat=True)

	undo_members = list(
		Member.objects.select_related('user')
		.filter(id__in=checked_in_today_ids)
		.order_by('user__full_name', 'id')
	)

	guests_today = list(GuestVisit.objects.filter(visit_date=today).order_by('-created_at', '-id'))

	return render(request, "attendance/check_in.html", {
		"qr_image": qr_image,
		"countdown": countdown,
		"members": members,
		"undo_members": undo_members,
		"guest_form": guest_form,
		"guests_today": guests_today,
	})


@login_required
def attendance_undo_check_in(request: HttpRequest) -> HttpResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method != 'POST':
		messages.error(request, 'Invalid request method.')
		return _safe_next_redirect(request, 'attendance_routes.check_in')

	member_id = (request.POST.get('member_id') or '').strip()
	member = Member.objects.select_related('user').filter(id=member_id).first() if member_id else None
	if member is None:
		messages.error(request, 'Please select a valid member.')
		return _safe_next_redirect(request, 'attendance_routes.check_in')

	today = timezone.localdate()
	attendance = Attendance.objects.filter(member=member, check_in_time__date=today).order_by('-check_in_time').first()
	if attendance is None:
		messages.error(request, f'No check-in found for {member.user.full_name} today.')
		return _safe_next_redirect(request, 'attendance_routes.check_in')

	attendance.delete()
	messages.success(request, f"Removed today's check-in for: {member.user.full_name}")
	return _safe_next_redirect(request, 'attendance_routes.check_in')


def attendance_history(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	active_tab = request.GET.get('tab') or 'members'
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

	guest_search = (request.GET.get('guest_search') or '').strip()
	date_from = (request.GET.get('date_from') or '').strip()
	date_to = (request.GET.get('date_to') or '').strip()

	if active_tab == 'guests':
		qs = GuestVisit.objects.all().order_by('-visit_date', '-id')

		# Name search
		if guest_search:
			qs = qs.filter(full_name__icontains=guest_search)

		# Date range filter
		if date_from:
			try:
				day_from = timezone.datetime.fromisoformat(date_from).date()
				qs = qs.filter(visit_date__gte=day_from)
			except ValueError:
				pass
		if date_to:
			try:
				day_to = timezone.datetime.fromisoformat(date_to).date()
				qs = qs.filter(visit_date__lte=day_to)
			except ValueError:
				pass

		# Single-date backward compat
		if selected_date and not date_from and not date_to:
			try:
				day = timezone.datetime.fromisoformat(selected_date).date()
				qs = qs.filter(visit_date=day)
			except ValueError:
				messages.error(request, 'Invalid date filter.')
				return redirect('attendance_routes.history')

		paginator = Paginator(qs, 15)
		page_obj = paginator.get_page(page_number)
		pagination = _PaginationAdapter(paginator, page_obj)

		return render(
			request,
			"attendance/history.html",
			{
				"active_tab": 'guests',
				"guest_records": list(page_obj.object_list),
				"pagination": pagination,
				"selected_date": selected_date,
				"guest_search": guest_search,
				"date_from": date_from,
				"date_to": date_to,
			},
		)
	else:
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
				"active_tab": 'members',
				"members": members,
				"attendance_records": list(page_obj.object_list),
				"pagination": pagination,
				"selected_member_id": selected_member_int,
				"selected_date": selected_date,
			},
		)


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

	active_qs = (
		Attendance.objects.select_related('member', 'member__user')
		.filter(check_out_time__isnull=True)
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
	buckets = {f"{h:02d}": 0 for h in range(24)}
	for dt in qs.values_list('check_in_time', flat=True):
		local_dt = timezone.localtime(dt)
		buckets[f"{local_dt.hour:02d}"] += 1
	return JsonResponse(buckets)


@login_required
def attendance_log_guest(request: HttpRequest) -> HttpResponse:
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	if request.method == 'POST':
		form = GuestVisitForm(request.POST)
		if form.is_valid():
			guest_visit = form.save(commit=False)
			guest_visit.visit_date = timezone.localdate()
			guest_visit.save()
			messages.success(request, f"Guest pass confirmed! Walk-in guest logged: {guest_visit.full_name}.")
			return redirect(reverse('attendance_routes.check_in') + '?tab=guest-pane')
		else:
			errors = ", ".join([f"{k}: {v[0]}" for k, v in form.errors.items()])
			messages.error(request, f'Failed to log guest: {errors}')
			return redirect(reverse('attendance_routes.check_in') + '?tab=guest-pane')
	return redirect('attendance_routes.check_in')


@login_required
def attendance_export_guests_csv(request: HttpRequest) -> HttpResponse:
	"""Export guest visit records as CSV with optional filters."""
	if not _require_roles(request, {'admin', 'staff'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	qs = GuestVisit.objects.all().order_by('-visit_date', '-id')

	# Apply same filters as the history page
	guest_search = (request.GET.get('guest_search') or '').strip()
	date_from = (request.GET.get('date_from') or '').strip()
	date_to = (request.GET.get('date_to') or '').strip()

	if guest_search:
		qs = qs.filter(full_name__icontains=guest_search)
	if date_from:
		try:
			qs = qs.filter(visit_date__gte=timezone.datetime.fromisoformat(date_from).date())
		except ValueError:
			pass
	if date_to:
		try:
			qs = qs.filter(visit_date__lte=timezone.datetime.fromisoformat(date_to).date())
		except ValueError:
			pass

	response = HttpResponse(content_type='text/csv')
	response['Content-Disposition'] = 'attachment; filename="guest_visits.csv"'

	writer = csv.writer(response)
	writer.writerow(['Full Name', 'Guest Type', 'Email', 'Phone Number', 'Visit Date', 'Amount Paid', 'Emergency Contact', 'Notes'])

	for g in qs.iterator():
		writer.writerow([
			g.full_name,
			g.guest_type,
			g.email or '',
			g.phone_number or '',
			g.visit_date.isoformat(),
			f'{g.amount_paid:.2f}',
			g.emergency_contact or '',
			g.notes or '',
		])

	return response
