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
	role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER, db_index=True)
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
		MONTHLY = 'monthly', 'Monthly'
		QUARTERLY = 'quarterly', 'Quarterly'
		ANNUAL = 'annual', 'Annual'

	class MemberTier(models.TextChoices):
		STUDENT = 'student', 'Student'
		REGULAR = 'regular', 'Regular'

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='member_profile')
	date_of_birth = models.DateField(blank=True, null=True)
	gender = models.CharField(max_length=10, blank=True)
	phone_number = models.CharField(max_length=20, blank=True)
	emergency_contact = models.CharField(max_length=120, blank=True)
	member_tier = models.CharField(
		max_length=20,
		choices=MemberTier.choices,
		default=MemberTier.REGULAR,
	)
	membership_type = models.CharField(
		max_length=20,
		choices=MembershipType.choices,
		default=MembershipType.MONTHLY,
	)
	membership_start_date = models.DateField()
	membership_expiry_date = models.DateField()
	pending_renewal_plan = models.CharField(
		max_length=20,
		choices=MembershipType.choices,
		blank=True,
		null=True,
	)
	consecutive_rejections = models.IntegerField(default=0)
	last_rejection_date = models.DateTimeField(blank=True, null=True)
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

	@property
	def active_subscriptions(self):
		from django.utils import timezone
		return self.subscriptions.filter(is_active=True, expiry_date__gte=timezone.localdate()).order_by('expiry_date')

	def update_membership_from_subscriptions(self):
		from django.utils import timezone
		today = timezone.localdate()
		active_subs = self.subscriptions.filter(is_active=True, expiry_date__gte=today)
		if active_subs.exists():
			latest_sub = active_subs.order_by('-expiry_date').first()
			self.membership_type = latest_sub.subscription_type
			self.membership_expiry_date = latest_sub.expiry_date
			self.membership_start_date = latest_sub.start_date
			self.is_active = True
		else:
			latest_sub = self.subscriptions.order_by('-expiry_date').first()
			if latest_sub:
				self.membership_type = latest_sub.subscription_type
				self.membership_expiry_date = latest_sub.expiry_date
				self.membership_start_date = latest_sub.start_date

	def save(self, *args, **kwargs):
		super().save(*args, **kwargs)
		if self.membership_start_date and self.membership_expiry_date:
			sub = Subscription.objects.filter(
				member=self,
				subscription_type=self.membership_type,
			).order_by('-expiry_date').first()
			if sub:
				sub.start_date = self.membership_start_date
				sub.expiry_date = self.membership_expiry_date
				sub.is_active = self.is_active
				sub.save()
			else:
				Subscription.objects.create(
					member=self,
					subscription_type=self.membership_type,
					start_date=self.membership_start_date,
					expiry_date=self.membership_expiry_date,
					is_active=self.is_active
				)


class Subscription(models.Model):
	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='subscriptions')
	subscription_type = models.CharField(
		max_length=20,
		choices=Member.MembershipType.choices,
		default=Member.MembershipType.MONTHLY,
	)
	start_date = models.DateField()
	expiry_date = models.DateField()
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"{self.member} - {self.get_subscription_type_display()} ({self.start_date} to {self.expiry_date})"

	def is_subscription_active(self) -> bool:
		from django.utils import timezone
		if not self.is_active:
			return False
		return self.expiry_date >= timezone.localdate()



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
	image = models.ImageField(upload_to='guide_images/', blank=True, null=True)
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

	def is_expiring_soon(self, days: int = 7) -> bool:
		"""Check if guide assignment is expiring within specified days."""
		from django.utils import timezone

		if self.is_completed or not self.target_completion_date:
			return False
		now = timezone.now()
		time_until_expiry = (self.target_completion_date - now).days
		return 0 <= time_until_expiry <= days

	def days_until_expiry(self) -> int | None:
		"""Get days until target completion date."""
		from django.utils import timezone

		if not self.target_completion_date:
			return None
		return (self.target_completion_date.date() - timezone.localdate()).days

	def get_start_date_as_date(self):
		"""Convert start_date to date object for template convenience."""
		return self.start_date.date() if self.start_date else None

	def get_target_completion_as_date(self):
		"""Convert target_completion_date to date object for template convenience."""
		return self.target_completion_date.date() if self.target_completion_date else None


