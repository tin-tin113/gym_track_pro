"""Fitness metrics model."""
from app import db
from datetime import datetime, timedelta


class FitnessMetric(db.Model):
    """Track member fitness measurements and body metrics."""

    __tablename__ = 'fitness_metrics'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False, index=True)
    metric_date = db.Column(db.Date, nullable=False)
    weight = db.Column(db.Float)  # kg
    height = db.Column(db.Float)  # cm
    bmi = db.Column(db.Float)
    chest = db.Column(db.Float)  # cm
    waist = db.Column(db.Float)  # cm
    hips = db.Column(db.Float)  # cm
    bicep = db.Column(db.Float)  # cm
    thigh = db.Column(db.Float)  # cm
    body_fat_percentage = db.Column(db.Float)
    muscle_mass = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    member = db.relationship('Member', backref='fitness_metrics')
    created_by = db.relationship('User', backref='fitness_records_created')

    def __repr__(self):
        return f'<FitnessMetric {self.member_id} on {self.metric_date}>'

    def calculate_bmi(self):
        """Calculate BMI from weight (kg) and height (cm)."""
        if self.weight and self.height:
            height_m = self.height / 100
            self.bmi = round(self.weight / (height_m ** 2), 2)
            return self.bmi
        return None

    def get_bmi_classification(self):
        """Get BMI classification (WHO standard)."""
        if not self.bmi:
            self.calculate_bmi()

        if not self.bmi:
            return None

        if self.bmi < 18.5:
            return 'Underweight'
        elif self.bmi < 25:
            return 'Normal weight'
        elif self.bmi < 30:
            return 'Overweight'
        else:
            return 'Obese'

    @staticmethod
    def get_weight_trend(member_id, days=30):
        """Calculate weight trend (% change) over specified days."""
        cutoff_date = datetime.utcnow().date() - timedelta(days=days)
        metrics = FitnessMetric.query.filter(
            FitnessMetric.member_id == member_id,
            FitnessMetric.metric_date >= cutoff_date
        ).order_by(FitnessMetric.metric_date).all()

        if len(metrics) < 2:
            return None

        start_weight = metrics[0].weight
        current_weight = metrics[-1].weight

        if not start_weight or not current_weight:
            return None

        weight_change = current_weight - start_weight
        percent_change = (weight_change / start_weight) * 100

        return {
            'start_weight': start_weight,
            'current_weight': current_weight,
            'weight_change': round(weight_change, 2),
            'percent_change': round(percent_change, 2),
            'trend': 'up' if weight_change > 0 else 'down' if weight_change < 0 else 'stable'
        }

    @staticmethod
    def get_metric_history(member_id, metric_field, days=90):
        """Get historical data for a specific metric."""
        cutoff_date = datetime.utcnow().date() - timedelta(days=days)
        metrics = FitnessMetric.query.filter(
            FitnessMetric.member_id == member_id,
            FitnessMetric.metric_date >= cutoff_date
        ).order_by(FitnessMetric.metric_date).all()

        return [
            {
                'date': m.metric_date.isoformat(),
                'value': getattr(m, metric_field)
            }
            for m in metrics if getattr(m, metric_field) is not None
        ]
