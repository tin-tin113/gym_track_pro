"""Workout tracking model."""
from app import db
from datetime import datetime, timedelta
from sqlalchemy import func


class Workout(db.Model):
    """Track member workout exercises and progress."""

    __tablename__ = 'workouts'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False, index=True)
    workout_date = db.Column(db.Date, nullable=False)
    exercise_name = db.Column(db.String(120), nullable=False)
    exercise_category = db.Column(db.String(50), nullable=False)  # Cardio, Strength, Flexibility, Sports

    # Strength training fields
    sets = db.Column(db.Integer)
    reps = db.Column(db.Integer)
    weight = db.Column(db.Float)  # kg

    # Cardio fields
    duration_minutes = db.Column(db.Integer)
    distance_km = db.Column(db.Float)

    intensity = db.Column(db.String(20), default='moderate')  # light, moderate, intense
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Trainer assignment fields
    trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # If assigned by trainer
    assigned_date = db.Column(db.DateTime)  # When trainer assigned the workout

    # Workout guide fields
    guide_id = db.Column(db.Integer, db.ForeignKey('workout_guides.id'))  # Guide this workout follows
    guide_assignment_id = db.Column(db.Integer, db.ForeignKey('guide_assignments.id'))  # The guide assignment record

    # Relationships
    member = db.relationship('Member', backref='workouts')
    trainer = db.relationship('User', foreign_keys=[trainer_id])

    def __repr__(self):
        status = f"(Assigned by Trainer)" if self.trainer_id else "(Self-logged)"
        return f'<Workout {self.exercise_name} on {self.workout_date} {status}>'

    @property
    def is_assigned(self):
        """Check if workout was assigned by trainer."""
        return self.trainer_id is not None

    @staticmethod
    def get_workout_history(member_id, days=90):
        """Get workouts for past N days."""
        cutoff_date = datetime.utcnow().date() - timedelta(days=days)
        workouts = Workout.query.filter(
            Workout.member_id == member_id,
            Workout.workout_date >= cutoff_date
        ).order_by(Workout.workout_date.desc()).all()
        return workouts

    @staticmethod
    def get_exercise_summary(member_id, days=90):
        """Get count of exercises by category."""
        cutoff_date = datetime.utcnow().date() - timedelta(days=days)
        summary = db.session.query(
            Workout.exercise_category,
            func.count(Workout.id).label('count')
        ).filter(
            Workout.member_id == member_id,
            Workout.workout_date >= cutoff_date
        ).group_by(Workout.exercise_category).all()

        return {category: count for category, count in summary}

    @staticmethod
    def get_personal_best(member_id, exercise_name):
        """Get personal best (max weight) for a specific exercise."""
        pb = Workout.query.filter(
            Workout.member_id == member_id,
            Workout.exercise_name.ilike(exercise_name),
            Workout.weight.isnot(None)
        ).order_by(Workout.weight.desc()).first()

        if pb:
            return {'weight': pb.weight, 'date': pb.workout_date, 'reps': pb.reps}
        return None

    @staticmethod
    def get_recent_workouts(member_id, limit=5):
        """Get recent workouts for dashboard."""
        workouts = Workout.query.filter(
            Workout.member_id == member_id
        ).order_by(Workout.workout_date.desc(), Workout.created_at.desc()).limit(limit).all()
        return workouts

    @staticmethod
    def get_member_workouts(member_id, include_assigned=True, days=None):
        """Get all workouts for a member (both self-logged and assigned)."""
        query = Workout.query.filter(Workout.member_id == member_id)

        if days:
            cutoff_date = datetime.utcnow().date() - timedelta(days=days)
            query = query.filter(Workout.workout_date >= cutoff_date)

        workouts = query.order_by(Workout.workout_date.desc(), Workout.created_at.desc()).all()
        return workouts

    @staticmethod
    def get_trainer_assigned_workouts(trainer_id, member_id=None):
        """Get workouts assigned by a trainer."""
        query = Workout.query.filter(Workout.trainer_id == trainer_id)

        if member_id:
            query = query.filter(Workout.member_id == member_id)

        workouts = query.order_by(Workout.workout_date.desc()).all()
        return workouts
