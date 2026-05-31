from __future__ import annotations

import csv
import io
from datetime import timedelta
from types import SimpleNamespace
from django.contrib import messages
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from tracker.models import Member, Attendance, FitnessMetric
from .base import _require_roles


def reports_dashboard(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	is_trainer = role == 'trainer'

	try:
		days = int(request.GET.get('days') or '7')
	except ValueError:
		days = 7
	if days not in {7, 30, 90}:
		days = 7

	now_dt = timezone.now()
	today = timezone.localdate()
	window_start = now_dt - timedelta(days=days)

	member_filter = Member.objects.filter(is_approved=True)
	if is_trainer:
		member_filter = member_filter.filter(assigned_trainer=request.user)

	total_members = member_filter.filter(is_active=True, membership_expiry_date__gte=today).count()
	expiring_soon = member_filter.filter(
		is_active=True,
		membership_expiry_date__gte=today,
		membership_expiry_date__lte=today + timedelta(days=7),
	).count()
	expired = member_filter.filter(Q(is_active=False) | Q(membership_expiry_date__lt=today)).count()

	attendance_filter = Attendance.objects.all()
	if is_trainer:
		attendance_filter = attendance_filter.filter(member__assigned_trainer=request.user)

	active_today = attendance_filter.filter(check_in_time__date=today).count()
	total_visits = attendance_filter.filter(check_in_time__gte=window_start).count()
	avg_daily_visits = round((total_visits / float(days)) if days else 0.0, 1)

	fitness_filter = FitnessMetric.objects.all()
	if is_trainer:
		fitness_filter = fitness_filter.filter(member__assigned_trainer=request.user)
	fitness_participants = (
		fitness_filter.values_list('member_id', flat=True).distinct().count()
		if fitness_filter.exists()
		else 0
	)

	rows = list(
		attendance_filter.filter(check_in_time__gte=window_start)
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
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	is_trainer = role == 'trainer'

	today = timezone.localdate()
	start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
	end = start + timedelta(days=1)

	qs = (
		Attendance.objects.select_related('member', 'member__user')
		.filter(check_in_time__gte=start, check_in_time__lt=end)
	)
	if is_trainer:
		qs = qs.filter(member__assigned_trainer=request.user)
	qs = qs.order_by('-check_in_time', '-id')

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

	completed_durations = [
		int((r.check_out_time - r.check_in_time).total_seconds() // 60)
		for r in records
		if r.check_in_time and r.check_out_time
	]
	avg_duration = int(sum(completed_durations) // len(completed_durations)) if completed_durations else None

	return render(
		request,
		"reports/daily_attendance.html",
		{
			"today": today,
			"now": now_dt,
			"records": records,
			"total_visits": total_visits,
			"still_checked_in": still_checked_in,
			"avg_duration": avg_duration,
		},
	)


def reports_attendance_report(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	is_trainer = role == 'trainer'

	now_dt = timezone.now()
	member_qs = Member.objects.select_related('user')
	if is_trainer:
		member_qs = member_qs.filter(assigned_trainer=request.user)
	members = list(member_qs.order_by('user__full_name', 'id'))
	
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

		qs = Attendance.objects.select_related('member', 'member__user').filter(check_in_time__gte=start_dt, check_in_time__lte=end_dt)
		if is_trainer:
			qs = qs.filter(member__assigned_trainer=request.user)
		qs = qs.order_by('-check_in_time', '-id')

		if member_id and member_id.isdigit():
			member_obj = Member.objects.select_related('user').filter(id=int(member_id)).first()
			if member_obj:
				if is_trainer and member_obj.assigned_trainer_id != request.user.id:
					messages.error(request, 'Access denied to this member.')
					return redirect('reports.attendance_report')
				qs = qs.filter(member=member_obj)

		records = list(qs)
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
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	is_trainer = role == 'trainer'

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('reports.dashboard')

	if is_trainer and member.assigned_trainer_id != request.user.id:
		messages.error(request, 'Access denied to this member.')
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
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	is_trainer = role == 'trainer'

	member = Member.objects.select_related('user').filter(id=member_id).first()
	if member is None:
		messages.error(request, 'Member not found.')
		return redirect('reports.dashboard')

	if is_trainer and member.assigned_trainer_id != request.user.id:
		messages.error(request, 'Access denied to this member.')
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
