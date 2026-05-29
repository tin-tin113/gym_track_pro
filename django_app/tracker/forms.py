from django import forms
from .models import Member, Workout, DietPlan, MealPlan, WorkoutGuide, WorkoutTip, FitnessMetric

class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            'phone_number',
            'date_of_birth',
            'gender',
            'emergency_contact',
            'membership_type',
            'membership_start_date',
            'membership_expiry_date',
            'profile_image_url',
            'notes',
            'is_active',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'membership_start_date': forms.DateInput(attrs={'type': 'date'}),
            'membership_expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }


class WorkoutForm(forms.ModelForm):
    class Meta:
        model = Workout
        fields = [
            'workout_date',
            'exercise_name',
            'exercise_category',
            'sets',
            'reps',
            'weight',
            'duration_minutes',
            'distance_km',
            'intensity',
            'notes',
        ]
        widgets = {
            'workout_date': forms.DateInput(attrs={'type': 'date'}),
        }


class DietPlanForm(forms.ModelForm):
    class Meta:
        model = DietPlan
        fields = [
            'name',
            'description',
            'diet_type',
            'daily_calories',
            'macro_ratio_protein',
            'macro_ratio_carbs',
            'macro_ratio_fats',
            'notes',
            'is_active',
        ]


class MealPlanForm(forms.ModelForm):
    class Meta:
        model = MealPlan
        fields = [
            'day_name',
            'meal_type',
            'meal_name',
            'calories',
            'protein_g',
            'carbs_g',
            'fats_g',
            'notes',
        ]


class WorkoutGuideForm(forms.ModelForm):
    class Meta:
        model = WorkoutGuide
        fields = [
            'name',
            'description',
            'category',
            'difficulty_level',
            'duration_weeks',
            'target_goals',
            'equipment_needed',
            'image',
            'status',
        ]


class WorkoutTipForm(forms.ModelForm):
    class Meta:
        model = WorkoutTip
        fields = [
            'exercise_name',
            'tip_category',
            'content',
            'order',
        ]


class FitnessMetricForm(forms.ModelForm):
    class Meta:
        model = FitnessMetric
        fields = [
            'metric_date',
            'weight',
            'height',
            'bmi',
            'chest',
            'waist',
            'hips',
            'bicep',
            'thigh',
            'body_fat_percentage',
            'muscle_mass',
            'notes',
        ]
        widgets = {
            'metric_date': forms.DateInput(attrs={'type': 'date'}),
        }
