from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from tracker.models import Member, FitnessMetric
from tracker.forms import FitnessMetricForm
from .base import _require_roles


def fitness_metrics(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect('auth.login')
	if not _require_roles(request, {'admin', 'staff', 'trainer'}):
		messages.error(request, 'Access denied.')
		return redirect('home')

	role = getattr(request.user, 'role', None)
	if role == 'trainer':
		members = Member.objects.filter(assigned_trainer=request.user, is_approved=True, is_active=True).select_related('user').order_by('user__full_name', 'id')
	else:
		members = Member.objects.filter(is_approved=True, is_active=True).select_related('user').order_by('user__full_name', 'id')

	if request.method == 'POST':
		member_id = (request.POST.get('member_id') or '').strip()
		metric_date_str = (request.POST.get('metric_date') or '').strip()
		weight_str = (request.POST.get('weight') or '').strip()
		height_str = (request.POST.get('height') or '').strip()

		if not member_id or not metric_date_str or not weight_str or not height_str:
			messages.error(request, 'Please fill in all required fields.')
			return redirect('fitness.add_metrics')

		try:
			member = Member.objects.get(id=int(member_id))
		except (ValueError, Member.DoesNotExist):
			messages.error(request, 'Invalid member selected.')
			return redirect('fitness.add_metrics')

		if role == 'trainer':
			if member.assigned_trainer_id != request.user.id:
				messages.error(request, 'You can only record metrics for your assigned members.')
				return redirect('fitness.add_metrics')

		form = FitnessMetricForm(request.POST)
		if form.is_valid():
			metric = form.save(commit=False)
			metric.member = member
			
			# BMI calculation: weight (kg) / (height (m) ^ 2)
			if metric.weight and metric.height:
				height_m = metric.height / 100.0
				metric.bmi = metric.weight / (height_m * height_m) if height_m > 0 else 0.0
				
			metric.created_by = request.user
			metric.save()
			messages.success(request, f'Fitness metrics recorded successfully for {member.user.full_name}.')
		else:
			messages.error(request, 'Weight and height must be valid numbers.')
			
		return redirect('fitness.add_metrics')

	return render(
		request,
		"fitness/metrics.html",
		{
			"members": list(members),
			"now": timezone.now,
		}
	)
