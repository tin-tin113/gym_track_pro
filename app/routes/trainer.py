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
from app.models.workout_guide import WorkoutGuide
from app.models.workout_tip import WorkoutTip
from app.models.guide_assignment import GuideAssignment
from app.models.diet_plan import DietPlan, MealPlan
from app.models.diet_assignment import DietAssignment, MealLog
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


# ==================== WORKOUT GUIDE MANAGEMENT ====================

@bp.route('/guides')
@login_required
@trainer_or_admin_required
def list_guides():
    """List my created guides or all guides (admin)."""
    page = request.args.get('page', 1, type=int)

    if current_user.role == 'admin':
        # Admin sees all guides
        guides = WorkoutGuide.query.order_by(WorkoutGuide.created_at.desc()).paginate(page=page, per_page=15)
    else:
        # Trainers see only their own guides
        guides = WorkoutGuide.query.filter_by(trainer_id=current_user.id).order_by(
            WorkoutGuide.created_at.desc()
        ).paginate(page=page, per_page=15)

    return render_template(
        'trainer/guides/list.html',
        guides=guides,
        page=page
    )


@bp.route('/guides/library')
@login_required
@trainer_or_admin_required
def browse_guides():
    """Browse all approved guides to assign to members."""
    page = request.args.get('page', 1, type=int)
    difficulty = request.args.get('difficulty', None)

    query = WorkoutGuide.query.filter_by(status='approved')

    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)

    guides = query.order_by(WorkoutGuide.created_at.desc()).paginate(page=page, per_page=15)

    return render_template(
        'trainer/guides/library.html',
        guides=guides,
        page=page,
        difficulty_filter=difficulty
    )


