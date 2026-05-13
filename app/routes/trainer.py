"""Trainer management and dashboard routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import secrets
import string
from app import db
from app.models.user import User
from app.models.trainer import Trainer
from app.models.member import Member
from app.models.assignment import TrainerAssignment
from app.models.attendance import Attendance
from app.models.fitness import FitnessMetric
from app.models.workout import Workout
from app.utils.decorators import admin_required, trainer_or_admin_required

bp = Blueprint('trainer', __name__, url_prefix='/trainer')


def generate_secure_password(length=12):
    """Generate a secure random password."""
    characters = string.ascii_letters + string.digits + string.punctuation
    # Avoid confusing characters
    characters = characters.replace("'", "").replace('"', "").replace("\\", "").replace("`", "")
    password = ''.join(secrets.choice(characters) for _ in range(length))
    return password


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


# ==================== Trainer Workout Management Routes ====================

@bp.route('/members/<int:member_id>/workouts')
@login_required
@trainer_or_admin_required
def member_workouts(member_id):
    """View all workouts for a member (self-logged and trainer-assigned)."""
    member = Member.query.get_or_404(member_id)

    # Check authorization
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

    # Get workouts
    page = request.args.get('page', 1, type=int)
    per_page = 15

    pagination = Workout.query.filter_by(member_id=member_id).order_by(
        Workout.workout_date.desc(), Workout.created_at.desc()
    ).paginate(page=page, per_page=per_page)

    workouts = pagination.items

    return render_template(
        'trainer/member_workouts.html',
        member=member,
        workouts=workouts,
        pagination=pagination
    )


@bp.route('/members/<int:member_id>/workouts/assign', methods=['GET', 'POST'])
@login_required
@trainer_or_admin_required
def assign_workout(member_id):
    """Assign a workout to a member."""
    member = Member.query.get_or_404(member_id)

    # Check authorization
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

    if request.method == 'POST':
        try:
            workout_date = datetime.strptime(request.form.get('workout_date'), '%Y-%m-%d').date()

            if workout_date > datetime.utcnow().date():
                flash('Workout date cannot be in the future.', 'danger')
                return redirect(url_for('trainer.assign_workout', member_id=member_id))

            exercise_name = request.form.get('exercise_name', '').strip()
            exercise_category = request.form.get('exercise_category', '').strip()

            if not all([exercise_name, exercise_category]):
                flash('Exercise name and category are required.', 'danger')
                return redirect(url_for('trainer.assign_workout', member_id=member_id))

            workout = Workout(
                member_id=member_id,
                workout_date=workout_date,
                exercise_name=exercise_name,
                exercise_category=exercise_category,
                intensity=request.form.get('intensity', 'moderate'),
                notes=request.form.get('notes', ''),
                trainer_id=current_user.id,
                assigned_date=datetime.utcnow()
            )

            # Handle optional fields based on exercise type
            if exercise_category in ['Strength', 'strength']:
                if request.form.get('sets'):
                    workout.sets = int(request.form.get('sets'))
                if request.form.get('reps'):
                    workout.reps = int(request.form.get('reps'))
                if request.form.get('weight'):
                    workout.weight = float(request.form.get('weight'))

            elif exercise_category in ['Cardio', 'cardio']:
                if request.form.get('duration_minutes'):
                    workout.duration_minutes = int(request.form.get('duration_minutes'))
                if request.form.get('distance_km'):
                    workout.distance_km = float(request.form.get('distance_km'))

            db.session.add(workout)
            db.session.commit()

            flash(f'Workout "{exercise_name}" assigned to {member.user.full_name}!', 'success')
            return redirect(url_for('trainer.member_workouts', member_id=member_id))

        except ValueError as e:
            flash('Invalid input: Please check your data format.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error assigning workout: {str(e)}', 'danger')

    return render_template(
        'trainer/assign_workout_form.html',
        member=member,
        now=datetime.utcnow
    )


@bp.route('/members/<int:member_id>/workouts/<int:workout_id>/edit', methods=['GET', 'POST'])
@login_required
@trainer_or_admin_required
def edit_assigned_workout(member_id, workout_id):
    """Edit a trainer-assigned workout."""
    member = Member.query.get_or_404(member_id)
    workout = Workout.query.get_or_404(workout_id)

    # Check authorization
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

        # Only trainer who assigned it can edit it
        if workout.trainer_id != current_user.id:
            flash('You can only edit workouts you assigned.', 'danger')
            return redirect(url_for('trainer.member_workouts', member_id=member_id))

    # Verify workout belongs to member
    if workout.member_id != member_id:
        flash('Invalid workout.', 'danger')
        return redirect(url_for('trainer.member_workouts', member_id=member_id))

    if request.method == 'POST':
        try:
            workout.workout_date = datetime.strptime(request.form.get('workout_date'), '%Y-%m-%d').date()
            workout.exercise_name = request.form.get('exercise_name', '').strip()
            workout.exercise_category = request.form.get('exercise_category', '').strip()
            workout.intensity = request.form.get('intensity', 'moderate')
            workout.notes = request.form.get('notes', '')

            # Clear optional fields first
            workout.sets = None
            workout.reps = None
            workout.weight = None
            workout.duration_minutes = None
            workout.distance_km = None

            # Handle optional fields based on exercise type
            if workout.exercise_category in ['Strength', 'strength']:
                if request.form.get('sets'):
                    workout.sets = int(request.form.get('sets'))
                if request.form.get('reps'):
                    workout.reps = int(request.form.get('reps'))
                if request.form.get('weight'):
                    workout.weight = float(request.form.get('weight'))

            elif workout.exercise_category in ['Cardio', 'cardio']:
                if request.form.get('duration_minutes'):
                    workout.duration_minutes = int(request.form.get('duration_minutes'))
                if request.form.get('distance_km'):
                    workout.distance_km = float(request.form.get('distance_km'))

            db.session.commit()
            flash('Workout updated successfully!', 'success')
            return redirect(url_for('trainer.member_workouts', member_id=member_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating workout: {str(e)}', 'danger')

    return render_template(
        'trainer/assign_workout_form.html',
        member=member,
        workout=workout,
        now=datetime.utcnow
    )


@bp.route('/members/<int:member_id>/workouts/<int:workout_id>/delete', methods=['POST'])
@login_required
@trainer_or_admin_required
def delete_assigned_workout(member_id, workout_id):
    """Delete a trainer-assigned workout."""
    member = Member.query.get_or_404(member_id)
    workout = Workout.query.get_or_404(workout_id)

    # Check authorization
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

        # Only trainer who assigned it can delete it
        if workout.trainer_id != current_user.id:
            flash('You can only delete workouts you assigned.', 'danger')
            return redirect(url_for('trainer.member_workouts', member_id=member_id))

    # Verify workout belongs to member
    if workout.member_id != member_id:
        flash('Invalid workout.', 'danger')
        return redirect(url_for('trainer.member_workouts', member_id=member_id))

    try:
        exercise_name = workout.exercise_name
        db.session.delete(workout)
        db.session.commit()
        flash(f'Workout "{exercise_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting workout: {str(e)}', 'danger')

    return redirect(url_for('trainer.member_workouts', member_id=member_id))

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

        # Calculate setup status
        has_setup_token = trainer.user.setup_token is not None
        is_setup_valid = has_setup_token and trainer.user.setup_token_expiry > datetime.utcnow()
        is_setup_expired = has_setup_token and trainer.user.setup_token_expiry <= datetime.utcnow()
        setup_link = url_for('auth.setup_password', token=trainer.user.setup_token, _external=True) if has_setup_token else None

        trainers_with_counts.append({
            'trainer': trainer,
            'member_count': member_count,
            'at_capacity': trainer.is_at_capacity(),
            'has_setup_token': has_setup_token,
            'is_setup_valid': is_setup_valid,
            'is_setup_expired': is_setup_expired,
            'setup_link': setup_link,
            'setup_token_expiry': trainer.user.setup_token_expiry,
            'setup_status': (
                'active' if not has_setup_token else (
                    'pending' if is_setup_valid else 'expired'
                )
            )
        })

    return render_template(
        'trainer/list.html',
        trainers=trainers_with_counts,
        pagination=pagination,
        search=search,
        now=datetime.utcnow()
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
            # Set a placeholder password (will be replaced by trainer during setup)
            user.set_password(secrets.token_urlsafe(32))

            # Generate one-time setup token (valid for 24 hours)
            setup_token = secrets.token_urlsafe(32)
            user.setup_token = setup_token
            user.setup_token_expiry = datetime.utcnow() + timedelta(hours=24)

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

            # Generate setup link
            setup_link = url_for('auth.setup_password', token=setup_token, _external=True)
            flash(f'Trainer {full_name} created! <a href="{setup_link}" target="_blank" class="alert-link">Click here for setup link</a>', 'success')
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

    # Calculate setup status for display
    has_setup_token = trainer.user.setup_token is not None
    is_setup_valid = has_setup_token and trainer.user.setup_token_expiry > datetime.utcnow()
    is_setup_expired = has_setup_token and trainer.user.setup_token_expiry <= datetime.utcnow()
    setup_link = url_for('auth.setup_password', token=trainer.user.setup_token, _external=True) if has_setup_token else None

    return render_template(
        'trainer/edit.html',
        trainer=trainer,
        action='Edit',
        has_setup_token=has_setup_token,
        is_setup_valid=is_setup_valid,
        is_setup_expired=is_setup_expired,
        setup_link=setup_link,
        setup_token_expiry=trainer.user.setup_token_expiry
    )


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


@bp.route('/<int:trainer_id>/resend-setup', methods=['POST'])
@login_required
@admin_required
def resend_setup_link(trainer_id):
    """Regenerate and resend setup link for a trainer."""
    trainer = Trainer.query.get_or_404(trainer_id)

    # Check if trainer already has a password set (setup completed)
    if trainer.user.password_hash and not trainer.user.setup_token:
        flash(f'Trainer {trainer.user.full_name} has already completed setup. Use password reset if they forgot their password.', 'info')
        return redirect(url_for('trainer.edit_trainer', trainer_id=trainer_id))

    try:
        # Generate new setup token
        setup_token = secrets.token_urlsafe(32)
        trainer.user.setup_token = setup_token
        trainer.user.setup_token_expiry = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()

        # Generate setup link
        setup_link = url_for('auth.setup_password', token=setup_token, _external=True)
        flash(f'New setup link generated for {trainer.user.full_name}! <a href="{setup_link}" target="_blank" class="alert-link">Click here for setup link</a>', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error regenerating setup link: {str(e)}', 'danger')

    return redirect(url_for('trainer.edit_trainer', trainer_id=trainer_id))


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
