from __future__ import annotations

from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from tracker.models import Member, Attendance
from .base import _require_roles, _safe_next_redirect, _PaginationAdapter, _qr_data_uri


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

	return render(
		request,
		"attendance/dashboard.html",
		{
			"qr_image": qr_image,
			"countdown": countdown,
			"members": members,
			"all_sessions": all_sessions,
			"active_count": active_count,
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
	return render(request, "attendance/check_in.html", {"qr_image": qr_image, "countdown": countdown, "members": members})


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
