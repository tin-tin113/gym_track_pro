"""Attendance tracking routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models.member import Member
from app.models.attendance import Attendance
from app.utils.decorators import staff_or_admin_required, trainer_or_admin_required
from app.utils.qr_handler import generate_qr_code, validate_qr_token, get_qr_expiry_countdown

bp = Blueprint('attendance_routes', __name__, url_prefix='/attendance')


@bp.route('/', methods=['GET'])
@login_required
@staff_or_admin_required
def dashboard():
    """Unified attendance dashboard with check-in, active members, and history."""
    # Get today's data
    active_today = Attendance.get_active_today()
    completed_today = Attendance.get_completed_today()

    # Generate QR code
    qr_result = generate_qr_code(0)
    members = Member.query.filter_by(is_active=True).all()

    return render_template(
        'attendance/dashboard.html',
        active_members=active_today,
        completed_sessions=completed_today,
        qr_image=f"data:image/png;base64,{qr_result['qr_image_base64']}",
        qr_token=qr_result['session_token'],
        expiry_time=qr_result['expiry_time'],
        countdown=get_qr_expiry_countdown(qr_result['expiry_time']),
        members=members
    )


@bp.route('/api/active-today', methods=['GET'])
@login_required
@staff_or_admin_required
def api_active_today():
    """Get active check-ins for real-time updates (AJAX)."""
    active = Attendance.get_active_today()

    return jsonify({
        'success': True,
        'active_members': [
            {
                'id': a.id,
                'member_id': a.member_id,
                'member_name': a.member.user.full_name,
                'email': a.member.user.email,
                'check_in_time': a.check_in_time.isoformat(),
                'duration_so_far': int((datetime.utcnow() - a.check_in_time).total_seconds() / 60)
            }
            for a in active
        ]
    })


@bp.route('/api/check-out/<int:attendance_id>', methods=['POST'])
@login_required
@staff_or_admin_required
def api_check_out(attendance_id):
    """AJAX check-out endpoint that returns JSON."""
    attendance = Attendance.query.get_or_404(attendance_id)

    try:
        attendance.check_out_time = datetime.utcnow()
        attendance.calculate_duration()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'{attendance.member.user.full_name} checked out',
            'member_name': attendance.member.user.full_name,
            'duration_minutes': attendance.duration_minutes
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/check-in', methods=['GET', 'POST'])
@login_required
@staff_or_admin_required
def check_in():
    """Display QR code and manual entry for check-in."""
    if request.method == 'POST':
        member_id = request.form.get('member_id', type=int)

        if not member_id:
            flash('Please select a member.', 'danger')
            return redirect(url_for('attendance_routes.check_in'))

        member = Member.query.get(member_id)
        if not member:
            flash('Member not found.', 'danger')
            return redirect(url_for('attendance_routes.check_in'))

        # Check if member is approved
        if not member.is_approved:
            flash(f'{member.user.full_name} has not been approved yet.', 'warning')
            return redirect(url_for('attendance_routes.check_in'))

        # Check for duplicate check-in
        if Attendance.is_duplicate_checkin(member_id):
            flash(f'{member.user.full_name} is already checked in today.', 'warning')
            return redirect(url_for('attendance_routes.check_in'))

        try:
            # Create attendance record
            attendance = Attendance(
                member_id=member_id,
                check_in_time=datetime.utcnow()
            )
            db.session.add(attendance)
            db.session.commit()

            flash(f'✓ {member.user.full_name} checked in successfully!', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error recording check-in: {str(e)}', 'danger')

        return redirect(url_for('attendance_routes.check_in'))

    # Generate new QR code
    qr_result = generate_qr_code(0)  # 0 = portal generic, not member-specific
    # Only show approved members
    members = Member.query.filter_by(is_active=True, is_approved=True).all()

    return render_template(
        'attendance/check_in.html',
        qr_image=f"data:image/png;base64,{qr_result['qr_image_base64']}",
        qr_token=qr_result['session_token'],
        expiry_time=qr_result['expiry_time'],
        countdown=get_qr_expiry_countdown(qr_result['expiry_time']),
        members=members
    )


@bp.route('/api/check-in', methods=['POST'])
@login_required
def api_check_in():
    """API endpoint for QR code validation and check-in.

    Requires authentication to prevent unauthorized check-ins.
    The QR token itself provides additional time-limited validation.
    """
    data = request.get_json() or {}
    qr_token = data.get('qr_code', '')

    if not qr_token:
        return jsonify({'success': False, 'error': 'QR code required'}), 400

    # Validate QR token
    validation = validate_qr_token(qr_token)

    if not validation['is_valid']:
        return jsonify({
            'success': False,
            'error': validation['error'],
            'expired': validation['expired']
        }), 400

    member_id = validation['member_id']
    session_token = validation['session_token']

    # Check member exists
    member = Member.query.get(member_id)
    if not member:
        return jsonify({'success': False, 'error': 'Member not found'}), 404

    # Check if member is approved
    if not member.is_approved:
        return jsonify({
            'success': False,
            'error': f'{member.user.full_name} has not been approved yet'
        }), 403

    # Check for duplicate check-in
    if Attendance.is_duplicate_checkin(member_id):
        return jsonify({
            'success': False,
            'error': f'{member.user.full_name} already checked in today'
        }), 409

    try:
        # Create attendance record with QR token
        attendance = Attendance(
            member_id=member_id,
            check_in_time=datetime.utcnow(),
            qr_code=session_token
        )
        db.session.add(attendance)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'✓ {member.user.full_name} checked in successfully',
            'member_name': member.user.full_name,
            'member_id': member_id,
            'check_in_time': attendance.check_in_time.isoformat()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/<int:attendance_id>/check-out', methods=['POST'])
@login_required
@staff_or_admin_required
def check_out(attendance_id):
    """Record check-out for attendance record."""
    attendance = Attendance.query.get_or_404(attendance_id)

    try:
        attendance.check_out_time = datetime.utcnow()
        attendance.calculate_duration()
        db.session.commit()

        flash(f'✓ {attendance.member.user.full_name} checked out. Duration: {attendance.duration_minutes} minutes', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error recording check-out: {str(e)}', 'danger')

    return redirect(url_for('attendance_routes.check_in'))


@bp.route('/history')
@login_required
@staff_or_admin_required
def history():
    """View attendance history with filtering."""
    page = request.args.get('page', 1, type=int)
    member_id = request.args.get('member_id', type=int)
    date_filter = request.args.get('date', '', type=str)

    query = Attendance.query

    # Filter by member if specified
    if member_id:
        query = query.filter_by(member_id=member_id)

    # Filter by date if specified
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            next_day = filter_date + timedelta(days=1)
            query = query.filter(
                Attendance.check_in_time >= datetime.combine(filter_date, datetime.min.time()),
                Attendance.check_in_time < datetime.combine(next_day, datetime.min.time())
            )
        except ValueError:
            flash('Invalid date format.', 'warning')

    # Order by most recent first
    query = query.order_by(Attendance.check_in_time.desc())
    pagination = query.paginate(page=page, per_page=50)

    members = Member.query.filter_by(is_active=True).all()

    return render_template(
        'attendance/history.html',
        attendance_records=pagination.items,
        pagination=pagination,
        members=members,
        selected_member_id=member_id,
        selected_date=date_filter
    )


@bp.route('/stats')
@login_required
@staff_or_admin_required
def stats():
    """Display attendance statistics."""
    # Today's check-ins
    today = datetime.utcnow().date()
    today_checkins = Attendance.query.filter(
        Attendance.check_in_time >= datetime.combine(today, datetime.min.time()),
        Attendance.check_in_time < datetime.combine(today + timedelta(days=1), datetime.min.time())
    ).count()

    # This week's check-ins
    week_ago = today - timedelta(days=7)
    week_checkins = Attendance.query.filter(
        Attendance.check_in_time >= datetime.combine(week_ago, datetime.min.time())
    ).count()

    # This month's check-ins
    month_ago = today - timedelta(days=30)
    month_checkins = Attendance.query.filter(
        Attendance.check_in_time >= datetime.combine(month_ago, datetime.min.time())
    ).count()

    # Members not checked in for 30 days
    inactive_cutoff = today - timedelta(days=30)
    all_members = Member.query.filter_by(is_active=True).all()
    inactive_members = []

    for member in all_members:
        last_visit = Attendance.query.filter_by(member_id=member.id).order_by(
            Attendance.check_in_time.desc()
        ).first()

        if not last_visit or last_visit.check_in_time.date() < inactive_cutoff:
            inactive_members.append(member)

    stats_data = {
        'today_checkins': today_checkins,
        'week_checkins': week_checkins,
        'month_checkins': month_checkins,
        'inactive_members': len(inactive_members),
        'inactive_members_list': inactive_members[:10]  # Show first 10
    }

    return render_template('attendance/stats.html', stats=stats_data)


@bp.route('/api/stats')
@login_required
@staff_or_admin_required
def api_stats():
    """API endpoint for real-time statistics (JSON)."""
    today = datetime.utcnow().date()

    # Hourly breakdown for today
    hourly_stats = {}
    for hour in range(24):
        hour_start = datetime.combine(today, datetime.min.time()).replace(hour=hour)
        hour_end = hour_start + timedelta(hours=1)

        count = Attendance.query.filter(
            Attendance.check_in_time >= hour_start,
            Attendance.check_in_time < hour_end
        ).count()

        hourly_stats[f"{hour:02d}:00"] = count

    return jsonify(hourly_stats)

