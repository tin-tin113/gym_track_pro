from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
	class Role(models.TextChoices):
		ADMIN = 'admin', 'Administrator'
		STAFF = 'staff', 'Staff'
		TRAINER = 'trainer', 'Trainer'
		MEMBER = 'member', 'Member'

	full_name = models.CharField(max_length=120, blank=True)
	role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
	setup_token = models.CharField(max_length=255, blank=True, null=True)
	setup_token_expiry = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return self.username

	@property
	def is_admin(self) -> bool:
		return self.role == self.Role.ADMIN

	@property
	def member(self):
		return getattr(self, 'member_profile', None)

	@property
	def trainer(self):
		return getattr(self, 'trainer_profile', None)


class Trainer(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trainer_profile')
	specialization = models.TextField(blank=True)
	certifications = models.TextField(blank=True)
	bio = models.TextField(blank=True)
	phone_number = models.CharField(max_length=20, blank=True)
	profile_image_url = models.CharField(max_length=255, blank=True)
	hourly_rate = models.FloatField(blank=True, null=True)
	years_experience = models.IntegerField(blank=True, null=True)
	max_clients = models.IntegerField(default=10)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	@property
	def certification(self) -> str:
		return self.certifications

	def __str__(self) -> str:
		return self.user.full_name or self.user.username

	def is_at_capacity(self) -> bool:
		# Avoid importing Member at module level; use reverse relation.
		try:
			active_count = self.user.members_assigned.filter(is_active=True, is_approved=True).count()
		except Exception:
			active_count = 0
		return active_count >= (self.max_clients or 0)


class Member(models.Model):
	class MembershipType(models.TextChoices):
		DAILY = 'daily', 'Daily'
		MONTHLY = 'monthly', 'Monthly'
		QUARTERLY = 'quarterly', 'Quarterly'
		ANNUAL = 'annual', 'Annual'

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='member_profile')
	date_of_birth = models.DateField(blank=True, null=True)
	gender = models.CharField(max_length=10, blank=True)
	phone_number = models.CharField(max_length=20, blank=True)
	emergency_contact = models.CharField(max_length=120, blank=True)
	membership_type = models.CharField(
		max_length=20,
		choices=MembershipType.choices,
		default=MembershipType.MONTHLY,
	)
	membership_start_date = models.DateField()
	membership_expiry_date = models.DateField()
	assigned_trainer = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name='members_assigned',
	)
	profile_image_url = models.CharField(max_length=255, blank=True)
	notes = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)
	is_approved = models.BooleanField(default=False)
	approval_date = models.DateTimeField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return self.user.full_name or self.user.username

	def is_membership_active(self) -> bool:
		from django.utils import timezone

		if not self.is_active:
			return False
		if not self.membership_expiry_date:
			return False
		return self.membership_expiry_date >= timezone.localdate()

	def days_until_expiry(self) -> int:
		from django.utils import timezone

		if not self.membership_expiry_date:
			return 0
		return (self.membership_expiry_date - timezone.localdate()).days

	def is_membership_expiring_soon(self) -> bool:
		# Template expects no args; default to 7 days.
		days_left = self.days_until_expiry()
		return 0 <= days_left <= 7

	def days_since_last_visit(self) -> int | None:
		"""Template helper used on trainer dashboard."""
		from django.utils import timezone

		last = self.attendance_records.order_by('-check_in_time').values_list('check_in_time', flat=True).first()
		if not last:
			return None
		return (timezone.now() - last).days


class TrainerAssignment(models.Model):
	class AssignmentType(models.TextChoices):
		PRIMARY = 'primary', 'Primary'
		SECONDARY = 'secondary', 'Secondary'
		TEMPORARY = 'temporary', 'Temporary'

	trainer = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='trainer_assignments',
	)
	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='trainer_assignments')
	assignment_date = models.DateField()
	start_date = models.DateField()
	end_date = models.DateField(blank=True, null=True)
	assignment_type = models.CharField(max_length=20, choices=AssignmentType.choices, default=AssignmentType.PRIMARY)
	is_active = models.BooleanField(default=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"{self.trainer_id} -> {self.member_id}"


class Attendance(models.Model):
	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='attendance_records')
	check_in_time = models.DateTimeField(db_index=True)
	check_out_time = models.DateTimeField(blank=True, null=True)
	duration_minutes = models.IntegerField(blank=True, null=True)
	qr_code = models.CharField(max_length=100, unique=True, blank=True, null=True, db_index=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.member_id} at {self.check_in_time}"


