from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
	Attendance,
	DietAssignment,
	DietPlan,
	FitnessMetric,
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

	def test_fitness_metrics_trainer_id_mismatch(self):
		# Create an artificial difference between User ID and Trainer ID
		# Force a high user ID by creating dummy users, then create the trainer profile
		for i in range(10):
			User.objects.create(username=f'dummy{i}', email=f'dummy{i}@gym.local')
		
		trainer_user2 = User.objects.create_user(username='trainer2', email='trainer2@gym.local', password='pw')
		trainer_user2.role = User.Role.TRAINER
		trainer_user2.save(update_fields=['role'])
		
		# Trainer profile ID will be 2 (second trainer), but User ID will be 13 (2 + 1 + 10)
		trainer_profile2 = Trainer.objects.create(user=trainer_user2, max_clients=10)
		
		self.assertNotEqual(trainer_user2.id, trainer_profile2.id)

		# Create member assigned to trainer2
		member_user2 = User.objects.create_user(username='member2', email='member2@gym.local', password='pw')
		member_user2.role = User.Role.MEMBER
		member_user2.save(update_fields=['role'])
		member2 = Member.objects.create(
			user=member_user2,
			membership_start_date=timezone.localdate(),
			membership_expiry_date=timezone.localdate() + timedelta(days=30),
			is_active=True,
			is_approved=True,
			assigned_trainer=trainer_user2,
		)

		self.client.force_login(trainer_user2)
		
		# Test GET fitness metrics lists member2
		resp = self.client.get(reverse('fitness.add_metrics'))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, member_user2.full_name)

		# Test POST fitness metrics successfully logs for member2
		resp = self.client.post(
			reverse('fitness.add_metrics'),
			data={
				'member_id': str(member2.id),
				'metric_date': str(timezone.localdate()),
				'weight': '75.5',
				'height': '178.0',
			}
		)
		self.assertEqual(resp.status_code, 302)
		self.assertTrue(FitnessMetric.objects.filter(member=member2, weight=75.5).exists())

	def test_dashboard_permissions_resolved(self):
		staff_user = User.objects.create_user(username='staff', email='staff@gym.local', password='pw')
		staff_user.role = User.Role.STAFF
		staff_user.save(update_fields=['role'])

		# 1. Staff user should be BLOCKED from admin dashboard
		self.client.force_login(staff_user)
		resp = self.client.get(reverse('admin.dashboard'))
		self.assertEqual(resp.status_code, 302) # Redirects to home with error

		# 2. Admin user should be ALLOWED on staff dashboard
		self.client.force_login(self.admin)
		resp = self.client.get(reverse('staff.dashboard'))
		self.assertEqual(resp.status_code, 200) # Renders fine

	def test_staff_member_approvals(self):
		staff_user = User.objects.create_user(username='staff2', email='staff2@gym.local', password='pw')
		staff_user.role = User.Role.STAFF
		staff_user.save(update_fields=['role'])

		pending_user = User.objects.create_user(username='pending', email='pending@gym.local', password='pw')
		pending_user.role = User.Role.MEMBER
		pending_user.save(update_fields=['role'])
		pending_member = Member.objects.create(
			user=pending_user,
			membership_start_date=timezone.localdate(),
			membership_expiry_date=timezone.localdate() + timedelta(days=30),
			is_active=True,
			is_approved=False,
		)

		self.client.force_login(staff_user)

		# Staff approves pending member
		resp = self.client.post(reverse('admin.approve_member', kwargs={'member_id': pending_member.id}))
		self.assertEqual(resp.status_code, 302)
		pending_member.refresh_from_db()
		self.assertTrue(pending_member.is_approved)

	def test_trainer_reports_scoping(self):
		# Create trainer
		trainer_user3 = User.objects.create_user(username='trainer3', email='trainer3@gym.local', password='pw')
		trainer_user3.role = User.Role.TRAINER
		trainer_user3.save(update_fields=['role'])
		Trainer.objects.create(user=trainer_user3)

		# Create members
		member_user3 = User.objects.create_user(username='member3', email='member3@gym.local', password='pw')
		member_user3.role = User.Role.MEMBER
		member_user3.save(update_fields=['role'])
		member3 = Member.objects.create(
			user=member_user3,
			membership_start_date=timezone.localdate(),
			membership_expiry_date=timezone.localdate() + timedelta(days=30),
			is_active=True,
			is_approved=True,
			assigned_trainer=trainer_user3,
		)

		# Another member not assigned to trainer3
		member_user4 = User.objects.create_user(username='member4', email='member4@gym.local', password='pw')
		member_user4.role = User.Role.MEMBER
		member_user4.save(update_fields=['role'])
		member4 = Member.objects.create(
			user=member_user4,
			membership_start_date=timezone.localdate(),
			membership_expiry_date=timezone.localdate() + timedelta(days=30),
			is_active=True,
			is_approved=True,
			assigned_trainer=self.trainer_user,
		)

		self.client.force_login(trainer_user3)

		# 1. Dashboard should be accessible by trainer
		resp = self.client.get(reverse('reports.dashboard'))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, '<h2 class="text-primary">1</h2>')  # Only member3 counted for trainer3

		# 2. Fitness report should be accessible by trainer for assigned member3
		resp = self.client.get(reverse('reports.fitness_report', kwargs={'member_id': member3.id}))
		self.assertEqual(resp.status_code, 200)

		# 3. Fitness report should be BLOCKED for unassigned member4
		resp = self.client.get(reverse('reports.fitness_report', kwargs={'member_id': member4.id}))
		self.assertEqual(resp.status_code, 302) # Access Denied / Redirects to dashboard

	def test_diet_crud_flow_and_meal_management(self):
		self.client.force_login(self.trainer_user)

		# 1. Create a diet plan
		resp = self.client.post(
			reverse('trainer.create_diet_plan'),
			data={
				'name': 'Test Diet Plan',
				'description': 'A very descriptive description',
				'diet_type': 'surplus',
				'daily_calories': '3000',
				'macro_ratio_protein': '35',
				'macro_ratio_carbs': '40',
				'macro_ratio_fats': '25',
				'notes': 'Some notes'
			}
		)
		self.assertEqual(resp.status_code, 302)
		plan = DietPlan.objects.filter(name='Test Diet Plan').first()
		self.assertIsNotNone(plan)
		self.assertEqual(plan.daily_calories, 3000)
		self.assertAlmostEqual(float(plan.macro_ratio_protein), 0.35)

		# 2. Edit the diet plan
		resp = self.client.post(
			reverse('trainer.edit_diet_plan', kwargs={'plan_id': plan.id}),
			data={
				'name': 'Test Diet Plan Edited',
				'description': 'An edited descriptive description',
				'diet_type': 'calorie_deficit',
				'daily_calories': '1800',
				'macro_ratio_protein': '40',
				'macro_ratio_carbs': '30',
				'macro_ratio_fats': '30',
				'notes': 'Some edited notes'
			}
		)
		self.assertEqual(resp.status_code, 302)
		plan.refresh_from_db()
		self.assertEqual(plan.name, 'Test Diet Plan Edited')
		self.assertEqual(plan.daily_calories, 1800)

		# 3. Add a meal
		resp = self.client.post(
			reverse('trainer.add_meal', kwargs={'plan_id': plan.id}),
			data={
				'meal_name': 'Super Protein Shake',
				'meal_type': 'Snack',
				'day_name': 'Wednesday',
				'calories': '400',
				'protein_g': '45',
				'carbs_g': '20',
				'fats_g': '5',
				'notes': 'Drink right after workout'
			}
		)
		self.assertEqual(resp.status_code, 302)
		meal = MealPlan.objects.filter(meal_name='Super Protein Shake', diet_plan=plan).first()
		self.assertIsNotNone(meal)
		self.assertEqual(meal.calories, 400)
		self.assertEqual(meal.day_name, 'Wednesday')

		# 4. View plan detail page
		resp = self.client.get(reverse('trainer.view_diet_plan', kwargs={'plan_id': plan.id}))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Super Protein Shake')

		# 5. Delete the meal
		resp = self.client.post(
			reverse('trainer.delete_meal', kwargs={'plan_id': plan.id, 'meal_id': meal.id})
		)
		self.assertEqual(resp.status_code, 302)
		self.assertFalse(MealPlan.objects.filter(id=meal.id).exists())

		# 6. Deactivate / Delete the diet plan
		resp = self.client.post(
			reverse('trainer.delete_diet_plan', kwargs={'plan_id': plan.id})
		)
		self.assertEqual(resp.status_code, 302)
		plan.refresh_from_db()
		self.assertFalse(plan.is_active)

	def test_member_guides_library_access_public(self):
		self.client.force_login(self.member_user)
		resp = self.client.get(reverse('member.browse_guides_library'))
		self.assertEqual(resp.status_code, 200)

	def test_admin_approve_guide_flow(self):
		guide = WorkoutGuide.objects.create(
			name='Review Program',
			category='Strength',
			difficulty_level='Beginner',
			duration_weeks=4,
			trainer=self.trainer_user,
			status=WorkoutGuide.Status.PENDING,
		)

		self.client.force_login(self.admin)
		resp = self.client.post(reverse('admin.approve_guide', kwargs={'guide_id': guide.id}))
		self.assertEqual(resp.status_code, 302)
		guide.refresh_from_db()
		self.assertEqual(guide.status, WorkoutGuide.Status.APPROVED)
		self.assertEqual(guide.rejection_reason, '')

	def test_admin_reject_guide_flow(self):
		guide = WorkoutGuide.objects.create(
			name='Review Program 2',
			category='Strength',
			difficulty_level='Beginner',
			duration_weeks=4,
			trainer=self.trainer_user,
			status=WorkoutGuide.Status.PENDING,
		)

		self.client.force_login(self.admin)
		resp = self.client.post(reverse('admin.reject_guide', kwargs={'guide_id': guide.id}), data={'reason': ''})
		self.assertEqual(resp.status_code, 302)
		guide.refresh_from_db()
		self.assertEqual(guide.status, WorkoutGuide.Status.PENDING)

		resp = self.client.post(reverse('admin.reject_guide', kwargs={'guide_id': guide.id}), data={'reason': 'Incorrect form tip.'})
		self.assertEqual(resp.status_code, 302)
		guide.refresh_from_db()
		self.assertEqual(guide.status, WorkoutGuide.Status.REJECTED)
		self.assertEqual(guide.rejection_reason, 'Incorrect form tip.')

	def test_admin_change_member_password(self):
		# 1. Admin logs in and changes member's password successfully
		self.client.force_login(self.admin)
		resp = self.client.post(
			reverse('member.change_password', kwargs={'member_id': self.member.id}),
			data={'password': 'NewSecurePassword123', 'confirm_password': 'NewSecurePassword123'},
		)
		self.assertEqual(resp.status_code, 302)
		self.member.user.refresh_from_db()
		self.assertTrue(self.member.user.check_password('NewSecurePassword123'))

		# 2. Admin enters mismatching passwords
		resp = self.client.post(
			reverse('member.change_password', kwargs={'member_id': self.member.id}),
			data={'password': 'Password123', 'confirm_password': 'MismatchingPassword'},
		)
		self.assertEqual(resp.status_code, 302)

		# 3. Trainer (non-admin/staff) is blocked
		self.client.force_login(self.trainer_user)
		resp = self.client.post(
			reverse('member.change_password', kwargs={'member_id': self.member.id}),
			data={'password': 'Password123', 'confirm_password': 'Password123'},
		)
		self.assertEqual(resp.status_code, 302)

