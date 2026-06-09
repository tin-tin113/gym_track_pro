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
	WorkoutSet,
	GuideAssignment,
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

	def test_member_rejection_dashboard_alerts(self):
		admin_user = User.objects.create_user(username='admin_reject2', email='admin_reject2@gym.local', password='pw')
		admin_user.role = User.Role.ADMIN
		admin_user.save(update_fields=['role'])

		# 1. Reject the renewal first
		self.client.force_login(admin_user)
		self.member.pending_renewal_plan = Member.MembershipType.MONTHLY
		self.member.save(update_fields=['pending_renewal_plan'])
		self.client.post(reverse('member.reject_renewal', kwargs={'member_id': self.member.id}))

		# 2. Member logs in, gets dashboard, and sees the alert banner
		self.client.force_login(self.member_user)
		resp = self.client.get(reverse('member.member_dashboard'))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Renewal Request Declined')

		# 3. Member submits a new renewal request
		self.client.post(reverse('member.renew'), data={'plan': 'monthly'})
		
		# 4. Member checks dashboard again; the alert banner should disappear because a new request is pending
		resp = self.client.get(reverse('member.member_dashboard'))
		self.assertEqual(resp.status_code, 200)
		self.assertNotContains(resp, 'Renewal Request Declined')

		# 5. Admin approves renewal
		self.client.force_login(admin_user)
		self.client.post(reverse('member.approve_renewal', kwargs={'member_id': self.member.id}))
		self.member.refresh_from_db()
		self.assertIsNone(self.member.last_rejection_date)

		# 6. Member checks dashboard; no alert banner is shown
		self.client.force_login(self.member_user)
		resp = self.client.get(reverse('member.member_dashboard'))
		self.assertEqual(resp.status_code, 200)
		self.assertNotContains(resp, 'Renewal Request Declined')


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

	def test_concurrent_subscriptions_created_and_displayed(self):
		from .models import Subscription
		# Create an admin user to approve renewal
		admin_user = User.objects.create_user(username='admin_sub_test', email='adminsub@gym.local', password='pw')
		admin_user.role = User.Role.ADMIN
		admin_user.save(update_fields=['role'])

		# 1. Member already has a default Monthly subscription created in setUp()
		# 2. Member requests a Quarterly subscription renewal (pending)
		self.client.force_login(self.member_user)
		resp = self.client.post(
			reverse('member.renew'),
			data={'plan': 'quarterly'},
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()
		self.assertEqual(self.member.pending_renewal_plan, Member.MembershipType.QUARTERLY)

		# 3. Admin approves/collects payment
		self.client.force_login(admin_user)
		resp = self.client.post(
			reverse('member.approve_renewal', kwargs={'member_id': self.member.id}),
		)
		self.assertEqual(resp.status_code, 302)
		self.member.refresh_from_db()

		# Verify that two active subscriptions exist in the database for this member
		active_subs = self.member.active_subscriptions
		self.assertEqual(active_subs.count(), 2)

		# Verify member list displays both active subscriptions
		resp = self.client.get(reverse('member.list_members'))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Monthly')
		self.assertContains(resp, 'Quarterly')



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


class AttendanceCheckInTests(TestCase):
	def setUp(self):
		self.admin = User.objects.create_user(username='admin_checkin', email='admincheckin@gym.local', password='pw')
		self.admin.role = User.Role.ADMIN
		self.admin.save(update_fields=['role'])

		self.member_user = User.objects.create_user(username='member_checkin', email='membercheckin@gym.local', password='pw')
		self.member_user.role = User.Role.MEMBER
		self.member_user.save(update_fields=['role'])
		self.member = Member.objects.create(
			user=self.member_user,
			membership_start_date=timezone.localdate(),
			membership_expiry_date=timezone.localdate() + timedelta(days=30),
			is_active=True,
			is_approved=True,
		)

	def test_check_in_page_requires_auth(self):
		response = self.client.get(reverse('attendance_routes.check_in'))
		self.assertEqual(response.status_code, 302)

	def test_check_in_page_renders_for_admin(self):
		self.client.force_login(self.admin)
		response = self.client.get(reverse('attendance_routes.check_in'))
		self.assertEqual(response.status_code, 200)

	def test_manual_check_in_success(self):
		self.client.force_login(self.admin)
		response = self.client.post(
			reverse('attendance_routes.check_in'),
			data={'member_id': str(self.member.id)}
		)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(Attendance.objects.filter(member=self.member).exists())

	def test_check_in_expired_membership_fails(self):
		# Set expiry date to yesterday
		self.member.membership_expiry_date = timezone.localdate() - timedelta(days=1)
		self.member.save()

		self.client.force_login(self.admin)
		response = self.client.post(
			reverse('attendance_routes.check_in'),
			data={'member_id': str(self.member.id)}
		)
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Attendance.objects.filter(member=self.member).exists())

	def test_check_in_page_contains_undo_members(self):
		self.client.force_login(self.admin)
		
		# Initially no check-ins, so the member should not be in the undo dropdown
		response = self.client.get(reverse('attendance_routes.check_in'))
		self.assertEqual(response.status_code, 200)
		html = response.content.decode()
		undo_section = html.split('id="undo_member_id"')[1].split('</select>')[0]
		self.assertNotIn(f'value="{self.member.id}"', undo_section)

		# Create a check-in today for the member
		Attendance.objects.create(member=self.member, check_in_time=timezone.now())

		# Now the member should be in the undo dropdown
		response = self.client.get(reverse('attendance_routes.check_in'))
		self.assertEqual(response.status_code, 200)
		html = response.content.decode()
		undo_section = html.split('id="undo_member_id"')[1].split('</select>')[0]
		self.assertIn(f'value="{self.member.id}"', undo_section)


