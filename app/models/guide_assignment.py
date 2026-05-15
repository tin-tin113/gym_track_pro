from app import db
from datetime import datetime

class GuideAssignment(db.Model):
    """Tracks when a trainer assigns a workout guide to a member."""
    __tablename__ = 'guide_assignments'

    id = db.Column(db.Integer, primary_key=True)
    guide_id = db.Column(db.Integer, db.ForeignKey('workout_guides.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Trainer who assigned
    assignment_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)  # When assigned
    start_date = db.Column(db.DateTime, nullable=True)  # When member should start
    target_completion_date = db.Column(db.DateTime, nullable=True)  # Expected completion date
    is_completed = db.Column(db.Boolean, nullable=False, default=False)
    completion_date = db.Column(db.DateTime, nullable=True)  # When member completed
    notes = db.Column(db.Text, nullable=True)  # Trainer notes/instructions
    is_active = db.Column(db.Boolean, nullable=False, default=True)  # Soft delete flag
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    member = db.relationship('Member', backref='guide_assignments')
    trainer = db.relationship('User', backref='assigned_guides')

    def __repr__(self):
        return f'<GuideAssignment guide={self.guide_id}, member={self.member_id}>'

    @staticmethod
    def get_active_assignments(member_id):
        """Get all active guide assignments for a member."""
        return GuideAssignment.query.filter_by(
            member_id=member_id,
            is_active=True,
            is_completed=False
        ).order_by(GuideAssignment.start_date.desc()).all()

    @staticmethod
    def get_completed_assignments(member_id):
        """Get all completed guide assignments for a member."""
        return GuideAssignment.query.filter_by(
            member_id=member_id,
            is_completed=True,
            is_active=True
        ).order_by(GuideAssignment.completion_date.desc()).all()

    @staticmethod
    def get_member_guide_assignments(member_id):
        """Get all (active and inactive) guide assignments for a member."""
        return GuideAssignment.query.filter_by(
            member_id=member_id,
            is_active=True
        ).order_by(GuideAssignment.start_date.desc()).all()

    @staticmethod
    def get_assignments_by_trainer(trainer_id):
        """Get all guide assignments made by a trainer."""
        return GuideAssignment.query.filter_by(
            trainer_id=trainer_id,
            is_active=True
        ).order_by(GuideAssignment.assignment_date.desc()).all()

    @staticmethod
    def get_assignments_for_guide(guide_id):
        """Get all members assigned to a specific guide."""
        return GuideAssignment.query.filter_by(
            guide_id=guide_id,
            is_active=True
        ).order_by(GuideAssignment.assignment_date.desc()).all()

    def calculate_progress(self):
        """Calculate progress percentage based on logged workouts from this guide."""
        if not self.is_active:
            return 100 if self.is_completed else 0

        from app.models.workout import Workout

        # Get all workouts logged for this guide assignment
        logged_workouts = Workout.query.filter_by(
            guide_assignment_id=self.id,
            member_id=self.member_id
        ).count()

        # Estimate expected workouts based on guide duration and difficulty
        # Assume ~3-4 workouts per week per difficulty
        if self.guide.duration_weeks:
            if self.guide.difficulty_level == 'Beginner':
                expected = self.guide.duration_weeks * 3
            elif self.guide.difficulty_level == 'Intermediate':
                expected = self.guide.duration_weeks * 4
            else:  # Advanced
                expected = self.guide.duration_weeks * 5

            if expected == 0:
                return 0

            progress = min(100, int((logged_workouts / expected) * 100))
            return progress

        return 0

    def get_days_elapsed(self):
        """Get number of days since assignment."""
        if self.start_date:
            return (datetime.utcnow() - self.start_date).days
        return 0

    def get_days_remaining(self):
        """Get number of days until target completion."""
        if self.target_completion_date and not self.is_completed:
            remaining = (self.target_completion_date - datetime.utcnow()).days
            return max(0, remaining)
        return 0

    def mark_completed(self):
        """Mark the guide as completed by member."""
        self.is_completed = True
        self.completion_date = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        db.session.commit()

    def unassign(self):
        """Soft delete the assignment (member no longer has this guide)."""
        self.is_active = False
        self.updated_at = datetime.utcnow()
        db.session.commit()

    def is_overdue(self):
        """Check if guide is overdue for completion."""
        if self.target_completion_date and not self.is_completed:
            return datetime.utcnow() > self.target_completion_date
        return False