class FitnessMetric(models.Model):
	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='fitness_metrics')
	metric_date = models.DateField()
	weight = models.FloatField(blank=True, null=True)
	height = models.FloatField(blank=True, null=True)
	bmi = models.FloatField(blank=True, null=True)
	chest = models.FloatField(blank=True, null=True)
	waist = models.FloatField(blank=True, null=True)
	hips = models.FloatField(blank=True, null=True)
	bicep = models.FloatField(blank=True, null=True)
	thigh = models.FloatField(blank=True, null=True)
	body_fat_percentage = models.FloatField(blank=True, null=True)
	muscle_mass = models.FloatField(blank=True, null=True)
	notes = models.TextField(blank=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name='fitness_records_created',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.member_id} on {self.metric_date}"

	def get_bmi_classification(self) -> str:
		bmi = self.bmi
		if bmi is None and self.weight and self.height:
			# height stored in cm in the original UI
			height_m = self.height / 100.0
			if height_m > 0:
				bmi = self.weight / (height_m * height_m)
		if bmi is None:
			return 'Unknown'
		if bmi < 18.5:
			return 'Underweight'
		if bmi < 25:
			return 'Normal'
		if bmi < 30:
			return 'Overweight'
		return 'Obese'


class WorkoutGuide(models.Model):
	class Status(models.TextChoices):
		DRAFT = 'draft', 'Draft'
		PENDING = 'pending', 'Pending'
		APPROVED = 'approved', 'Approved'
		REJECTED = 'rejected', 'Rejected'

	name = models.CharField(max_length=150)
	description = models.TextField(blank=True)
	category = models.CharField(max_length=50)
	difficulty_level = models.CharField(max_length=20, default='Intermediate')
	duration_weeks = models.IntegerField(blank=True, null=True)
	target_goals = models.CharField(max_length=300, blank=True)
	equipment_needed = models.CharField(max_length=300, blank=True)
	trainer = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name='workout_guides_created',
	)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
	rejection_reason = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return self.name

	def get_target_goals(self) -> list[str]:
		"""Template helper: split stored target_goals into a list."""
		raw = (self.target_goals or '').strip()
		if not raw:
			return []
		return [p.strip() for p in raw.replace(';', ',').split(',') if p.strip()]

	def get_equipment(self) -> list[str]:
		"""Template helper: split stored equipment_needed into a list."""
		raw = (self.equipment_needed or '').strip()
		if not raw:
			return []
		return [p.strip() for p in raw.replace(';', ',').split(',') if p.strip()]


class WorkoutTip(models.Model):
	guide = models.ForeignKey(WorkoutGuide, on_delete=models.CASCADE, related_name='tips')
	exercise_name = models.CharField(max_length=150)
	tip_category = models.CharField(max_length=50)
	content = models.TextField()
	order = models.IntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"{self.exercise_name} - {self.tip_category}"


class GuideAssignment(models.Model):
	guide = models.ForeignKey(WorkoutGuide, on_delete=models.CASCADE, related_name='assignments')
	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='guide_assignments')
	trainer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assigned_guides')
	assignment_date = models.DateTimeField(auto_now_add=True)
	start_date = models.DateTimeField(blank=True, null=True)
	target_completion_date = models.DateTimeField(blank=True, null=True)
	is_completed = models.BooleanField(default=False)
	completion_date = models.DateTimeField(blank=True, null=True)
	notes = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"guide={self.guide_id}, member={self.member_id}"

	def calculate_progress(self) -> int:
		"""Template helper used in member dashboard.

		Falls back to time-based progress when no explicit completion exists.
		"""
		from django.utils import timezone

		if self.is_completed:
			return 100
		if self.start_date and self.target_completion_date and self.target_completion_date > self.start_date:
			now = timezone.now()
			total = (self.target_completion_date - self.start_date).total_seconds()
			elapsed = (now - self.start_date).total_seconds()
			pct = int(max(0.0, min(1.0, elapsed / total)) * 100)
			return pct
		return 0