class MemberWorkoutImprovementTests(TestCase):
	def setUp(self):
		self.today = timezone.localdate()
		self.member_user = User.objects.create_user(username='member_workout_test', email='mworkout@gym.local', password='pw')
		self.member_user.role = User.Role.MEMBER
		self.member_user.full_name = 'Workout Member'
		self.member_user.save(update_fields=['role', 'full_name'])
		self.member = Member.objects.create(
			user=self.member_user,
			membership_start_date=self.today - timedelta(days=5),
			membership_expiry_date=self.today + timedelta(days=25),
			is_active=True,
			is_approved=True,
		)
		self.client.force_login(self.member_user)

	def test_member_workouts_list_filtering(self):
		w1 = Workout.objects.create(
			member=self.member,
			workout_date=self.today,
			exercise_name='Barbell Curl',
			exercise_category='Strength',
			muscle_group='arms',
			sets=3,
			reps=10,
			weight=60.0,
			intensity='moderate',
		)
		w2 = Workout.objects.create(
			member=self.member,
			workout_date=self.today - timedelta(days=1),
			exercise_name='Treadmill Run',
			exercise_category='Cardio',
			muscle_group='cardio',
			duration_minutes=30,
			distance_km=5.0,
			intensity='intense',
		)

		# 1. Search filter
		resp = self.client.get(reverse('member.list_workouts') + '?search=Barbell')
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Barbell Curl')
		self.assertNotContains(resp, 'Treadmill Run')

		# 2. Category filter
		resp = self.client.get(reverse('member.list_workouts') + '?category=Cardio')
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Treadmill Run')
		self.assertNotContains(resp, 'Barbell Curl')

		# 3. Muscle Group filter
		resp = self.client.get(reverse('member.list_workouts') + '?muscle_group=arms')
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Barbell Curl')
		self.assertNotContains(resp, 'Treadmill Run')

		# 4. Date filter
		resp = self.client.get(reverse('member.list_workouts') + f'?date_from={self.today}&date_to={self.today}')
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Barbell Curl')
		self.assertNotContains(resp, 'Treadmill Run')

	def test_member_dashboard_workout_statistics(self):
		Workout.objects.create(
			member=self.member,
			workout_date=self.today,
			exercise_name='Barbell Curl',
			exercise_category='Strength',
			muscle_group='arms',
			sets=3,
			reps=10,
			weight=60.0,
		)
		Workout.objects.create(
			member=self.member,
			workout_date=self.today,
			exercise_name='Squat',
			exercise_category='Strength',
			muscle_group='legs',
			sets=3,
			reps=5,
			weight=100.0,
		)
		Workout.objects.create(
			member=self.member,
			workout_date=self.today - timedelta(days=1),
			exercise_name='Running',
			exercise_category='Cardio',
			duration_minutes=30,
			distance_km=5.0,
		)

		resp = self.client.get(reverse('member.member_dashboard'))
		self.assertEqual(resp.status_code, 200)
		
		# Assert metrics and statistics are removed from the dashboard response
		self.assertNotContains(resp, 'Total Workouts')
		self.assertNotContains(resp, 'Weekly Frequency')
		self.assertNotContains(resp, 'Training Balance')

	def test_member_exercise_history_view(self):
		# Create progressive overload workouts
		Workout.objects.create(
			member=self.member,
			workout_date=self.today - timedelta(days=2),
			exercise_name='Barbell Curl',
			exercise_category='Strength',
			muscle_group='arms',
			sets=3,
			reps=10,
			weight=50.0,
		)
		Workout.objects.create(
			member=self.member,
			workout_date=self.today - timedelta(days=1),
			exercise_name='Barbell Curl',
			exercise_category='Strength',
			muscle_group='arms',
			sets=3,
			reps=8,
			weight=60.0,
		)

		resp = self.client.get(reverse('member.exercise_history') + '?exercise=Barbell%20Curl')
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Barbell Curl History')
		
		# Verify PR badges are rendered in response
		self.assertContains(resp, 'PR')
		self.assertContains(resp, '1RM PR')
		self.assertContains(resp, '50.0')
		self.assertContains(resp, '60.0')

	def test_member_clone_workout_success(self):
		orig = Workout.objects.create(
			member=self.member,
			workout_date=self.today - timedelta(days=2),
			exercise_name='Deadlift',
			exercise_category='Strength',
			muscle_group='back',
			sets=1,
			reps=5,
			weight=140.0,
			notes='Heavy session',
		)
		WorkoutSet.objects.create(
			workout=orig,
			set_number=1,
			reps=5,
			weight=140.0,
			is_completed=True,
		)

		# 1. GET page with clone_id
		resp = self.client.get(reverse('member.create_workout') + f"?clone_id={orig.id}")
		self.assertEqual(resp.status_code, 200)
		
		# Verify HTML content has pre-filled values
		self.assertContains(resp, 'Deadlift')
		self.assertContains(resp, '140')
		self.assertContains(resp, '5')

		# 2. POST to save the cloned workout template
		import json
		post_data = {
			'workout_date': self.today.strftime('%Y-%m-%d'),
			'exercise_category': 'Strength',
			'muscle_group': 'back',
			'exercise_name': 'Deadlift',
			'sets': 1,
			'reps': 5,
			'weight': 140.0,
			'intensity': 'moderate',
			'notes': 'Heavy session copy',
			'sets_data': json.dumps([{
				'set_number': 1,
				'weight': 140.0,
				'reps': 5,
				'is_completed': True,
			}])
		}
		resp2 = self.client.post(reverse('member.create_workout'), post_data)
		self.assertEqual(resp2.status_code, 302)

		cloned = Workout.objects.filter(exercise_name='Deadlift').order_by('-id').first()
		self.assertNotEqual(cloned.id, orig.id)
		self.assertEqual(cloned.workout_date, self.today)
		self.assertEqual(cloned.sets, 1)
		self.assertEqual(cloned.reps, 5)
		self.assertEqual(cloned.weight, 140.0)

	def test_member_clone_workout_calculates_prs(self):
		# Create prior history for Bench Press (60kg)
		prior_workout = Workout.objects.create(
			member=self.member,
			workout_date=self.today - timedelta(days=5),
			exercise_name='Bench Press',
			exercise_category='Strength',
			muscle_group='chest',
		)
		WorkoutSet.objects.create(
			workout=prior_workout,
			set_number=1,
			reps=10,
			weight=60.0,
			is_completed=True,
		)

		# Create the workout to clone which has the same 60kg set
		orig = Workout.objects.create(
			member=self.member,
			workout_date=self.today - timedelta(days=2),
			exercise_name='Bench Press',
			exercise_category='Strength',
			muscle_group='chest',
			sets=1,
			reps=10,
			weight=60.0,
		)
		WorkoutSet.objects.create(
			workout=orig,
			set_number=1,
			reps=10,
			weight=60.0,
			is_completed=True,
		)

		# 1. GET page with clone_id
		resp = self.client.get(reverse('member.create_workout') + f"?clone_id={orig.id}")
		self.assertEqual(resp.status_code, 200)

		# 2. POST to save it with a new PR (80kg)
		import json
		post_data = {
			'workout_date': self.today.strftime('%Y-%m-%d'),
			'exercise_category': 'Strength',
			'muscle_group': 'chest',
			'exercise_name': 'Bench Press',
			'sets': 1,
			'reps': 10,
			'weight': 80.0,
			'intensity': 'moderate',
			'sets_data': json.dumps([{
				'set_number': 1,
				'weight': 80.0,
				'reps': 10,
				'is_completed': True,
			}])
		}
		resp2 = self.client.post(reverse('member.create_workout'), post_data)
		self.assertEqual(resp2.status_code, 302)

		# Fetch the cloned workout and sets
		cloned = Workout.objects.filter(exercise_name='Bench Press').order_by('-id').first()
		self.assertNotEqual(cloned.id, orig.id)
		self.assertEqual(cloned.workout_date, self.today)

		cloned_set = cloned.sets_list.filter(set_number=1).first()
		self.assertIsNotNone(cloned_set)
		# It should be flagged as a PR because 80kg is higher than the historical 60kg!
		self.assertTrue(cloned_set.is_pr)

		# Now clone a workout that is NOT a PR (e.g. 50kg, since the history now has 80kg from today)
		orig_light = Workout.objects.create(
			member=self.member,
			workout_date=self.today - timedelta(days=1),
			exercise_name='Bench Press',
			exercise_category='Strength',
			muscle_group='chest',
			sets=1,
			reps=10,
			weight=50.0,
		)
		WorkoutSet.objects.create(
			workout=orig_light,
			set_number=1,
			reps=10,
			weight=50.0,
			is_completed=True,
		)

		resp3 = self.client.get(reverse('member.create_workout') + f"?clone_id={orig_light.id}")
		self.assertEqual(resp3.status_code, 200)

		post_data_light = {
			'workout_date': self.today.strftime('%Y-%m-%d'),
			'exercise_category': 'Strength',
			'muscle_group': 'chest',
			'exercise_name': 'Bench Press',
			'sets': 1,
			'reps': 10,
			'weight': 50.0,
			'intensity': 'moderate',
			'sets_data': json.dumps([{
				'set_number': 1,
				'weight': 50.0,
				'reps': 10,
				'is_completed': True,
			}])
		}
		resp4 = self.client.post(reverse('member.create_workout'), post_data_light)
		self.assertEqual(resp4.status_code, 302)

		cloned_light = Workout.objects.filter(exercise_name='Bench Press').order_by('-id').first()
		cloned_light_set = cloned_light.sets_list.filter(set_number=1).first()
		self.assertIsNotNone(cloned_light_set)
		# It should NOT be flagged as a PR because 50kg is lower than the historical 80kg!
		self.assertFalse(cloned_light_set.is_pr)


