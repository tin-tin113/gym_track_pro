from django.contrib import admin

from .models import (
	Attendance,
	DietAssignment,
	DietPlan,
	FitnessMetric,
	GuideAssignment,
	MealLog,
	MealPlan,
	Member,
	Subscription,
	Trainer,
	TrainerAssignment,
	User,
	Workout,
	WorkoutGuide,
	WorkoutTip,
)


admin.site.register(User)
admin.site.register(Member)
admin.site.register(Subscription)
admin.site.register(Trainer)
admin.site.register(TrainerAssignment)

admin.site.register(Attendance)
admin.site.register(FitnessMetric)

admin.site.register(WorkoutGuide)
admin.site.register(WorkoutTip)
admin.site.register(GuideAssignment)
admin.site.register(Workout)

admin.site.register(DietPlan)
admin.site.register(MealPlan)
admin.site.register(DietAssignment)
admin.site.register(MealLog)

# Register your models here.