class Workout(models.Model):
	class Intensity(models.TextChoices):
		LIGHT = 'light', 'Light'
		MODERATE = 'moderate', 'Moderate'
		INTENSE = 'intense', 'Intense'

	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='workouts')
	workout_date = models.DateField()
	exercise_name = models.CharField(max_length=120)
	exercise_category = models.CharField(max_length=50)

	sets = models.IntegerField(blank=True, null=True)
	reps = models.IntegerField(blank=True, null=True)
	weight = models.FloatField(blank=True, null=True)

	duration_minutes = models.IntegerField(blank=True, null=True)
	distance_km = models.FloatField(blank=True, null=True)

	intensity = models.CharField(max_length=20, choices=Intensity.choices, default=Intensity.MODERATE)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	trainer = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name='workouts_assigned',
	)
	assigned_date = models.DateTimeField(blank=True, null=True)

	guide = models.ForeignKey(WorkoutGuide, on_delete=models.SET_NULL, blank=True, null=True, related_name='workouts')
	guide_assignment = models.ForeignKey(
		GuideAssignment,
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name='workouts_logged',
	)

	def __str__(self) -> str:
		return f"{self.exercise_name} on {self.workout_date}"


class DietPlan(models.Model):
	name = models.CharField(max_length=150)
	description = models.TextField(blank=True)
	diet_type = models.CharField(max_length=50)
	daily_calories = models.IntegerField(blank=True, null=True)
	macro_ratio_protein = models.FloatField(default=0.30, blank=True, null=True)
	macro_ratio_carbs = models.FloatField(default=0.45, blank=True, null=True)
	macro_ratio_fats = models.FloatField(default=0.25, blank=True, null=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name='diet_plans_created',
	)
	notes = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return self.name


class MealPlan(models.Model):
	diet_plan = models.ForeignKey(DietPlan, on_delete=models.CASCADE, related_name='meal_plans')
	day_name = models.CharField(max_length=20)
	meal_type = models.CharField(max_length=20)
	meal_name = models.CharField(max_length=200)
	calories = models.IntegerField(blank=True, null=True)
	protein_g = models.FloatField(blank=True, null=True)
	carbs_g = models.FloatField(blank=True, null=True)
	fats_g = models.FloatField(blank=True, null=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return self.meal_name


class DietAssignment(models.Model):
	diet_plan = models.ForeignKey(DietPlan, on_delete=models.CASCADE, related_name='assignments')
	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='diet_assignments')
	trainer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assigned_diets')
	assignment_date = models.DateTimeField(auto_now_add=True)
	start_date = models.DateTimeField(blank=True, null=True)
	target_end_date = models.DateTimeField(blank=True, null=True)
	is_active = models.BooleanField(default=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"diet={self.diet_plan_id}, member={self.member_id}"

	@property
	def diet(self) -> DietPlan:
		"""Template compatibility: Flask templates refer to assignment.diet.*"""
		return self.diet_plan


class MealLog(models.Model):
	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='meal_logs')
	diet_assignment = models.ForeignKey(
		DietAssignment,
		on_delete=models.SET_NULL,
		blank=True,
		null=True,
		related_name='meal_logs',
	)
	meal_plan = models.ForeignKey(MealPlan, on_delete=models.SET_NULL, blank=True, null=True, related_name='meal_logs')
	meal_date = models.DateField()
	meal_type = models.CharField(max_length=20)
	meal_name = models.CharField(max_length=200)
	calories_actual = models.IntegerField(blank=True, null=True)
	protein_g = models.FloatField(blank=True, null=True)
	carbs_g = models.FloatField(blank=True, null=True)
	fats_g = models.FloatField(blank=True, null=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"{self.meal_name} - {self.meal_date}"
