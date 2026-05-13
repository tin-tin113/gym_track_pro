"""Member model."""
from app import db
from datetime import datetime, timedelta


class Member(db.Model):
    """Member profile model."""

    __tablename__ = 'members'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    phone_number = db.Column(db.String(20))
    emergency_contact = db.Column(db.String(120))
    membership_type = db.Column(db.String(20), default='monthly', nullable=False)  # daily, monthly, quarterly, annual
    membership_start_date = db.Column(db.Date, nullable=False)
    membership_expiry_date = db.Column(db.Date, nullable=False)
    assigned_trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    profile_image_url = db.Column(db.String(255))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)  # For self-registered members needing admin approval
    approval_date = db.Column(db.DateTime)  # When admin approved the member
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Member {self.user.full_name}>'

    def is_membership_active(self):
        """Check if membership is currently active."""
        return self.membership_expiry_date >= datetime.utcnow().date() and self.is_active

    def is_membership_expiring_soon(self, days=7):
        """Check if membership expires within specified days."""
        expiry_threshold = datetime.utcnow().date() + timedelta(days=days)
        return self.membership_expiry_date <= expiry_threshold and self.membership_expiry_date >= datetime.utcnow().date()

    def days_until_expiry(self):
        """Get days until membership expires."""
        if self.is_membership_active():
            return (self.membership_expiry_date - datetime.utcnow().date()).days
        return 0

    def days_since_last_visit(self):
        """Get days since last gym visit."""
        from app.models.attendance import Attendance
        last_visit = Attendance.query.filter_by(member_id=self.id).order_by(Attendance.check_in_time.desc()).first()
        if last_visit:
            return (datetime.utcnow() - last_visit.check_in_time).days
        return None
