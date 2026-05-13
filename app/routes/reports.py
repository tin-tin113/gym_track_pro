"""Reports and analytics routes."""
from flask import Blueprint, render_template, request, send_file, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.member import Member
from app.models.attendance import Attendance
from app.models.fitness import FitnessMetric
from app.utils.decorators import staff_or_admin_required, can_view_member_fitness_report
from datetime import datetime, timedelta
from io import BytesIO
import csv

bp = Blueprint('reports', __name__, url_prefix='/reports')


@bp.route('/dashboard', methods=['GET'])
@login_required
@staff_or_admin_required
def dashboard():
    """Gym analytics dashboard with system-wide statistics."""
    # Get date range from query params
    days = request.args.get('days', 30, type=int)
    start_date = datetime.utcnow().date() - timedelta(days=days)

    # Member statistics
    total_members = Member.query.filter_by(is_active=True).count()
    active_today = Attendance.query.filter(
        Attendance.check_in_time >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    ).distinct(Attendance.member_id).count()

    # Attendance statistics
    attendance_records = Attendance.query.filter(
        Attendance.check_in_time >= start_date
    ).all()
    total_visits = len(attendance_records)
    avg_daily_visits = total_visits / max(days, 1)

    # Membership expiry statistics
    expiry_date = datetime.utcnow().date() + timedelta(days=7)
    expiring_soon = Member.query.filter(
        Member.membership_expiry_date <= expiry_date,
        Member.membership_expiry_date >= datetime.utcnow().date(),
        Member.is_active == True
    ).count()
    expired = Member.query.filter(
        Member.membership_expiry_date < datetime.utcnow().date(),
        Member.is_active == True
    ).count()

    # Fitness tracking participation
    fitness_participants = FitnessMetric.query.filter(
        FitnessMetric.created_at >= start_date
    ).distinct(FitnessMetric.member_id).count()

    # Top attending members
    member_visits = db.session.query(
        Member.id,
        User.full_name,
        db.func.count(Attendance.id).label('visit_count')
    ).join(User, Member.user_id == User.id).join(
        Attendance, Member.id == Attendance.member_id
    ).filter(
        Attendance.check_in_time >= start_date
    ).group_by(Member.id).order_by(
        db.func.count(Attendance.id).desc()
    ).limit(10).all()

    return render_template(
        'reports/dashboard.html',
        total_members=total_members,
        active_today=active_today,
        total_visits=total_visits,
        avg_daily_visits=round(avg_daily_visits, 2),
        expiring_soon=expiring_soon,
        expired=expired,
        fitness_participants=fitness_participants,
        member_visits=member_visits,
        days=days
    )


@bp.route('/attendance', methods=['GET', 'POST'])
@login_required
@staff_or_admin_required
def attendance_report():
    """Generate attendance reports with filtering."""
    members = Member.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        member_id = request.form.get('member_id')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        format_type = request.form.get('format', 'html')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        query = Attendance.query.filter(
            Attendance.check_in_time >= start_date,
            Attendance.check_in_time <= end_date
        )

        if member_id:
            query = query.filter(Attendance.member_id == member_id)

        records = query.order_by(Attendance.check_in_time.desc()).all()

        if format_type == 'csv':
            return _generate_attendance_csv(records)
        else:
            member = Member.query.get(member_id) if member_id else None
            return render_template(
                'reports/attendance_report.html',
                records=records,
                member=member,
                start_date=start_date,
                end_date=end_date,
                members=members
            )

    return render_template('reports/attendance_report.html', members=members)


@bp.route('/fitness/<int:member_id>', methods=['GET'])
@login_required
def fitness_report(member_id):
    """Generate fitness progress report for a member.

    Access:
    - Admin/Staff: Any member
    - Trainer: Assigned members only
    - Member: Own report only
    """
    member = Member.query.get_or_404(member_id)

    # Authorization check using helper
    if not can_view_member_fitness_report(current_user, member):
        return {'error': 'Unauthorized'}, 403

    metrics = FitnessMetric.query.filter(
        FitnessMetric.member_id == member_id
    ).order_by(FitnessMetric.metric_date.desc()).all()

    # Calculate trends
    weight_trend = FitnessMetric.get_weight_trend(member_id, days=90)
    bmi_trend = {}
    if metrics and len(metrics) >= 2:
        oldest_metric = metrics[-1]
        newest_metric = metrics[0]
        bmi_trend = {
            'start_bmi': oldest_metric.bmi,
            'current_bmi': newest_metric.bmi,
            'change': round(newest_metric.bmi - oldest_metric.bmi, 2) if oldest_metric.bmi else 0
        }

    return render_template(
        'reports/fitness_report.html',
        member=member,
        metrics=metrics,
        weight_trend=weight_trend,
        bmi_trend=bmi_trend
    )


