from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
	Attendance,
	DietAssignment,
	DietPlan,
	MealPlan,
	Member,
	Trainer,
	TrainerAssignment,
	User,
	Workout,
	WorkoutGuide,
	WorkoutTip,
)


class TrainerModuleSmokeTests(TestCase):
	def setUp(self):
		today = timezone.localdate()

		self.admin = User.objects.create_user(username='admin', email='admin@gym.local', password='pw')
		self.admin.role = User.Role.ADMIN
		self.admin.full_name = 'Admin'
		self.admin.save(update_fields=['role', 'full_name'])

		self.trainer_user = User.objects.create_user(username='trainer', email='trainer@gym.local', password='pw')
		self.trainer_user.role = User.Role.TRAINER
		self.trainer_user.full_name = 'Trainer'
		self.trainer_user.save(update_fields=['role', 'full_name'])
		self.trainer_profile = Trainer.objects.create(user=self.trainer_user, max_clients=10)

		self.member_user = User.objects.create_user(username='member', email='member@gym.local', password='pw')
		self.member_user.role = User.Role.MEMBER
		self.member_user.full_name = 'Member'
		self.member_user.save(update_fields=['role', 'full_name'])
		self.member = Member.objects.create(
			user=self.member_user,
			membership_start_date=today,
			membership_expiry_date=today + timedelta(days=30),
			is_active=True,
			is_approved=True,
			assigned_trainer=self.trainer_user,
		)

		TrainerAssignment.objects.create(
			trainer=self.trainer_user,
			member=self.member,
			assignment_date=today,
			start_date=today,
			assignment_type=TrainerAssignment.AssignmentType.PRIMARY,
			is_active=True,
		)

		Attendance.objects.create(member=self.member, check_in_time=timezone.now() - timedelta(days=1), duration_minutes=45)

	def test_admin_review_guide_page_renders(self):
		guide = WorkoutGuide.objects.create(
			name='Test Guide',
			description='Test description',
			category='Strength',
			difficulty_level='Beginner',
			duration_weeks=4,
			trainer=self.trainer_user,
			status=WorkoutGuide.Status.PENDING,
		)
		WorkoutTip.objects.create(
			guide=guide,
			exercise_name='Squat',
			tip_category='Form',
			content='Keep your back neutral.',
			order=1,
		)

		self.client.force_login(self.admin)
		resp = self.client.get(reverse('admin.review_guide', kwargs={'guide_id': guide.id}))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Tips Included:')

	def test_trainer_dashboard_and_members_pages(self):
		self.client.force_login(self.trainer_user)
		resp = self.client.get(reverse('trainer.dashboard'))
		self.assertEqual(resp.status_code, 200)
		resp = self.client.get(reverse('trainer.members'))
		self.assertEqual(resp.status_code, 200)

	def test_admin_trainer_list_and_manage_assignments(self):
		self.client.force_login(self.admin)
		resp = self.client.get(reverse('trainer.list_trainers'))
		self.assertEqual(resp.status_code, 200)

		# Unassign then re-assign via manage assignments
		resp = self.client.post(
			reverse('trainer.manage_assignments', kwargs={'trainer_id': self.trainer_profile.id}),
			data={'action': 'unassign', 'member_id': str(self.member.id)},
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		self.assertIsNone(self.member.assigned_trainer_id)

		resp = self.client.post(
			reverse('trainer.manage_assignments', kwargs={'trainer_id': self.trainer_profile.id}),
			data={'action': 'assign', 'member_id': str(self.member.id)},
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		self.assertEqual(self.member.assigned_trainer_id, self.trainer_user.id)

	def test_trainer_member_progress_and_workout_assignment(self):
		self.client.force_login(self.trainer_user)
		resp = self.client.get(reverse('trainer.member_progress', kwargs={'member_id': self.member.id}))
		self.assertEqual(resp.status_code, 200)
		resp = self.client.get(reverse('trainer.member_workouts', kwargs={'member_id': self.member.id}))
		self.assertEqual(resp.status_code, 200)

		resp = self.client.post(
			reverse('trainer.assign_workout', kwargs={'member_id': self.member.id}),
			data={
				'workout_date': str(timezone.localdate()),
				'exercise_name': 'Bench Press',
				'exercise_category': 'Strength',
				'sets': '3',
				'reps': '8',
				'weight': '80',
				'intensity': 'moderate',
				'notes': 'Assigned by trainer',
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertTrue(Workout.objects.filter(member=self.member, trainer=self.trainer_user).exists())

	def test_trainer_guides_and_diets_flows(self):
		self.client.force_login(self.trainer_user)

		# Create guide
		resp = self.client.post(
			reverse('trainer.create_guide'),
			data={
				'name': 'Beginner Program',
				'category': 'Strength',
				'difficulty_level': 'Beginner',
				'duration_weeks': '4',
			},
		)
		self.assertEqual(resp.status_code, 302)
		guide = WorkoutGuide.objects.order_by('-id').first()
		self.assertIsNotNone(guide)
		self.assertEqual(guide.status, WorkoutGuide.Status.DRAFT)

		# Add tip
		resp = self.client.post(
			reverse('trainer.add_guide_tip', kwargs={'guide_id': guide.id}),
			data={'exercise_name': 'Squat', 'tip_category': 'Form', 'content': 'Keep your back neutral.'},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertTrue(WorkoutTip.objects.filter(guide=guide).exists())

		# Submit guide
		resp = self.client.post(reverse('trainer.submit_guide', kwargs={'guide_id': guide.id}))
		self.assertEqual(resp.status_code, 302)
		guide.refresh_from_db()
		self.assertEqual(guide.status, WorkoutGuide.Status.PENDING)

		# Diet plan list + detail + assign
		plan = DietPlan.objects.create(name='Cutting', diet_type='cut', description='Test', is_active=True)
		MealPlan.objects.create(diet_plan=plan, day_name='Monday', meal_type='Breakfast', meal_name='Oats', calories=300)

		resp = self.client.get(reverse('trainer.list_diet_plans'))
		self.assertEqual(resp.status_code, 200)
		resp = self.client.get(reverse('trainer.view_diet_plan', kwargs={'plan_id': plan.id}))
		self.assertEqual(resp.status_code, 200)
		resp = self.client.post(
			reverse('trainer.assign_diet_to_member', kwargs={'member_id': self.member.id}),
			data={'diet_plan_id': str(plan.id), 'notes': 'Follow strictly'},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertTrue(DietAssignment.objects.filter(member=self.member, diet_plan=plan, is_active=True).exists())

	def test_reports_attendance_report(self):
		self.client.force_login(self.trainer_user)
		
		# Test GET request
		resp = self.client.get(reverse('reports.attendance_report'))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Attendance Report')

		# Test POST request for HTML view
		resp = self.client.post(
			reverse('reports.attendance_report'),
			data={
				'member_id': '',
				'start_date': (timezone.localdate() - timedelta(days=5)).isoformat(),
				'end_date': timezone.localdate().isoformat(),
				'format': 'html'
			}
		)
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Attendance Records')

		# Test POST request for CSV view
		resp = self.client.post(
			reverse('reports.attendance_report'),
			data={
				'member_id': '',
				'start_date': (timezone.localdate() - timedelta(days=5)).isoformat(),
				'end_date': timezone.localdate().isoformat(),
				'format': 'csv'
			}
		)
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp['Content-Type'], 'text/csv')

		# Test reports dashboard
		resp = self.client.get(reverse('reports.dashboard'))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Analytics Dashboard')

		# Test daily attendance report GET and CSV export
		resp = self.client.get(reverse('reports.daily_attendance'))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, "Today's Gym Attendance")

		resp = self.client.get(reverse('reports.daily_attendance') + '?format=csv')
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp['Content-Type'], 'text/csv')

		# Test fitness progress report GET and CSV export
		resp = self.client.get(reverse('reports.fitness_report', kwargs={'member_id': self.member.id}))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Fitness Progress Report')

		resp = self.client.get(reverse('reports.fitness_export', kwargs={'member_id': self.member.id}))
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp['Content-Type'], 'text/csv')

		# Test member list CSV export
		resp = self.client.get(reverse('member.list_members') + '?format=csv')
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp['Content-Type'], 'text/csv')


class MemberModuleSubscriptionTests(TestCase):
	def setUp(self):
		today = timezone.localdate()
		self.member_user = User.objects.create_user(username='member2', email='member2@gym.local', password='pw')
		self.member_user.role = User.Role.MEMBER
		self.member_user.full_name = 'Member Name'
		self.member_user.save(update_fields=['role', 'full_name'])
		self.member = Member.objects.create(
			user=self.member_user,
			membership_start_date=today,
			membership_expiry_date=today + timedelta(days=30),
			is_active=True,
			is_approved=True,
		)

	def test_member_profile_edit_success(self):
		self.client.force_login(self.member_user)
		resp = self.client.post(
			reverse('member.edit_member_profile'),
			data={
				'full_name': 'New Full Name',
				'email': 'newemail@gym.local',
				'phone_number': '1234567890',
				'gender': 'M',
				'date_of_birth': '1995-01-01',
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		self.member_user.refresh_from_db()
		self.assertEqual(self.member_user.full_name, 'New Full Name')
		self.assertEqual(self.member_user.email, 'newemail@gym.local')
		self.assertEqual(self.member.phone_number, '1234567890')
		self.assertEqual(self.member.gender, 'M')
		self.assertEqual(str(self.member.date_of_birth), '1995-01-01')

	def test_member_renew_pending_request(self):
		self.client.force_login(self.member_user)
		current_expiry = self.member.membership_expiry_date
		
		# 1. Member requests renewal (must remain pending)
		resp = self.client.post(
			reverse('member.renew'),
			data={'plan': 'monthly'},
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		self.assertEqual(self.member.membership_expiry_date, current_expiry)
		self.assertEqual(self.member.pending_renewal_plan, Member.MembershipType.MONTHLY)

		# 2. Admin confirms counter payment and approves
		admin_user = User.objects.create_user(username='admin_test', email='admin_test@gym.local', password='pw')
		admin_user.role = User.Role.ADMIN
		admin_user.save(update_fields=['role'])
		
		self.client.force_login(admin_user)
		resp = self.client.post(
			reverse('member.approve_renewal', kwargs={'member_id': self.member.id}),
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		self.assertEqual(self.member.membership_expiry_date, current_expiry + timedelta(days=30))
		self.assertEqual(self.member.membership_type, Member.MembershipType.MONTHLY)
		self.assertIsNone(self.member.pending_renewal_plan)

	def test_member_renew_already_pending(self):
		self.client.force_login(self.member_user)
		self.member.pending_renewal_plan = Member.MembershipType.MONTHLY
		self.member.save(update_fields=['pending_renewal_plan'])

		# Try to request renewal again
		resp = self.client.post(
			reverse('member.renew'),
			data={'plan': 'quarterly'},
		)
		self.assertEqual(resp.status_code, 302)
		
		self.member.refresh_from_db()
		# The pending plan must not have changed to 'quarterly'
		self.assertEqual(self.member.pending_renewal_plan, Member.MembershipType.MONTHLY)

	def test_member_reject_renewal_success(self):
		admin_user = User.objects.create_user(username='admin_reject', email='admin_reject@gym.local', password='pw')
		admin_user.role = User.Role.ADMIN
		admin_user.save(update_fields=['role'])
		self.client.force_login(admin_user)

		# Set pending plan
		self.member.pending_renewal_plan = Member.MembershipType.MONTHLY
		self.member.save(update_fields=['pending_renewal_plan'])

		# Reject renewal request
		resp = self.client.post(
			reverse('member.reject_renewal', kwargs={'member_id': self.member.id}),
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		self.assertIsNone(self.member.pending_renewal_plan)
		self.assertEqual(self.member.consecutive_rejections, 1)
		self.assertIsNotNone(self.member.last_rejection_date)

	def test_member_renewal_cooldown_enforced(self):
		self.client.force_login(self.member_user)
		
		# Set 3 consecutive rejections and a recent rejection timestamp
		self.member.consecutive_rejections = 3
		self.member.last_rejection_date = timezone.now()
		self.member.save(update_fields=['consecutive_rejections', 'last_rejection_date'])

		# Try to request renewal during lockout
		resp = self.client.post(
			reverse('member.renew'),
			data={'plan': 'monthly'},
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		self.assertIsNone(self.member.pending_renewal_plan)

	def test_member_renewal_cooldown_expired(self):
		self.client.force_login(self.member_user)
		
		# Set 3 consecutive rejections and a rejection timestamp > 1 month ago
		self.member.consecutive_rejections = 3
		self.member.last_rejection_date = timezone.now() - timedelta(days=31)
		self.member.save(update_fields=['consecutive_rejections', 'last_rejection_date'])

		# Try to request renewal after cooldown expired
		resp = self.client.post(
			reverse('member.renew'),
			data={'plan': 'monthly'},
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		# The request should succeed and reset consecutive rejections
		self.assertEqual(self.member.pending_renewal_plan, Member.MembershipType.MONTHLY)
		self.assertEqual(self.member.consecutive_rejections, 0)

	def test_member_list_pending_renewal_filter(self):
		# Create an admin user to access the list
		admin_user = User.objects.create_user(username='admin_test2', email='admin_test2@gym.local', password='pw')
		admin_user.role = User.Role.ADMIN
		admin_user.save(update_fields=['role'])
		self.client.force_login(admin_user)

		# Initially, no members have pending renewals
		resp = self.client.get(reverse('member.list_members') + '?status=pending_renewal')
		self.assertEqual(resp.status_code, 200)
		self.assertNotContains(resp, self.member.user.full_name)

		# Set the member's pending renewal plan
		self.member.pending_renewal_plan = Member.MembershipType.MONTHLY
		self.member.save(update_fields=['pending_renewal_plan'])

		# Now, the member should be shown in the filtered list
		resp = self.client.get(reverse('member.list_members') + '?status=pending_renewal')
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, self.member.user.full_name)
		self.assertContains(resp, 'Pay Counter: Monthly')
		self.assertContains(resp, 'Collect Payment')


class GuestVisitTests(TestCase):
	def setUp(self):
		self.admin = User.objects.create_user(username='admin_guest_test', email='adminguest@gym.local', password='pw')
		self.admin.role = User.Role.ADMIN
		self.admin.save(update_fields=['role'])

	def test_guest_visit_logging_success(self):
		self.client.force_login(self.admin)
		
		# Log guest visit via POST
		resp = self.client.post(
			reverse('attendance_routes.log_guest'),
			data={
				'full_name': 'Guest Walkin',
				'guest_type': 'regular',
				'email': 'guestwalkin@gym.local',
				'phone_number': '0987654321',
				'amount_paid': '100.00',
				'emergency_contact': 'Jane Doe (0987654321)',
				'notes': 'First time guest pass visitor',
			},
		)
		self.assertEqual(resp.status_code, 302)
		
		# Verify database state
		from .models import GuestVisit
		guest = GuestVisit.objects.filter(full_name='Guest Walkin').first()
		self.assertIsNotNone(guest)
		self.assertEqual(guest.email, 'guestwalkin@gym.local')
		self.assertEqual(guest.amount_paid, 100.00)
		self.assertEqual(guest.notes, 'First time guest pass visitor')