class Workout(models.Model):
	class Intensity(models.TextChoices):
		LIGHT = 'light', 'Light'
		MODERATE = 'moderate', 'Moderate'
		INTENSE = 'intense', 'Intense'

	class MuscleGroup(models.TextChoices):
		CHEST = 'chest', 'Chest'
		BACK = 'back', 'Back'
		SHOULDERS = 'shoulders', 'Shoulders'
		ARMS = 'arms', 'Arms'
		LEGS = 'legs', 'Legs'
		CORE = 'core', 'Core'
		FULL_BODY = 'full_body', 'Full Body'
		CARDIO = 'cardio', 'Cardio'
		OTHER = 'other', 'Other'

	member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='workouts')
	workout_date = models.DateField()
	exercise_name = models.CharField(max_length=120)
	exercise_category = models.CharField(max_length=50)
	muscle_group = models.CharField(
		max_length=20,
		choices=MuscleGroup.choices,
		default=MuscleGroup.OTHER,
		blank=True
	)

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

	def get_volume(self) -> float:
		if self.sets_list.exists():
			return sum((s.reps or 0) * (s.weight or 0.0) for s in self.sets_list.all() if s.is_completed)
		return float((self.sets or 0) * (self.reps or 0) * (self.weight or 0.0))

	def get_max_weight(self) -> float:
		if self.sets_list.exists():
			completed = [s for s in self.sets_list.all() if s.is_completed]
			if completed:
				return max(s.weight for s in completed)
			return 0.0
		return self.weight or 0.0

	def get_max_estimated_1rm(self) -> float:
		if self.sets_list.exists():
			completed = [s for s in self.sets_list.all() if s.is_completed and s.reps and s.weight]
			if completed:
				return max(s.weight * (1 + s.reps / 30.0) for s in completed)
			return 0.0
		if self.reps and self.weight:
			return self.weight * (1 + self.reps / 30.0)
		return 0.0


class WorkoutSet(models.Model):
	class SetType(models.TextChoices):
		WARMUP = 'warmup', 'Warm-up'
		WORKING = 'working', 'Working'
		DROP = 'drop', 'Drop Set'

	workout = models.ForeignKey(Workout, on_delete=models.CASCADE, related_name='sets_list')
	set_number = models.IntegerField()
	reps = models.IntegerField()
	weight = models.FloatField()
	set_type = models.CharField(max_length=15, choices=SetType.choices, default=SetType.WORKING)
	is_completed = models.BooleanField(default=False)
	# PR detection — True when this set was a new personal record at the time it was logged
	is_pr = models.BooleanField(default=False)
	# Trainer coaching notes specific to this individual set
	trainer_notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.workout.exercise_name} Set {self.set_number}: {self.weight}kg x {self.reps}"



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

	def is_expiring_soon(self, days: int = 7) -> bool:
		"""Check if diet assignment is expiring within specified days."""
		from django.utils import timezone

		if not self.is_active or not self.target_end_date:
			return False
		now = timezone.now()
		time_until_expiry = (self.target_end_date - now).days
		return 0 <= time_until_expiry <= days

	def days_until_expiry(self) -> int | None:
		"""Get days until target end date."""
		from django.utils import timezone

		if not self.target_end_date:
			return None
		return (self.target_end_date.date() - timezone.localdate()).days

	def get_start_date_as_date(self):
		"""Convert start_date to date object for template convenience."""
		return self.start_date.date() if self.start_date else None

	def get_target_end_as_date(self):
		"""Convert target_end_date to date object for template convenience."""
		return self.target_end_date.date() if self.target_end_date else None


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


class GuestVisit(models.Model):
	class GuestType(models.TextChoices):
		STUDENT = 'student', 'Student'
		REGULAR = 'regular', 'Regular'

	full_name = models.CharField(max_length=120)
	guest_type = models.CharField(
		max_length=20,
		choices=GuestType.choices,
		default=GuestType.REGULAR,
	)
	email = models.EmailField(blank=True, null=True)
	phone_number = models.CharField(max_length=20, blank=True)
	visit_date = models.DateField(db_index=True)
	amount_paid = models.FloatField(default=100.0)
	emergency_contact = models.CharField(max_length=120, blank=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.full_name} on {self.visit_date}"
