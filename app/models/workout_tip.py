from app import db
from datetime import datetime

class WorkoutTip(db.Model):
    """Exercise tips and guidance for proper form, recovery, nutrition, etc."""
    __tablename__ = 'workout_tips'

    id = db.Column(db.Integer, primary_key=True)
    guide_id = db.Column(db.Integer, db.ForeignKey('workout_guides.id'), nullable=False)
    exercise_name = db.Column(db.String(150), nullable=False)  # e.g., "Bench Press", "Squats"
    tip_category = db.Column(db.String(50), nullable=False)  # form, recovery, nutrition, mental
    content = db.Column(db.Text, nullable=False)  # The actual tip text
    order = db.Column(db.Integer, nullable=True, default=0)  # Display order
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<WorkoutTip {self.exercise_name} - {self.tip_category}>'

    @staticmethod
    def get_tips_for_exercise(guide_id, exercise_name):
        """Get all tips for a specific exercise in a guide."""
        return WorkoutTip.query.filter_by(
            guide_id=guide_id,
            exercise_name=exercise_name
        ).order_by(WorkoutTip.order.asc()).all()

    @staticmethod
    def get_form_tips(guide_id):
        """Get all form tips for a guide."""
        return WorkoutTip.query.filter_by(
            guide_id=guide_id,
            tip_category='form'
        ).order_by(WorkoutTip.exercise_name.asc()).all()

    @staticmethod
    def get_recovery_tips(guide_id):
        """Get all recovery tips for a guide."""
        return WorkoutTip.query.filter_by(
            guide_id=guide_id,
            tip_category='recovery'
        ).order_by(WorkoutTip.exercise_name.asc()).all()

    @staticmethod
    def get_nutrition_tips(guide_id):
        """Get all nutrition tips for a guide."""
        return WorkoutTip.query.filter_by(
            guide_id=guide_id,
            tip_category='nutrition'
        ).order_by(WorkoutTip.exercise_name.asc()).all()

    @staticmethod
    def get_mental_tips(guide_id):
        """Get all mental/motivation tips for a guide."""
        return WorkoutTip.query.filter_by(
            guide_id=guide_id,
            tip_category='mental'
        ).order_by(WorkoutTip.exercise_name.asc()).all()

    @staticmethod
    def get_by_category(guide_id, category):
        """Get tips by category."""
        return WorkoutTip.query.filter_by(
            guide_id=guide_id,
            tip_category=category
        ).order_by(WorkoutTip.order.asc()).all()
