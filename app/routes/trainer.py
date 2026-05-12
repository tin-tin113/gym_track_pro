"""Trainer management and dashboard routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models.user import User
from app.models.trainer import Trainer
from app.models.member import Member
from app.models.assignment import TrainerAssignment
from app.models.attendance import Attendance
from app.models.fitness import FitnessMetric
from app.utils.decorators import admin_required, trainer_or_admin_required

bp = Blueprint('trainer', __name__, url_prefix='/trainer')


@bp.route('/dashboard')
@login_required
@trainer_or_admin_required
def dashboard():
    """Trainer dashboard with assigned members and stats."""
    if current_user.role == 'trainer':
        # Get trainer record
        trainer = Trainer.query.filter_by(user_id=current_user.id).first()
        if not trainer:
            flash('Trainer profile not set up yet.', 'warning')
            return redirect(url_for('auth.login'))

        # Get assigned members
        assignments = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.is_active == True
        ).all()
        members = [a.member for a in assignments]
    else:
        # Admin view all trainers
        trainer = None
        members = Member.query.filter_by(is_active=True).limit(10).all()

    # Calculate stats
    stats = {
        'assigned_members': len(members),
        'recent_checkins': 0,
        'active_today': 0,
        'inactive_30plus': 0
    }

    if members:
        today = datetime.utcnow().date()
        today_checkins = Attendance.query.filter(
            Attendance.member_id.in_([m.id for m in members]),
            Attendance.check_in_time >= datetime.combine(today, datetime.min.time()),
            Attendance.check_in_time < datetime.combine(today + timedelta(days=1), datetime.min.time())
        ).count()
        stats['recent_checkins'] = today_checkins
        stats['active_today'] = today_checkins

        # Inactive members (30+ days)
        cutoff_date = today - timedelta(days=30)
        for member in members:
            last_visit = Attendance.query.filter_by(member_id=member.id).order_by(
                Attendance.check_in_time.desc()
            ).first()
            if not last_visit or last_visit.check_in_time.date() < cutoff_date:
                stats['inactive_30plus'] += 1

    return render_template(
        'trainer/dashboard.html',
        trainer=trainer,
        members=members,
        stats=stats,
        current_user_is_trainer=(current_user.role == 'trainer')
    )


@bp.route('/members')
@login_required
@trainer_or_admin_required
def members():
    """List assigned members with detailed stats."""
    if current_user.role == 'trainer':
        assignments = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.is_active == True
        ).all()
        members_list = [a.member for a in assignments]
    else:
        members_list = Member.query.filter_by(is_active=True).all()

    # Add attendance stats to each member
    members_with_stats = []
    for member in members_list:
        stats = Attendance.get_attendance_stats(member.id, days=30)
        members_with_stats.append({
            'member': member,
            'stats': stats,
            'days_since_visit': member.days_since_last_visit()
        })

    return render_template(
        'trainer/members.html',
        members=members_with_stats,
        current_user_is_trainer=(current_user.role == 'trainer')
    )


@bp.route('/members/<int:member_id>/progress')
@login_required
@trainer_or_admin_required
def member_progress(member_id):
    """View specific member's progress and fitness metrics."""
    member = Member.query.get_or_404(member_id)

    # Check authorization (trainer can only view assigned members)
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

    # Get metrics
    metrics = FitnessMetric.query.filter_by(member_id=member_id).order_by(
        FitnessMetric.metric_date.desc()
    ).all()

    latest_metric = metrics[0] if metrics else None
    weight_trend = FitnessMetric.get_weight_trend(member_id, days=90)

    # Get attendance stats
    attendance_stats = Attendance.get_attendance_stats(member_id, days=30)

    return render_template(
        'trainer/member_progress.html',
        member=member,
        metrics=metrics,
        latest_metric=latest_metric,
        weight_trend=weight_trend,
        attendance_stats=attendance_stats
    )