@bp.route('/guides/new', methods=['GET', 'POST'])
@login_required
@trainer_or_admin_required
def create_guide():
    """Create a new workout guide."""
    if request.method == 'POST':
        try:
            guide = WorkoutGuide(
                name=request.form.get('name'),
                description=request.form.get('description'),
                category=request.form.get('category'),
                difficulty_level=request.form.get('difficulty_level', 'Intermediate'),
                duration_weeks=request.form.get('duration_weeks', type=int),
                target_goals=request.form.get('target_goals'),
                equipment_needed=request.form.get('equipment_needed'),
                trainer_id=current_user.id,
                status='draft'
            )
            db.session.add(guide)
            db.session.commit()
            flash('Workout guide created! Now add tips for exercises.', 'success')
            return redirect(url_for('trainer.edit_guide', guide_id=guide.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating guide: {str(e)}', 'danger')

    return render_template('trainer/guides/form.html', guide=None)


@bp.route('/guides/<int:guide_id>')
@login_required
@trainer_or_admin_required
def view_guide(guide_id):
    """View guide details with tips."""
    guide = WorkoutGuide.query.get_or_404(guide_id)

    # Check permissions
    if current_user.role == 'trainer' and guide.trainer_id != current_user.id:
        flash('You do not have access to this guide.', 'danger')
        return redirect(url_for('trainer.list_guides'))

    tips = WorkoutTip.query.filter_by(guide_id=guide_id).order_by(WorkoutTip.exercise_name.asc()).all()
    assignments = GuideAssignment.query.filter_by(guide_id=guide_id, is_active=True).all()

    return render_template(
        'trainer/guides/detail.html',
        guide=guide,
        tips=tips,
        assignments=assignments
    )


@bp.route('/guides/<int:guide_id>/edit', methods=['GET', 'POST'])
@login_required
@trainer_or_admin_required
def edit_guide(guide_id):
    """Edit a workout guide."""
    guide = WorkoutGuide.query.get_or_404(guide_id)

    # Check permissions
    if current_user.role == 'trainer' and guide.trainer_id != current_user.id:
        flash('You do not have access to edit this guide.', 'danger')
        return redirect(url_for('trainer.list_guides'))

    if request.method == 'POST':
        try:
            guide.name = request.form.get('name')
            guide.description = request.form.get('description')
            guide.category = request.form.get('category')
            guide.difficulty_level = request.form.get('difficulty_level')
            guide.duration_weeks = request.form.get('duration_weeks', type=int)
            guide.target_goals = request.form.get('target_goals')
            guide.equipment_needed = request.form.get('equipment_needed')
            guide.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Guide updated successfully.', 'success')
            return redirect(url_for('trainer.view_guide', guide_id=guide.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating guide: {str(e)}', 'danger')

    return render_template('trainer/guides/form.html', guide=guide)


@bp.route('/guides/<int:guide_id>/delete', methods=['POST'])
@login_required
@trainer_or_admin_required
def delete_guide(guide_id):
    """Delete a workout guide (soft delete)."""
    guide = WorkoutGuide.query.get_or_404(guide_id)

    # Check permissions
    if current_user.role == 'trainer' and guide.trainer_id != current_user.id:
        flash('You do not have access to delete this guide.', 'danger')
        return redirect(url_for('trainer.list_guides'))

    try:
        # Soft delete by removing all assignments
        GuideAssignment.query.filter_by(guide_id=guide_id).update({'is_active': False})
        db.session.delete(guide)
        db.session.commit()
        flash('Guide deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting guide: {str(e)}', 'danger')

    return redirect(url_for('trainer.list_guides'))


@bp.route('/guides/<int:guide_id>/submit', methods=['POST'])
@login_required
@trainer_or_admin_required
def submit_guide(guide_id):
    """Submit guide for admin approval."""
    guide = WorkoutGuide.query.get_or_404(guide_id)

    # Check permissions
    if current_user.role == 'trainer' and guide.trainer_id != current_user.id:
        flash('You do not have access to this guide.', 'danger')
        return redirect(url_for('trainer.list_guides'))

    try:
        if guide.status != 'draft':
            flash('Only draft guides can be submitted.', 'warning')
        else:
            guide.status = 'pending'
            guide.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Guide submitted for approval by admin.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting guide: {str(e)}', 'danger')

    return redirect(url_for('trainer.view_guide', guide_id=guide.id))


# ==================== WORKOUT GUIDE TIPS ====================

@bp.route('/guides/<int:guide_id>/tips/add', methods=['POST'])
@login_required
@trainer_or_admin_required
def add_guide_tip(guide_id):
    """Add a tip to a guide (exercise-specific guidance)."""
    guide = WorkoutGuide.query.get_or_404(guide_id)

    # Check permissions
    if current_user.role == 'trainer' and guide.trainer_id != current_user.id:
        flash('You do not have access to this guide.', 'danger')
        return redirect(url_for('trainer.list_guides'))

    try:
        tip = WorkoutTip(
            guide_id=guide_id,
            exercise_name=request.form.get('exercise_name'),
            tip_category=request.form.get('tip_category'),
            content=request.form.get('content'),
            order=request.form.get('order', 0, type=int)
        )
        db.session.add(tip)
        db.session.commit()
        flash('Tip added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding tip: {str(e)}', 'danger')

    return redirect(url_for('trainer.view_guide', guide_id=guide.id))


@bp.route('/guides/<int:guide_id>/tips/<int:tip_id>/delete', methods=['POST'])
@login_required
@trainer_or_admin_required
def delete_guide_tip(guide_id, tip_id):
    """Delete a tip from a guide."""
    guide = WorkoutGuide.query.get_or_404(guide_id)
    tip = WorkoutTip.query.get_or_404(tip_id)

    # Check permissions
    if current_user.role == 'trainer' and guide.trainer_id != current_user.id:
        flash('You do not have access to this guide.', 'danger')
        return redirect(url_for('trainer.list_guides'))

    try:
        db.session.delete(tip)
        db.session.commit()
        flash('Tip deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting tip: {str(e)}', 'danger')

    return redirect(url_for('trainer.view_guide', guide_id=guide.id))


# ==================== GUIDE ASSIGNMENT TO MEMBERS ====================

@bp.route('/members/<int:member_id>/assign-guide', methods=['GET', 'POST'])
@login_required
@trainer_or_admin_required
def assign_guide_to_member(member_id):
    """Assign a workout guide to a member."""
    member = Member.query.get_or_404(member_id)

    # Check access - trainer can only assign to their members
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter_by(
            trainer_id=current_user.id,
            member_id=member_id,
            is_active=True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

    if request.method == 'POST':
        try:
            guide_id = request.form.get('guide_id', type=int)
            guide = WorkoutGuide.query.get_or_404(guide_id)

            # Verify guide is approved
            if guide.status != 'approved':
                flash('Can only assign approved guides.', 'warning')
                return redirect(url_for('trainer.assign_guide_to_member', member_id=member_id))

            assignment = GuideAssignment(
                guide_id=guide_id,
                member_id=member_id,
                trainer_id=current_user.id,
                start_date=datetime.utcnow(),
                notes=request.form.get('notes')
            )
            db.session.add(assignment)
            db.session.commit()
            flash(f'Guide "{guide.name}" assigned to {member.user.full_name}.', 'success')
            return redirect(url_for('trainer.members'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error assigning guide: {str(e)}', 'danger')

    # Get approved guides
    guides = WorkoutGuide.query.filter_by(status='approved').order_by(WorkoutGuide.name.asc()).all()

    return render_template(
        'trainer/guides/assign_member.html',
        member=member,
        guides=guides
    )


@bp.route('/members/<int:member_id>/guides')
@login_required
@trainer_or_admin_required
def member_guides(member_id):
    """View all guides assigned to a member."""
    member = Member.query.get_or_404(member_id)

    # Check access
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter_by(
            trainer_id=current_user.id,
            member_id=member_id,
            is_active=True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

    assignments = GuideAssignment.query.filter_by(
        member_id=member_id,
        is_active=True
    ).order_by(GuideAssignment.start_date.desc()).all()

    return render_template(
        'trainer/guides/member_guides.html',
        member=member,
        assignments=assignments
    )


@bp.route('/guides/<int:guide_id>/assign/<int:member_id>/delete', methods=['POST'])
@login_required
@trainer_or_admin_required
def unassign_guide(guide_id, member_id):
    """Remove a guide assignment from a member."""
    assignment = GuideAssignment.query.filter_by(
        guide_id=guide_id,
        member_id=member_id
    ).first_or_404()

    # Check access
    if current_user.role == 'trainer' and assignment.trainer_id != current_user.id:
        flash('You do not have access to this assignment.', 'danger')
        return redirect(url_for('trainer.members'))

    try:
        assignment.unassign()
        flash('Guide unassigned from member.', 'success')
    except Exception as e:
        flash(f'Error unassigning guide: {str(e)}', 'danger')

    return redirect(url_for('trainer.member_guides', member_id=member_id))


# ==================== DIET PLAN MANAGEMENT ====================

@bp.route('/diet-plans')
@login_required
@trainer_or_admin_required
def list_diet_plans():
    """List all available diet plans."""
    page = request.args.get('page', 1, type=int)
    diet_type = request.args.get('type', None)

    query = DietPlan.query.filter_by(is_active=True)

    if diet_type:
        query = query.filter_by(diet_type=diet_type)

    plans = query.order_by(DietPlan.name.asc()).paginate(page=page, per_page=15)

    return render_template(
        'trainer/diet/list.html',
        plans=plans,
        page=page,
        diet_type_filter=diet_type
    )


@bp.route('/diet-plans/<int:plan_id>')
@login_required
@trainer_or_admin_required
def view_diet_plan(plan_id):
    """View a diet plan with all meals."""
    plan = DietPlan.query.get_or_404(plan_id)
    meals = MealPlan.query.filter_by(diet_plan_id=plan_id).order_by(
        MealPlan.day_name.asc(),
        MealPlan.meal_type.asc()
    ).all()

    return render_template(
        'trainer/diet/detail.html',
        plan=plan,
        meals=meals
    )


@bp.route('/members/<int:member_id>/assign-diet', methods=['GET', 'POST'])
@login_required
@trainer_or_admin_required
def assign_diet_to_member(member_id):
    """Assign a diet plan to a member."""
    member = Member.query.get_or_404(member_id)

    # Check access
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter_by(
            trainer_id=current_user.id,
            member_id=member_id,
            is_active=True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

    if request.method == 'POST':
        try:
            # Deactivate existing diet if any
            existing = DietAssignment.query.filter_by(member_id=member_id, is_active=True).first()
            if existing:
                existing.deactivate()

            diet_plan_id = request.form.get('diet_plan_id', type=int)
            diet_plan = DietPlan.query.get_or_404(diet_plan_id)

            assignment = DietAssignment(
                diet_plan_id=diet_plan_id,
                member_id=member_id,
                trainer_id=current_user.id,
                start_date=datetime.utcnow(),
                notes=request.form.get('notes')
            )
            db.session.add(assignment)
            db.session.commit()
            flash(f'Diet plan "{diet_plan.name}" assigned to {member.user.full_name}.', 'success')
            return redirect(url_for('trainer.members'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error assigning diet: {str(e)}', 'danger')

    # Get available diet plans
    plans = DietPlan.query.filter_by(is_active=True).order_by(DietPlan.name.asc()).all()

    return render_template(
        'trainer/diet/assign_member.html',
        member=member,
        plans=plans
    )


@bp.route('/members/<int:member_id>/diet')
@login_required
@trainer_or_admin_required
def member_diet(member_id):
    """View current diet assignment for a member."""
    member = Member.query.get_or_404(member_id)

    # Check access
    if current_user.role == 'trainer':
        assignment = TrainerAssignment.query.filter_by(
            trainer_id=current_user.id,
            member_id=member_id,
            is_active=True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('trainer.members'))

    diet_assignment = DietAssignment.query.filter_by(member_id=member_id, is_active=True).first()

    if diet_assignment:
        meals = MealPlan.query.filter_by(diet_plan_id=diet_assignment.diet_plan_id).all()
    else:
        meals = []

    return render_template(
        'trainer/diet/member_diet.html',
        member=member,
        diet_assignment=diet_assignment,
        meals=meals
    )


@bp.route('/members/<int:member_id>/diet/remove', methods=['POST'])
@login_required
@trainer_or_admin_required
def remove_member_diet(member_id):
    """Remove diet assignment from member."""
    member = Member.query.get_or_404(member_id)
    diet_assignment = DietAssignment.query.filter_by(member_id=member_id, is_active=True).first()

    # Check access
    if current_user.role == 'trainer':
        if not diet_assignment or diet_assignment.trainer_id != current_user.id:
            flash('You do not have access to this assignment.', 'danger')
            return redirect(url_for('trainer.members'))

    if diet_assignment:
        try:
            diet_assignment.deactivate()
            flash('Diet plan removed from member.', 'success')
        except Exception as e:
            flash(f'Error removing diet: {str(e)}', 'danger')

    return redirect(url_for('trainer.member_diet', member_id=member_id))
