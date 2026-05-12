"""Trainer-Member assignment model."""
from app import db
from datetime import datetime


class TrainerAssignment(db.Model):
    """Track trainer assignments to members."""

    __tablename__ = 'trainer_assignments'

    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False, index=True)
    assignment_date = db.Column(db.Date, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    assignment_type = db.Column(db.String(20), default='primary')  # primary, secondary, temporary
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    trainer = db.relationship('User', foreign_keys=[trainer_id], backref='trainer_assignments')
    member = db.relationship('Member', backref='trainer_assignments')

    def __repr__(self):
        return f'<TrainerAssignment {self.trainer_id} -> {self.member_id}>'

    @staticmethod
    def get_active_assignment(member_id):
        """Get current active trainer assignment for a member."""
        return TrainerAssignment.query.filter(
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()

    @staticmethod
    def get_trainer_members(trainer_id):
        """Get list of members assigned to a trainer."""
        return TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == trainer_id,
            TrainerAssignment.is_active == True
        ).all()
