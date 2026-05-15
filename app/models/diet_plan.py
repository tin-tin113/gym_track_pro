from app import db
from datetime import datetime

class DietPlan(db.Model):
    """Pre-made nutrition/diet plans that trainers can assign to members."""
    __tablename__ = 'diet_plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    diet_type = db.Column(db.String(50), nullable=False)  # calorie_deficit, maintenance, surplus, keto, balanced, etc.
    daily_calories = db.Column(db.Integer, nullable=True)  # Target daily calories
    macro_ratio_protein = db.Column(db.Float, nullable=True, default=0.30)  # 0.30 = 30%
    macro_ratio_carbs = db.Column(db.Float, nullable=True, default=0.45)
    macro_ratio_fats = db.Column(db.Float, nullable=True, default=0.25)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Admin/Staff who created
    notes = db.Column(db.Text, nullable=True)  # General notes about the diet
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meal_plans = db.relationship('MealPlan', backref='diet', lazy=True, cascade='all, delete-orphan')
    assignments = db.relationship('DietAssignment', backref='diet', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<DietPlan {self.name}>'

    @staticmethod
    def get_available_plans():
        """Get all active diet plans available for assignment."""
        return DietPlan.query.filter_by(is_active=True).order_by(DietPlan.name.asc()).all()

    @staticmethod
    def get_by_type(diet_type):
        """Get diet plans by type."""
        return DietPlan.query.filter_by(diet_type=diet_type, is_active=True).all()

    @staticmethod
    def get_recommended_for_goal(goal):
        """Get recommended diet plan based on fitness goal."""
        goal_map = {
            'weight_loss': 'calorie_deficit',
            'muscle_gain': 'surplus',
            'tone': 'balanced',
            'maintenance': 'maintenance'
        }
        diet_type = goal_map.get(goal.lower(), 'balanced')
        return DietPlan.query.filter_by(diet_type=diet_type, is_active=True).all()

    def get_macros_from_calories(self, total_calories=None):
        """Calculate macros based on ratio and total calories."""
        cal = total_calories or self.daily_calories or 2000

        protein_cals = cal * self.macro_ratio_protein
        carbs_cals = cal * self.macro_ratio_carbs
        fats_cals = cal * self.macro_ratio_fats

        return {
            'protein_g': round(protein_cals / 4),  # 4 cal per gram
            'carbs_g': round(carbs_cals / 4),
            'fats_g': round(fats_cals / 9)  # 9 cal per gram
        }

    def get_daily_meals_total(self):
        """Get total calories and macros for all meals in plan (weekly)."""
        daily_total = {
            'calories': 0,
            'protein_g': 0,
            'carbs_g': 0,
            'fats_g': 0
        }

        # Get unique days and sum
        days = set()
        for meal in self.meal_plans:
            if meal.day_name not in days:
                daily_total['calories'] += meal.calories or 0
                daily_total['protein_g'] += meal.protein_g or 0
                daily_total['carbs_g'] += meal.carbs_g or 0
                daily_total['fats_g'] += meal.fats_g or 0
                days.add(meal.day_name)

        # Average per day
        if len(days) > 0:
            daily_total['calories'] = round(daily_total['calories'] / len(days))
            daily_total['protein_g'] = round(daily_total['protein_g'] / len(days))
            daily_total['carbs_g'] = round(daily_total['carbs_g'] / len(days))
            daily_total['fats_g'] = round(daily_total['fats_g'] / len(days))

        return daily_total

    def get_meals_for_day(self, day_name):
        """Get all meals for a specific day."""
        return MealPlan.query.filter_by(diet_plan_id=self.id, day_name=day_name).all()

    def deactivate(self):
        """Deactivate the diet plan."""
        self.is_active = False
        self.updated_at = datetime.utcnow()
        db.session.commit()


class MealPlan(db.Model):
    """Individual meals that are part of a diet plan (e.g., Monday breakfast, etc.)"""
    __tablename__ = 'meal_plans'

    id = db.Column(db.Integer, primary_key=True)
    diet_plan_id = db.Column(db.Integer, db.ForeignKey('diet_plans.id'), nullable=False)
    day_name = db.Column(db.String(20), nullable=False)  # Monday, Tuesday, etc. (or Daily for all days)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner, snack
    meal_name = db.Column(db.String(200), nullable=False)
    calories = db.Column(db.Integer, nullable=True)
    protein_g = db.Column(db.Float, nullable=True)
    carbs_g = db.Column(db.Float, nullable=True)
    fats_g = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)  # Preparation notes, portions, etc.
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<MealPlan {self.meal_name}>'

    @staticmethod
    def get_daily_total_calories(diet_plan_id, day_name='Daily'):
        """Get total calories for a day."""
        meals = MealPlan.query.filter_by(diet_plan_id=diet_plan_id, day_name=day_name).all()
        return sum(meal.calories or 0 for meal in meals)

    @staticmethod
    def get_daily_macros(diet_plan_id, day_name='Daily'):
        """Get total macros for a day."""
        meals = MealPlan.query.filter_by(diet_plan_id=diet_plan_id, day_name=day_name).all()
        return {
            'protein_g': sum(meal.protein_g or 0 for meal in meals),
            'carbs_g': sum(meal.carbs_g or 0 for meal in meals),
            'fats_g': sum(meal.fats_g or 0 for meal in meals)
        }

    def get_macros_for_meal(self):
        """Get macros for this meal as dict."""
        return {
            'protein_g': self.protein_g or 0,
            'carbs_g': self.carbs_g or 0,
            'fats_g': self.fats_g or 0,
            'calories': self.calories or 0
        }