@bp.route('/list')
@login_required
@admin_required
def list_trainers():
    """Admin view of all trainers."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)

    query = Trainer.query

    if search:
        query = query.filter(
            Trainer.user.has(User.full_name.ilike(f'%{search}%'))
        )

    pagination = query.paginate(page=page, per_page=20)
    trainers = pagination.items

    # Add member count to each trainer
    trainers_with_counts = []
    for trainer in trainers:
        member_count = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == trainer.user_id,
            TrainerAssignment.is_active == True
        ).count()
        trainers_with_counts.append({
            'trainer': trainer,
            'member_count': member_count,
            'at_capacity': trainer.is_at_capacity()
        })

    return render_template(
        'trainer/list.html',
        trainers=trainers_with_counts,
        pagination=pagination,
        search=search
    )


@bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_trainer():
    """Create new trainer (admin only)."""
    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone_number', '').strip()
            spec = request.form.get('specialization', '').strip()
            cert = request.form.get('certifications', '').strip()
            bio = request.form.get('bio', '').strip()
            max_clients = request.form.get('max_clients', type=int, default=10)

            if not all([full_name, email]):
                flash('Full name and email are required.', 'danger')
                return redirect(url_for('trainer.create_trainer'))

            if User.query.filter_by(email=email).first():
                flash('Email already registered.', 'danger')
                return redirect(url_for('trainer.create_trainer'))

            # Create user
            user = User(
                username=email.split('@')[0],
                email=email,
                full_name=full_name,
                role='trainer',
                is_active=True
            )
            user.set_password('GymTrack2026!')

            # Create trainer
            trainer_obj = Trainer(
                user=user,
                phone_number=phone,
                specialization=spec,
                certifications=cert,
                bio=bio,
                max_clients=max_clients
            )

            db.session.add(user)
            db.session.add(trainer_obj)
            db.session.commit()

            flash(f'Trainer {full_name} created successfully!', 'success')
            return redirect(url_for('trainer.list_trainers'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating trainer: {str(e)}', 'danger')
            return redirect(url_for('trainer.create_trainer'))

    return render_template('trainer/edit.html', trainer=None, action='Create')


@bp.route('/<int:trainer_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_trainer(trainer_id):
    """Edit trainer details (admin only)."""
    trainer = Trainer.query.get_or_404(trainer_id)

    if request.method == 'POST':
        try:
            trainer.user.full_name = request.form.get('full_name', trainer.user.full_name)
            trainer.phone_number = request.form.get('phone_number', trainer.phone_number)
            trainer.specialization = request.form.get('specialization', trainer.specialization)
            trainer.certifications = request.form.get('certifications', trainer.certifications)
            trainer.bio = request.form.get('bio', trainer.bio)
            trainer.max_clients = request.form.get('max_clients', type=int, default=trainer.max_clients)

            db.session.commit()
            flash(f'Trainer {trainer.user.full_name} updated successfully!', 'success')
            return redirect(url_for('trainer.list_trainers'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating trainer: {str(e)}', 'danger')

    return render_template('trainer/edit.html', trainer=trainer, action='Edit')


@bp.route('/<int:trainer_id>/assignments', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_assignments(trainer_id):
    """Manage member assignments for a trainer."""
    trainer = Trainer.query.get_or_404(trainer_id)

    if request.method == 'POST':
        member_id = request.form.get('member_id', type=int)
        action = request.form.get('action')

        if action == 'assign':
            if trainer.is_at_capacity():
                flash(f'Trainer {trainer.user.full_name} is at maximum capacity ({trainer.max_clients} members).', 'warning')
                return redirect(url_for('trainer.manage_assignments', trainer_id=trainer_id))

            member = Member.query.get(member_id)
            if not member:
                flash('Member not found.', 'danger')
                return redirect(url_for('trainer.manage_assignments', trainer_id=trainer_id))

            # Deactivate previous assignment if exists
            old = TrainerAssignment.query.filter(
                TrainerAssignment.member_id == member_id,
                TrainerAssignment.is_active == True
            ).first()
            if old:
                old.is_active = False

            # Create new assignment
            assignment = TrainerAssignment(
                trainer_id=trainer.user_id,
                member_id=member_id,
                assignment_date=datetime.utcnow().date(),
                start_date=datetime.utcnow().date(),
                assignment_type='primary',
                is_active=True
            )
            db.session.add(assignment)
            db.session.commit()
            flash(f'{member.user.full_name} assigned to {trainer.user.full_name}', 'success')

        elif action == 'unassign':
            assignment = TrainerAssignment.query.filter(
                TrainerAssignment.trainer_id == trainer.user_id,
                TrainerAssignment.member_id == member_id,
                TrainerAssignment.is_active == True
            ).first()
            if assignment:
                assignment.is_active = False
                assignment.end_date = datetime.utcnow().date()
                db.session.commit()
                flash('Assignment removed', 'success')

        return redirect(url_for('trainer.manage_assignments', trainer_id=trainer_id))

    # Get assigned members
    assignments = TrainerAssignment.query.filter(
        TrainerAssignment.trainer_id == trainer.user_id,
        TrainerAssignment.is_active == True
    ).all()
    assigned_members = [a.member_id for a in assignments]

    # Get unassigned active members
    unassigned = Member.query.filter(
        Member.is_active == True,
        ~Member.id.in_(assigned_members)
    ).all()

    return render_template(
        'trainer/assignments.html',
        trainer=trainer,
        assignments=assignments,
        unassigned_members=unassigned
    )


@bp.route('/<int:trainer_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_trainer(trainer_id):
    """Soft delete trainer (deactivate)."""
    trainer = Trainer.query.get_or_404(trainer_id)

    try:
        trainer.user.is_active = False
        db.session.commit()
        flash(f'Trainer {trainer.user.full_name} has been deactivated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deactivating trainer: {str(e)}', 'danger')

    return redirect(url_for('trainer.list_trainers'))


@bp.route('/api/stats/<int:trainer_id>')
@login_required
@admin_required
def api_stats(trainer_id):
    """API endpoint for trainer statistics."""
    trainer = Trainer.query.get_or_404(trainer_id)

    # Get assigned members
    assignments = TrainerAssignment.query.filter(
        TrainerAssignment.trainer_id == trainer.user_id,
        TrainerAssignment.is_active == True
    ).all()

    member_ids = [a.member_id for a in assignments]

    if not member_ids:
        return jsonify({
            'assigned_count': 0,
            'today_checkins': 0,
            'week_checkins': 0,
            'avg_attendance': 0
        })

    today = datetime.utcnow().date()

    # Today's check-ins
    today_checkins = Attendance.query.filter(
        Attendance.member_id.in_(member_ids),
        Attendance.check_in_time >= datetime.combine(today, datetime.min.time()),
        Attendance.check_in_time < datetime.combine(today + timedelta(days=1), datetime.min.time())
    ).count()

    # Week's check-ins
    week_ago = today - timedelta(days=7)
    week_checkins = Attendance.query.filter(
        Attendance.member_id.in_(member_ids),
        Attendance.check_in_time >= datetime.combine(week_ago, datetime.min.time())
    ).count()

    # Average attendance per member
    avg_attendance = week_checkins // len(member_ids) if member_ids else 0

    return jsonify({
        'assigned_count': len(member_ids),
        'today_checkins': today_checkins,
        'week_checkins': week_checkins,
        'avg_attendance': avg_attendance
    })
