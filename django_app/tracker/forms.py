from django import forms
from .models import Member, Workout, DietPlan, MealPlan, WorkoutGuide, WorkoutTip, FitnessMetric, GuideAssignment, DietAssignment, GuestVisit

class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            'phone_number',
            'date_of_birth',
            'gender',
            'emergency_contact',
            'member_tier',
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


class MemberProfileForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            'phone_number',
            'date_of_birth',
            'gender',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
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


class GuideAssignmentForm(forms.Form):
    """Form for assigning workout guides to members with validation."""
    guide_id = forms.IntegerField(required=True)
    notes = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    target_completion_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        target_completion_date = cleaned_data.get('target_completion_date')

        if start_date and target_completion_date and target_completion_date <= start_date:
            raise forms.ValidationError('Target completion date must be after start date.')

        return cleaned_data


class DietAssignmentForm(forms.Form):
    """Form for assigning diet plans to members with validation."""
    diet_plan_id = forms.IntegerField(required=True)
    notes = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    target_end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        target_end_date = cleaned_data.get('target_end_date')

        if start_date and target_end_date and target_end_date <= start_date:
            raise forms.ValidationError('End date must be after start date.')

        return cleaned_data


class GuestVisitForm(forms.ModelForm):
    class Meta:
        model = GuestVisit
        fields = ['full_name', 'guest_type', 'email', 'phone_number', 'amount_paid', 'emergency_contact', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional visitor notes...'}),
        }

