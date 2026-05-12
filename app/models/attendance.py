"""Attendance model."""
from app import db
from datetime import datetime, timedelta


class Attendance(db.Model):
    """Track member check-ins and check-outs."""

    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False, index=True)
    check_in_time = db.Column(db.DateTime, nullable=False, index=True)
    check_out_time = db.Column(db.DateTime)
    duration_minutes = db.Column(db.Integer)
    qr_code = db.Column(db.String(100), unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    member = db.relationship('Member', backref='attendance_records')

    def __repr__(self):
        return f'<Attendance {self.member_id} at {self.check_in_time}>'

    def calculate_duration(self):
        """Calculate duration in minutes if checked out."""
        if self.check_out_time:
            delta = self.check_out_time - self.check_in_time
            self.duration_minutes = int(delta.total_seconds() / 60)
            return self.duration_minutes
        return None

    @staticmethod
    def is_duplicate_checkin(member_id):
        """Check if member already checked in today."""
        today = datetime.utcnow().date()
        existing_checkin = Attendance.query.filter(
            Attendance.member_id == member_id,
            Attendance.check_in_time >= datetime.combine(today, datetime.min.time()),
            Attendance.check_in_time <= datetime.combine(today, datetime.max.time()),
            Attendance.check_out_time == None
        ).first()
        return existing_checkin is not None

    @staticmethod
    def get_attendance_stats(member_id, days=30):
        """Get attendance statistics for a member."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        records = Attendance.query.filter(
            Attendance.member_id == member_id,
            Attendance.check_in_time >= cutoff_date
        ).all()

        total_visits = len(records)
        total_duration = sum(r.duration_minutes for r in records if r.duration_minutes) if records else 0
        avg_duration = total_duration / total_visits if total_visits > 0 else 0

        return {
            'total_visits': total_visits,
            'avg_duration': int(avg_duration),
            'total_duration': total_duration
        }

    @staticmethod
    def get_active_today():
        """Get members checked in today but not checked out yet."""
        from datetime import datetime, time
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, time.min)

        return Attendance.query.filter(
            Attendance.check_in_time >= today_start,
            Attendance.check_out_time == None
        ).order_by(Attendance.check_in_time.asc()).all()

    @staticmethod
    def get_completed_today():
        """Get members checked out today."""
        from datetime import datetime, time
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, time.min)

        return Attendance.query.filter(
            Attendance.check_in_time >= today_start,
            Attendance.check_out_time != None
        ).order_by(Attendance.check_out_time.desc()).limit(15).all()