@bp.route('/fitness/<int:member_id>/export', methods=['GET'])
@login_required
def fitness_export(member_id):
    """Export fitness metrics as CSV.

    Access:
    - Admin/Staff: Any member
    - Trainer: Assigned members only
    - Member: Own export only
    """
    member = Member.query.get_or_404(member_id)

    # Authorization check using helper
    if not can_view_member_fitness_report(current_user, member):
        return {'error': 'Unauthorized'}, 403

    metrics = FitnessMetric.query.filter(
        FitnessMetric.member_id == member_id
    ).order_by(FitnessMetric.metric_date).all()

    output = BytesIO()
    writer = csv.writer(output.getbuffer())

    # Header
    writer.writerow([
        'Date', 'Weight (kg)', 'Height (cm)', 'BMI', 'Chest (cm)',
        'Waist (cm)', 'Hips (cm)', 'Bicep (cm)', 'Thigh (cm)',
        'Body Fat %', 'Notes'
    ])

    # Data rows
    for metric in metrics:
        writer.writerow([
            metric.metric_date,
            metric.weight or '',
            metric.height or '',
            metric.bmi or '',
            metric.chest or '',
            metric.waist or '',
            metric.hips or '',
            metric.bicep or '',
            metric.thigh or '',
            metric.body_fat_percentage or '',
            metric.notes or ''
        ])

    output.seek(0)
    filename = f"fitness_{member.user.full_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"

    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/members/export', methods=['GET'])
@login_required
@staff_or_admin_required
def members_export():
    """Export all members as CSV."""
    members = Member.query.filter_by(is_active=True).all()

    output = BytesIO()
    writer = csv.writer(output.getbuffer())

    # Header
    writer.writerow([
        'Full Name', 'Email', 'Phone', 'Membership Type', 'Start Date',
        'Expiry Date', 'Status'
    ])

    # Data rows
    for member in members:
        status = 'Active'
        if member.is_membership_expiring_soon(days=7):
            status = 'Expiring Soon'
        elif not member.is_membership_active():
            status = 'Expired'

        writer.writerow([
            member.user.full_name,
            member.user.email,
            member.phone_number or '',
            member.membership_type,
            member.membership_start_date,
            member.membership_expiry_date,
            status
        ])

    output.seek(0)
    filename = f"members_{datetime.now().strftime('%Y%m%d')}.csv"

    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/api/stats', methods=['GET'])
@login_required
@staff_or_admin_required
def api_stats():
    """API endpoint for dashboard statistics (for charts)."""
    days = request.args.get('days', 30, type=int)
    start_date = datetime.utcnow().date() - timedelta(days=days)

    # Get daily visit counts
    daily_stats = db.session.query(
        db.func.date(Attendance.check_in_time).label('date'),
        db.func.count(Attendance.id).label('visits'),
        db.func.avg(Attendance.duration_minutes).label('avg_duration')
    ).filter(
        Attendance.check_in_time >= start_date
    ).group_by(
        db.func.date(Attendance.check_in_time)
    ).order_by('date').all()

    chart_data = {
        'dates': [str(stat[0]) for stat in daily_stats],
        'visits': [stat[1] for stat in daily_stats],
        'avg_duration': [round(stat[2] or 0, 2) for stat in daily_stats]
    }

    return jsonify(chart_data)




@bp.route('/daily-attendance', methods=['GET'])
@login_required
@staff_or_admin_required
def daily_attendance():
    """Display and export daily gym attendance for today."""
    today = datetime.utcnow().date()
    start_time = datetime.combine(today, datetime.min.time())
    end_time = datetime.combine(today, datetime.max.time())

    # Get all attendance records for today
    records = Attendance.query.filter(
        Attendance.check_in_time >= start_time,
        Attendance.check_in_time <= end_time
    ).order_by(Attendance.check_in_time.desc()).all()

    # Calculate summary stats
    total_visits = len(records)
    still_checked_in = sum(1 for r in records if r.check_out_time is None)

    # Handle CSV export
    if request.args.get('format') == 'csv':
        return _generate_daily_attendance_csv(records, today)

    return render_template('reports/daily_attendance.html',
        records=records,
        today=today,
        total_visits=total_visits,
        still_checked_in=still_checked_in)


def _generate_daily_attendance_csv(records, date):
    """Generate CSV export for daily attendance."""
    output = BytesIO()
    writer = csv.writer(output.getbuffer())

    writer.writerow(['Daily Attendance Report', date.strftime('%Y-%m-%d')])
    writer.writerow([])
    writer.writerow(['Member Name', 'Email', 'Check-in Time', 'Check-out Time', 'Duration (minutes)'])

    for record in records:
        duration = ''
        if record.check_out_time and record.check_in_time:
            duration = int((record.check_out_time - record.check_in_time).total_seconds() / 60)

        writer.writerow([
            record.member.user.full_name,
            record.member.user.email,
            record.check_in_time.strftime('%H:%M:%S') if record.check_in_time else '',
            record.check_out_time.strftime('%H:%M:%S') if record.check_out_time else 'Still here',
            duration
        ])

    output.seek(0)
    filename = f"daily_attendance_{date.strftime('%Y%m%d')}.csv"
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name=filename)

