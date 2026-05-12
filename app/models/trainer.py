"""Trainer model."""
from app import db
from datetime import datetime


class Trainer(db.Model):
    """Trainer profile model."""

    __tablename__ = 'trainers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    specialization = db.Column(db.Text)  # Comma-separated or JSON
    certifications = db.Column(db.Text)
    bio = db.Column(db.Text)
    phone_number = db.Column(db.String(20))
    profile_image_url = db.Column(db.String(255))
    hourly_rate = db.Column(db.Float)
    max_clients = db.Column(db.Integer, default=10)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Trainer {self.user.full_name}>'

    def get_assigned_members_count(self):
        """Get count of currently assigned members."""
        from app.models.assignment import TrainerAssignment
        return TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == self.user_id,
            TrainerAssignment.is_active == True
        ).count()

    def is_at_capacity(self):
        """Check if trainer is at maximum client capacity."""
        return self.get_assigned_members_count() >= self.max_clients

    def get_specializations_list(self):
        """Get list of specializations."""
        if self.specialization:
            return [s.strip() for s in self.specialization.split(',')]
        return []
