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

	def test_public_signup_accepts_matching_passwords(self):
		resp = self.client.post(
			reverse('auth.signup'),
			data={
				'full_name': 'New Member',
				'email': 'new.member@example.com',
				'password': 'StrongPass123!',
				'confirm_password': 'StrongPass123!',
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertTrue(User.objects.filter(email='new.member@example.com').exists())