class AdvancedFitnessLoggingTests(TestCase):
	def setUp(self):
		self.today = timezone.localdate()
		self.member_user = User.objects.create_user(username='adv_member', email='adv@gym.local', password='pw')
		self.member_user.role = User.Role.MEMBER
		self.member_user.save(update_fields=['role'])
		self.member = Member.objects.create(
			user=self.member_user,
			membership_start_date=self.today - timedelta(days=2),
			membership_expiry_date=self.today + timedelta(days=28),
			is_active=True,
			is_approved=True,
		)
		self.client.force_login(self.member_user)

	def test_workout_set_volume_and_1rm_properties(self):
		workout = Workout.objects.create(
			member=self.member,
			workout_date=self.today,
			exercise_name='Bench Press',
			exercise_category='Strength',
		)
		s1 = WorkoutSet.objects.create(
			workout=workout, set_number=1, weight=60.0, reps=10, is_completed=True
		)
		s2 = WorkoutSet.objects.create(
			workout=workout, set_number=2, weight=70.0, reps=8, is_completed=True
		)
		s3 = WorkoutSet.objects.create(
			workout=workout, set_number=3, weight=80.0, reps=6, is_completed=True
		)
		s4 = WorkoutSet.objects.create(
			workout=workout, set_number=4, weight=90.0, reps=5, is_completed=False  # not completed
		)

		# Completed volume: (60*10) + (70*8) + (80*6) = 600 + 560 + 480 = 1640
		self.assertEqual(workout.get_volume(), 1640.0)

		# Max completed weight: 80.0
		self.assertEqual(workout.get_max_weight(), 80.0)

		# Estimated 1RM max completed:
		# s1: 60 * (1 + 10/30) = 80.0
		# s2: 70 * (1 + 8/30) = 88.66
		# s3: 80 * (1 + 6/30) = 96.0
		# max: 96.0
		self.assertAlmostEqual(workout.get_max_estimated_1rm(), 96.0)

	def test_member_workout_form_multiple_sets_saving(self):
		post_data = {
			'workout_date': self.today.strftime('%Y-%m-%d'),
			'exercise_category': 'Strength',
			'muscle_group': 'chest',
			'exercise_name': 'Bench Press',
			'sets': 3,
			'reps': 10,
			'weight': 60,
			'intensity': 'moderate',
			'notes': 'Some notes',
			'sets_data': '[{"set_number":1,"weight":60,"reps":10,"is_completed":true},{"set_number":2,"weight":65,"reps":8,"is_completed":true},{"set_number":3,"weight":70,"reps":6,"is_completed":true}]'
		}
		resp = self.client.post(reverse('member.create_workout'), post_data)
		self.assertEqual(resp.status_code, 302)

		workout = Workout.objects.filter(member=self.member, exercise_name='Bench Press').first()
		self.assertIsNotNone(workout)
		self.assertEqual(workout.sets_list.count(), 3)
		
		# Summary fields should match the max/total
		self.assertEqual(workout.sets, 3)
		self.assertEqual(workout.reps, 10)  # max reps
		self.assertEqual(workout.weight, 70.0)  # max weight

	def test_start_assigned_guide_session_flow(self):
		trainer_user = User.objects.create_user(username='tr_guide', email='tr@gym.local', password='pw')
		guide = WorkoutGuide.objects.create(
			name='PPL Push',
			category='Strength',
			difficulty_level='Intermediate',
			trainer=trainer_user,
			status=WorkoutGuide.Status.APPROVED
		)
		tip1 = WorkoutTip.objects.create(
			guide=guide, exercise_name='Overhead Press', tip_category='Strength', content='Press heavy', order=1
		)
		tip2 = WorkoutTip.objects.create(
			guide=guide, exercise_name='Incline Bench', tip_category='Strength', content='30 deg incline', order=2
		)
		assignment = GuideAssignment.objects.create(
			guide=guide, member=self.member, trainer=trainer_user, is_active=True
		)

		# 1. Trigger Start Guide View
		start_url = reverse('member.start_assigned_guide_session', kwargs={'assignment_id': assignment.id})
		resp = self.client.get(start_url)
		expected_redirect = reverse('member.create_workout') + f"?guide_id={guide.id}&tip_index=0"
		self.assertRedirects(resp, expected_redirect)

		# 2. Perform GET on the redirected form page
		resp = self.client.get(expected_redirect)
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Overhead Press')  # prefilled exercise name

		# 3. Post first exercise log
		post_data_1 = {
			'workout_date': self.today.strftime('%Y-%m-%d'),
			'exercise_category': 'Strength',
			'exercise_name': 'Overhead Press',
			'sets': 3,
			'reps': 10,
			'weight': 40,
			'intensity': 'moderate',
			'sets_data': '[{"set_number":1,"weight":40,"reps":10,"is_completed":true}]'
		}
		resp = self.client.post(reverse('member.create_workout') + f"?guide_id={guide.id}&tip_index=0", post_data_1)
		self.assertRedirects(resp, reverse('member.create_workout') + f"?guide_id={guide.id}&tip_index=1")

		w1 = Workout.objects.filter(exercise_name='Overhead Press').first()
		self.assertEqual(w1.guide, guide)
		self.assertEqual(w1.guide_assignment, assignment)

		# 4. Post second (last) exercise log
		post_data_2 = {
			'workout_date': self.today.strftime('%Y-%m-%d'),
			'exercise_category': 'Strength',
			'exercise_name': 'Incline Bench',
			'sets': 3,
			'reps': 8,
			'weight': 60,
			'intensity': 'intense',
			'sets_data': '[{"set_number":1,"weight":60,"reps":8,"is_completed":true}]'
		}
		resp = self.client.post(reverse('member.create_workout') + f"?guide_id={guide.id}&tip_index=1", post_data_2)
		self.assertRedirects(resp, reverse('member.member_programs'))

		assignment.refresh_from_db()
		self.assertTrue(assignment.is_completed)
		self.assertIsNotNone(assignment.completion_date)



