from app import db
from datetime import datetime

class WorkoutGuide(db.Model):
    """Pre-made workout templates/guides that trainers can create and assign to members."""
    __tablename__ = 'workout_guides'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False)  # Strength, Cardio, Flexibility, Sports, Other
    difficulty_level = db.Column(db.String(20), nullable=False, default='Intermediate')  # Beginner, Intermediate, Advanced
    duration_weeks = db.Column(db.Integer, nullable=True)  # How many weeks the program runs
    target_goals = db.Column(db.String(300), nullable=True)  # Comma-separated goals: weight loss, muscle gain, etc.
    equipment_needed = db.Column(db.String(300), nullable=True)  # Comma-separated equipment list
    trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who created it (trainer or admin)
    status = db.Column(db.String(20), nullable=False, default='draft')  # draft, pending, approved, rejected
    rejection_reason = db.Column(db.Text, nullable=True)  # Reason admin rejected
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tips = db.relationship('WorkoutTip', backref='guide', lazy=True, cascade='all, delete-orphan')
    assignments = db.relationship('GuideAssignment', backref='guide', lazy=True, cascade='all, delete-orphan')
    workouts = db.relationship('Workout', backref='workout_guide', lazy=True)

    def __repr__(self):
        return f'<WorkoutGuide {self.name}>'

    @staticmethod
    def get_by_difficulty(difficulty):
        """Get all approved guides by difficulty level."""
        return WorkoutGuide.query.filter_by(difficulty_level=difficulty, status='approved').all()

    @staticmethod
    def get_public_guides():
        """Get all approved guides (public library)."""
        return WorkoutGuide.query.filter_by(status='approved').order_by(WorkoutGuide.created_at.desc()).all()

    @staticmethod
    def get_pending_approval():
        """Get guides pending admin approval."""
        return WorkoutGuide.query.filter_by(status='pending').order_by(WorkoutGuide.created_at.desc()).all()

    @classmethod
    def get_recommended_for_fitness_level(cls, fitness_level):
        """Get recommended guides based on fitness level."""
        level_map = {
            'beginner': 'Beginner',
            'intermediate': 'Intermediate',
            'advanced': 'Advanced'
        }
        difficulty = level_map.get(fitness_level.lower(), 'Intermediate')
        return cls.query.filter_by(difficulty_level=difficulty, status='approved').all()

    def get_trainer_guides(trainer_id):
        """Get all guides created by a specific trainer."""
        return WorkoutGuide.query.filter_by(trainer_id=trainer_id).order_by(WorkoutGuide.created_at.desc()).all()

    def is_approved(self):
        """Check if guide is approved and can be assigned."""
        return self.status == 'approved'

    def approve(self):
        """Approve the guide."""
        self.status = 'approved'
        self.rejection_reason = None
        self.updated_at = datetime.utcnow()
        db.session.commit()

    def reject(self, reason):
        """Reject the guide with a reason."""
        self.status = 'rejected'
        self.rejection_reason = reason
        self.updated_at = datetime.utcnow()
        db.session.commit()

    def get_target_goals(self):
        """Get target goals as a list."""
        if not self.target_goals:
            return []
        return [goal.strip() for goal in self.target_goals.split(',')]

    def get_equipment(self):
        """Get equipment list."""
        if not self.equipment_needed:
            return []
        return [equip.strip() for equip in self.equipment_needed.split(',')]
