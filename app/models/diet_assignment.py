from app import db
from datetime import datetime, timedelta

class DietAssignment(db.Model):
    """Tracks when a trainer assigns a diet plan to a member."""
    __tablename__ = 'diet_assignments'

    id = db.Column(db.Integer, primary_key=True)
    diet_plan_id = db.Column(db.Integer, db.ForeignKey('diet_plans.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Trainer who assigned
    assignment_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    start_date = db.Column(db.DateTime, nullable=True)
    target_end_date = db.Column(db.DateTime, nullable=True)  # Expected diet end date
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text, nullable=True)  # Trainer notes about compliance, adjustments, etc.
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    member = db.relationship('Member', backref='diet_assignments')
    trainer = db.relationship('User', backref='assigned_diets')

    def __repr__(self):
        return f'<DietAssignment diet={self.diet_plan_id}, member={self.member_id}>'

    @staticmethod
    def get_active_diet(member_id):
        """Get the currently active diet assignment for a member."""
        return DietAssignment.query.filter_by(
            member_id=member_id,
            is_active=True
        ).first()

    @staticmethod
    def get_diet_history(member_id):
        """Get all past diet assignments for a member."""
        return DietAssignment.query.filter_by(
            member_id=member_id
        ).order_by(DietAssignment.start_date.desc()).all()

    @staticmethod
    def get_assignments_by_trainer(trainer_id):
        """Get all diet assignments made by a trainer."""
        return DietAssignment.query.filter_by(
            trainer_id=trainer_id,
            is_active=True
        ).order_by(DietAssignment.assignment_date.desc()).all()

    def calculate_adherence(self):
        """Calculate adherence percentage based on logged meals vs. expected."""
        if not self.start_date:
            return 0

        days_active = (datetime.utcnow() - self.start_date).days
        if days_active <= 0:
            return 0

        # Get all meal logs for this assignment
        meal_logs = MealLog.query.filter(
            MealLog.member_id == self.member_id,
            MealLog.meal_date >= self.start_date.date()
        ).all()

        if days_active == 0:
            return 0

        # Adherence = logged days / total days
        days_with_logs = len(set(log.meal_date for log in meal_logs))
        adherence = min(100, int((days_with_logs / days_active) * 100))

        return adherence

    def get_calorie_burn_recommendation(self):
        """Get recommended calorie burn based on member's assigned workouts."""
        # This will be called after calculating from workouts
        # For now, provide a default based on typical gym attendance
        from app.models.attendance import Attendance

        # Check attendance in last 7 days
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_checkins = Attendance.query.filter(
            Attendance.member_id == self.member_id,
            Attendance.check_in_time >= seven_days_ago
        ).count()

        # Estimate calorie burn based on workout frequency
        workouts_per_week = recent_checkins
        calories_per_workout = 300  # Conservative estimate

        estimated_burn = workouts_per_week * calories_per_workout

        return estimated_burn

    def deactivate(self):
        """End the diet assignment."""
        self.is_active = False
        self.updated_at = datetime.utcnow()
        db.session.commit()


class MealLog(db.Model):
    """Tracks meals logged by a member against their assigned diet plan."""
    __tablename__ = 'meal_logs'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    diet_assignment_id = db.Column(db.Integer, db.ForeignKey('diet_assignments.id'), nullable=True)  # Link to diet assignment
    meal_plan_id = db.Column(db.Integer, db.ForeignKey('meal_plans.id'), nullable=True)  # Reference to meal plan suggestion
    meal_date = db.Column(db.Date, nullable=False)  # Date of the meal
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner, snack
    meal_name = db.Column(db.String(200), nullable=False)
    calories_actual = db.Column(db.Integer, nullable=True)
    protein_g = db.Column(db.Float, nullable=True)
    carbs_g = db.Column(db.Float, nullable=True)
    fats_g = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    member = db.relationship('Member', backref='meal_logs')
    diet_assignment = db.relationship('DietAssignment', backref='meal_logs')
    suggested_meal = db.relationship('MealPlan')

    def __repr__(self):
        return f'<MealLog {self.meal_name} - {self.meal_date}>'

    @staticmethod
    def get_daily_logs(member_id, meal_date):
        """Get all meal logs for a member on a specific date."""
        return MealLog.query.filter_by(
            member_id=member_id,
            meal_date=meal_date
        ).order_by(MealLog.created_at.asc()).all()

    @staticmethod
    def get_date_range_logs(member_id, start_date, end_date):
        """Get meal logs within a date range."""
        return MealLog.query.filter(
            MealLog.member_id == member_id,
            MealLog.meal_date >= start_date,
            MealLog.meal_date <= end_date
        ).order_by(MealLog.meal_date.desc()).all()

    @staticmethod
    def calculate_daily_calories(member_id, meal_date):
        """Calculate total calories consumed on a specific date."""
        logs = MealLog.get_daily_logs(member_id, meal_date)
        return sum(log.calories_actual or 0 for log in logs)

    @staticmethod
    def calculate_daily_macros(member_id, meal_date):
        """Calculate total macros for a specific date."""
        logs = MealLog.get_daily_logs(member_id, meal_date)
        return {
            'protein_g': sum(log.protein_g or 0 for log in logs),
            'carbs_g': sum(log.carbs_g or 0 for log in logs),
            'fats_g': sum(log.fats_g or 0 for log in logs),
            'calories': sum(log.calories_actual or 0 for log in logs)
        }

    @staticmethod
    def get_adherence_score(member_id, diet_assignment_id, days=7):
        """Calculate adherence score for last N days."""
        start_date = (datetime.utcnow() - timedelta(days=days)).date()
        logs = MealLog.query.filter(
            MealLog.member_id == member_id,
            MealLog.diet_assignment_id == diet_assignment_id,
            MealLog.meal_date >= start_date
        ).all()

        # Days with at least one meal logged
        days_logged = len(set(log.meal_date for log in logs))

        adherence = min(100, int((days_logged / days) * 100))
        return adherence

    @staticmethod
    def get_weekly_average_calories(member_id, weeks_back=4):
        """Get weekly average calorie consumption."""
        start_date = (datetime.utcnow() - timedelta(weeks=weeks_back)).date()
        logs = MealLog.query.filter(
            MealLog.member_id == member_id,
            MealLog.meal_date >= start_date
        ).all()

        if not logs:
            return 0

        # Group by week and calculate average
        from collections import defaultdict
        weekly_totals = defaultdict(int)

        for log in logs:
            week_num = log.meal_date.isocalendar()[1]
            weekly_totals[week_num] += log.calories_actual or 0

        if weekly_totals:
            return int(sum(weekly_totals.values()) / len(weekly_totals))

        return 0
