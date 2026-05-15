"""Member management routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models.user import User
from app.models.member import Member
from app.models.trainer import Trainer
from app.models.assignment import TrainerAssignment
from app.models.workout import Workout
from app.models.fitness import FitnessMetric
from app.models.attendance import Attendance
from app.models.workout_guide import WorkoutGuide
from app.models.guide_assignment import GuideAssignment
from app.models.workout_tip import WorkoutTip
from app.models.diet_plan import DietPlan, MealPlan
from app.models.diet_assignment import DietAssignment, MealLog
from app.utils.decorators import staff_or_admin_required, admin_required
import csv
from io import StringIO

bp = Blueprint('member', __name__, url_prefix='/members')


@bp.route('/')
@login_required
@staff_or_admin_required
def list_members():
    """List all members with pagination and filtering."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    status = request.args.get('status', 'all', type=str)
    per_page = 20

    # Build query - use explicit join to avoid ambiguous foreign keys
    query = Member.query.join(User, Member.user_id == User.id)

    # Apply search filter
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )

    # Apply status filter
    if status == 'pending':
        query = query.filter_by(is_approved=False)
    elif status == 'expiring_soon':
        expiry_threshold = datetime.utcnow().date() + timedelta(days=7)
        query = query.filter(
            Member.membership_expiry_date <= expiry_threshold,
            Member.membership_expiry_date >= datetime.utcnow().date(),
            Member.is_approved == True
        )
    elif status == 'expired':
        query = query.filter(Member.membership_expiry_date < datetime.utcnow().date())
    elif status == 'active':
        query = query.filter(
            Member.membership_expiry_date >= datetime.utcnow().date(),
            Member.is_approved == True
        )
    else:  # all
        query = query.filter_by(is_active=True)

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page)
    members = pagination.items

    return render_template(
        'member/list.html',
        members=members,
        pagination=pagination,
        search=search,
        status=status
    )


@bp.route('/new', methods=['GET', 'POST'])
@login_required
@staff_or_admin_required
def create_member():
    """Create a new member."""
    if request.method == 'POST':
        try:
            # Validate input
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone_number', '').strip()
            dob = request.form.get('date_of_birth', '')
            gender = request.form.get('gender', '')
            membership_type = request.form.get('membership_type', 'monthly')
            membership_start = datetime.strptime(request.form.get('membership_start_date'), '%Y-%m-%d').date()
            membership_expiry = datetime.strptime(request.form.get('membership_expiry_date'), '%Y-%m-%d').date()

            if not all([full_name, email, membership_start, membership_expiry]):
                flash('All required fields must be filled.', 'danger')
                return redirect(url_for('member.create_member'))

            if membership_start > membership_expiry:
                flash('Membership start date must be before expiry date.', 'danger')
                return redirect(url_for('member.create_member'))

            # Check if email already exists
            if User.query.filter_by(email=email).first():
                flash('Email already registered.', 'danger')
                return redirect(url_for('member.create_member'))

            # Create user
            user = User(
                username=email.split('@')[0],
                email=email,
                full_name=full_name,
                role='member',
                is_active=True
            )
            user.set_password('GymTrack2026!')  # Default password

            # Create member
            member = Member(
                user=user,
                phone_number=phone,
                gender=gender,
                membership_type=membership_type,
                membership_start_date=membership_start,
                membership_expiry_date=membership_expiry,
                is_active=True
            )

            if dob:
                member.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()

            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            flash(f'Member {full_name} created successfully!', 'success')
            return redirect(url_for('member.view_member', member_id=member.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating member: {str(e)}', 'danger')
            return redirect(url_for('member.create_member'))

    return render_template('member/edit.html', member=None, action='Create')


@bp.route('/<int:member_id>')
@login_required
@staff_or_admin_required
def view_member(member_id):
    """View member profile."""
    member = Member.query.get_or_404(member_id)

    # Get assigned trainer assignment if exists
    trainer_assignment = TrainerAssignment.query.filter(
        TrainerAssignment.member_id == member_id,
        TrainerAssignment.is_active == True
    ).first()

    # Get attendance stats
    from app.models.attendance import Attendance
    attendance_stats = Attendance.get_attendance_stats(member_id, days=30)

    # Get latest fitness metrics
    from app.models.fitness import FitnessMetric
    latest_metrics = FitnessMetric.query.filter_by(member_id=member_id).order_by(
        FitnessMetric.metric_date.desc()
    ).first()

    # Get all available trainers for dropdown
    from app.models.trainer import Trainer
    trainers = Trainer.query.all()

    return render_template(
        'member/detail.html',
        member=member,
        trainer_assignment=trainer_assignment,
        attendance_stats=attendance_stats,
        latest_metrics=latest_metrics,
        trainers=trainers
    )


@bp.route('/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
@staff_or_admin_required
def edit_member(member_id):
    """Edit member details."""
    member = Member.query.get_or_404(member_id)

    if request.method == 'POST':
        try:
            member.user.full_name = request.form.get('full_name', member.user.full_name)
            member.phone_number = request.form.get('phone_number', member.phone_number)
            member.gender = request.form.get('gender', member.gender)
            member.membership_type = request.form.get('membership_type', member.membership_type)

            if request.form.get('membership_start_date'):
                member.membership_start_date = datetime.strptime(
                    request.form.get('membership_start_date'), '%Y-%m-%d'
                ).date()

            if request.form.get('membership_expiry_date'):
                member.membership_expiry_date = datetime.strptime(
                    request.form.get('membership_expiry_date'), '%Y-%m-%d'
                ).date()

            if request.form.get('date_of_birth'):
                member.date_of_birth = datetime.strptime(
                    request.form.get('date_of_birth'), '%Y-%m-%d'
                ).date()

            member.notes = request.form.get('notes', member.notes)

            db.session.commit()
            flash(f'Member {member.user.full_name} updated successfully!', 'success')
            return redirect(url_for('member.view_member', member_id=member.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating member: {str(e)}', 'danger')

    return render_template('member/edit.html', member=member, action='Edit')


@bp.route('/<int:member_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_member(member_id):
    """Soft delete (archive) a member."""
    member = Member.query.get_or_404(member_id)

    try:
        member.is_active = False
        db.session.commit()
        flash(f'Member {member.user.full_name} archived.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error archiving member: {str(e)}', 'danger')

    return redirect(url_for('member.list_members'))


@bp.route('/<int:member_id>/assign-trainer', methods=['POST'])
@login_required
@admin_required
def assign_trainer(member_id):
    """Assign trainer to member."""
    member = Member.query.get_or_404(member_id)
    trainer_id = request.form.get('trainer_id', type=int)

    if not trainer_id:
        flash('Please select a trainer.', 'danger')
        return redirect(url_for('member.view_member', member_id=member_id))

    try:
        trainer = User.query.get(trainer_id)
        if not trainer or trainer.role != 'trainer':
            flash('Invalid trainer selected.', 'danger')
            return redirect(url_for('member.view_member', member_id=member_id))

        # Deactivate previous assignment if exists
        old_assignment = TrainerAssignment.query.filter(
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()

        if old_assignment:
            old_assignment.is_active = False
            old_assignment.end_date = datetime.utcnow().date()

        # Create new assignment
        assignment = TrainerAssignment(
            trainer_id=trainer_id,
            member_id=member_id,
            assignment_date=datetime.utcnow().date(),
            start_date=datetime.utcnow().date(),
            assignment_type='primary',
            is_active=True
        )

        db.session.add(assignment)
        db.session.commit()

        flash(f'Trainer {trainer.full_name} assigned to {member.user.full_name}.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error assigning trainer: {str(e)}', 'danger')

    return redirect(url_for('member.view_member', member_id=member_id))


@bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_csv():
    """Bulk import members from CSV."""
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file uploaded.', 'danger')
            return redirect(url_for('member.import_csv'))

        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('member.import_csv'))

        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'danger')
            return redirect(url_for('member.import_csv'))

        try:
            stream = StringIO(file.stream.read().decode("utf-8"), newline=None)
            csv_reader = csv.DictReader(stream)

            imported = 0
            skipped = 0
            errors = []

            for row_num, row in enumerate(csv_reader, 1):
                try:
                    # Validate required fields
                    if not all(row.get(field, '').strip() for field in ['full_name', 'email']):
                        errors.append({'row': row_num, 'error': 'Missing required fields'})
                        skipped += 1
                        continue

                    # Check duplicate email
                    if User.query.filter_by(email=row['email'].strip()).first():
                        errors.append({'row': row_num, 'error': 'Email already exists'})
                        skipped += 1
                        continue

                    # Parse dates
                    try:
                        start_date = datetime.strptime(row.get('membership_start_date', ''), '%Y-%m-%d').date()
                        expiry_date = datetime.strptime(row.get('membership_expiry_date', ''), '%Y-%m-%d').date()
                    except ValueError:
                        errors.append({'row': row_num, 'error': 'Invalid date format (use YYYY-MM-DD)'})
                        skipped += 1
                        continue

                    # Create user and member
                    user = User(
                        username=row['email'].split('@')[0].lower(),
                        email=row['email'].strip(),
                        full_name=row['full_name'].strip(),
                        role='member',
                        is_active=True
                    )
                    user.set_password('GymTrack2026!')

                    member = Member(
                        user=user,
                        phone_number=row.get('phone_number', '').strip(),
                        gender=row.get('gender', '').strip(),
                        membership_type=row.get('membership_type', 'monthly').strip(),
                        membership_start_date=start_date,
                        membership_expiry_date=expiry_date,
                        is_active=True
                    )

                    if row.get('date_of_birth', '').strip():
                        try:
                            member.date_of_birth = datetime.strptime(
                                row['date_of_birth'].strip(), '%Y-%m-%d'
                            ).date()
                        except ValueError:
                            pass

                    db.session.add(user)
                    db.session.add(member)
                    db.session.flush()

                    imported += 1

                except Exception as e:
                    errors.append({'row': row_num, 'error': str(e)})
                    skipped += 1

            db.session.commit()

            flash(
                f'Import complete: {imported} members imported, {skipped} skipped.',
                'success' if imported > 0 else 'warning'
            )

            if errors:
                return render_template(
                    'member/import.html',
                    import_result={'imported': imported, 'skipped': skipped, 'errors': errors}
                )

            return redirect(url_for('member.list_members'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error importing CSV: {str(e)}', 'danger')
            return redirect(url_for('member.import_csv'))

    return render_template('member/import.html')


@bp.route('/api/search')
@login_required
@staff_or_admin_required
def search_members():
    """API endpoint for member search (JSON)."""
    query = request.args.get('q', '').strip()

    if len(query) < 2:
        return jsonify([])

    members = Member.query.join(User, Member.user_id == User.id).filter(
        Member.is_active == True,
        (User.full_name.ilike(f'%{query}%')) |
        (User.email.ilike(f'%{query}%'))
    ).limit(10).all()

    return jsonify([
        {
            'id': m.id,
            'name': m.user.full_name,
            'email': m.user.email,
            'phone': m.phone_number or 'N/A',
            'status': 'Expiring Soon' if m.is_membership_expiring_soon() else ('Expired' if not m.is_membership_active() else 'Active')
        }
        for m in members
    ])


# ==================== Member Self-Service Routes (Member Dashboard) ====================

@bp.route('/dashboard')
@login_required
def member_dashboard():
    """Member dashboard - personal progress overview."""
    # Verify user is a member
    if current_user.role != 'member':
        flash('This page is for members only.', 'danger')
        return redirect(url_for('trainer.trainer_dashboard' if current_user.role == 'trainer' else 'admin.admin_dashboard'))

    member = Member.query.join(User, Member.user_id == User.id).filter(User.id == current_user.id).first()
    if not member:
        flash('Member profile not found.', 'danger')
        return redirect(url_for('auth.login'))

    if not member.is_approved:
        flash('Your account is pending approval. Please wait for admin confirmation.', 'warning')
        return redirect(url_for('auth.pending_status'))

    # Get recent workouts (last 5)
    recent_workouts = Workout.get_recent_workouts(member.id, limit=5)

    # Get exercise summary (last 90 days)
    exercise_summary = Workout.get_exercise_summary(member.id, days=90)

    # Get latest fitness metrics
    latest_metrics = FitnessMetric.query.filter_by(member_id=member.id).order_by(
        FitnessMetric.metric_date.desc()
    ).first()

    # Get weight history (last 30 days)
    weight_history = FitnessMetric.get_metric_history(member.id, 'weight', days=30)

    # Get attendance stats (last 30 days)
    attendance_stats = Attendance.get_attendance_stats(member.id, days=30)

    return render_template(
        'member_dashboard/dashboard.html',
        member=member,
        recent_workouts=recent_workouts,
        exercise_summary=exercise_summary,
        latest_metrics=latest_metrics,
        weight_history=weight_history,
        attendance_stats=attendance_stats
    )


@bp.route('/profile')
@login_required
def member_profile():
    """View member's own profile."""
    if current_user.role != 'member':
        flash('This page is for members only.', 'danger')
        return redirect(url_for('trainer.trainer_dashboard' if current_user.role == 'trainer' else 'admin.admin_dashboard'))

    member = Member.query.join(User, Member.user_id == User.id).filter(User.id == current_user.id).first()
    if not member:
        flash('Member profile not found.', 'danger')
        return redirect(url_for('auth.login'))

    if not member.is_approved:
        flash('Your account is pending approval. Please wait for admin confirmation.', 'warning')
        return redirect(url_for('auth.pending_status'))

    # Get trainer assignment
    trainer_assignment = TrainerAssignment.query.filter(
        TrainerAssignment.member_id == member.id,
        TrainerAssignment.is_active == True
    ).first()

    return render_template(
        'member_dashboard/profile.html',
        member=member,
        trainer_assignment=trainer_assignment
    )


@bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_member_profile():
    """Edit member's own profile."""
    if current_user.role != 'member':
        flash('This page is for members only.', 'danger')
        return redirect(url_for('trainer.trainer_dashboard' if current_user.role == 'trainer' else 'admin.admin_dashboard'))

    member = Member.query.join(User, Member.user_id == User.id).filter(User.id == current_user.id).first()
    if not member:
        flash('Member profile not found.', 'danger')
        return redirect(url_for('auth.login'))

    if not member.is_approved:
        flash('Your account is pending approval. Please wait for admin confirmation.', 'warning')
        return redirect(url_for('auth.pending_status'))

    if request.method == 'POST':
        try:
            member.user.full_name = request.form.get('full_name', member.user.full_name)
            member.phone_number = request.form.get('phone_number', member.phone_number)
            member.user.email = request.form.get('email', member.user.email)

            if request.form.get('date_of_birth'):
                member.date_of_birth = datetime.strptime(
                    request.form.get('date_of_birth'), '%Y-%m-%d'
                ).date()

            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('member.member_profile'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')

    return render_template('member_dashboard/profile_edit.html', member=member)


# ==================== Workout Tracking Routes ====================

@bp.route('/workouts')
@login_required
def list_workouts():
    """List member's workouts."""
    if current_user.role == 'member':
        member = Member.query.join(User, Member.user_id == User.id).filter(User.id == current_user.id).first()
        if not member:
            flash('Member profile not found.', 'danger')
            return redirect(url_for('auth.login'))
        if not member.is_approved:
            flash('Your account is pending approval. Please wait for admin confirmation.', 'warning')
            return redirect(url_for('auth.pending_status'))
    else:
        flash('Access denied.', 'danger')
        return redirect(url_for('trainer.trainer_dashboard' if current_user.role == 'trainer' else 'admin.admin_dashboard'))

    page = request.args.get('page', 1, type=int)
    per_page = 15

    # Get workouts for pagination
    pagination = Workout.query.filter_by(member_id=member.id).order_by(
        Workout.workout_date.desc(), Workout.created_at.desc()
    ).paginate(page=page, per_page=per_page)

    workouts = pagination.items

    return render_template(
        'member_dashboard/workouts.html',
        member=member,
        workouts=workouts,
        pagination=pagination
    )


@bp.route('/workouts/new', methods=['GET', 'POST'])
@login_required
def create_workout():
    """Create a new workout entry."""
    if current_user.role != 'member':
        flash('Only members can create workouts.', 'danger')
        return redirect(url_for('auth.login'))

    member = Member.query.join(User, Member.user_id == User.id).filter(User.id == current_user.id).first()
    if not member:
        flash('Member profile not found.', 'danger')
        return redirect(url_for('auth.login'))

    if not member.is_approved:
        flash('Your account is pending approval. Please wait for admin confirmation.', 'warning')
        return redirect(url_for('auth.pending_status'))

    if request.method == 'POST':
        try:
            workout_date = datetime.strptime(request.form.get('workout_date'), '%Y-%m-%d').date()

            if workout_date > datetime.utcnow().date():
                flash('Workout date cannot be in the future.', 'danger')
                return redirect(url_for('member.create_workout'))

            exercise_name = request.form.get('exercise_name', '').strip()
            exercise_category = request.form.get('exercise_category', '').strip()

            if not all([exercise_name, exercise_category]):
                flash('Exercise name and category are required.', 'danger')
                return redirect(url_for('member.create_workout'))

            workout = Workout(
                member_id=member.id,
                workout_date=workout_date,
                exercise_name=exercise_name,
                exercise_category=exercise_category,
                intensity=request.form.get('intensity', 'moderate'),
                notes=request.form.get('notes', '')
            )

            # Handle optional fields based on exercise type
            if exercise_category in ['Strength', 'strength']:
                sets = request.form.get('sets')
                reps = request.form.get('reps')
                weight = request.form.get('weight')

                if sets:
                    workout.sets = int(sets)
                if reps:
                    workout.reps = int(reps)
                if weight:
                    workout.weight = float(weight)

            elif exercise_category in ['Cardio', 'cardio']:
                duration = request.form.get('duration_minutes')
                distance = request.form.get('distance_km')

                if duration:
                    workout.duration_minutes = int(duration)
                if distance:
                    workout.distance_km = float(distance)

            db.session.add(workout)
            db.session.commit()

            flash(f'Workout "{exercise_name}" logged successfully!', 'success')
            return redirect(url_for('member.list_workouts'))

        except ValueError as e:
            flash('Invalid input: Please check your data format.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error logging workout: {str(e)}', 'danger')

    return render_template('member_dashboard/workout_form.html', member=member, workout=None, now=datetime.utcnow)


@bp.route('/workouts/<int:workout_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_workout(workout_id):
    """Edit a workout entry."""
    workout = Workout.query.get_or_404(workout_id)
    member = workout.member

    # Verify ownership
    if current_user.role == 'member' and member.user_id != current_user.id:
        flash('You can only edit your own workouts.', 'danger')
        return redirect(url_for('member.list_workouts'))

    # Check approval status for members
    if current_user.role == 'member' and not member.is_approved:
        flash('Your account is pending approval. Please wait for admin confirmation.', 'warning')
        return redirect(url_for('auth.pending_status'))

    # Check if trainer-assigned: members cannot edit trainer-assigned workouts
    if current_user.role == 'member' and workout.trainer_id is not None:
        flash('You cannot edit trainer-assigned workouts.', 'danger')
        return redirect(url_for('member.list_workouts'))

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
            return redirect(url_for('member.list_workouts'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating workout: {str(e)}', 'danger')

    return render_template('member_dashboard/workout_form.html', member=member, workout=workout, now=datetime.utcnow)


@bp.route('/workouts/<int:workout_id>/delete', methods=['POST'])
@login_required
def delete_workout(workout_id):
    """Delete a workout entry."""
    workout = Workout.query.get_or_404(workout_id)
    member = workout.member

    # Verify ownership
    if current_user.role == 'member' and member.user_id != current_user.id:
        flash('You can only delete your own workouts.', 'danger')
        return redirect(url_for('member.list_workouts'))

    # Check approval status for members
    if current_user.role == 'member' and not member.is_approved:
        flash('Your account is pending approval. Please wait for admin confirmation.', 'warning')
        return redirect(url_for('auth.pending_status'))

    # Check if trainer-assigned: members cannot delete trainer-assigned workouts
    if current_user.role == 'member' and workout.trainer_id is not None:
        flash('You cannot delete trainer-assigned workouts.', 'danger')
        return redirect(url_for('member.list_workouts'))

    try:
        exercise_name = workout.exercise_name
        db.session.delete(workout)
        db.session.commit()
        flash(f'Workout "{exercise_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting workout: {str(e)}', 'danger')

    return redirect(url_for('member.list_workouts'))


# ==================== MEMBER WORKOUT PROGRAMS ====================

@bp.route('/programs')
@login_required
def member_programs():
    """View assigned workout guides and current diet plan (unified programs dashboard)."""
    member = Member.query.filter_by(user_id=current_user.id).first_or_404()

    # Get active guide assignments
    active_guides = GuideAssignment.query.filter_by(
        member_id=member.id,
        is_active=True,
        is_completed=False
    ).all()

    # Get completed guides
    completed_guides = GuideAssignment.query.filter_by(
        member_id=member.id,
        is_completed=True
    ).all()

    # Get current diet assignment
    current_diet = DietAssignment.query.filter_by(
        member_id=member.id,
        is_active=True
    ).first()

    # Get recent workouts
    recent_workouts = Workout.query.filter_by(member_id=member.id).order_by(
        Workout.workout_date.desc()
    ).limit(5).all()

    # Calculate stats
    stats = {
        'active_guides': len(active_guides),
        'completed_guides': len(completed_guides),
        'current_diet': current_diet is not None,
        'recent_workouts': len(recent_workouts)
    }

    return render_template(
        'member_dashboard/programs.html',
        member=member,
        active_guides=active_guides,
        completed_guides=completed_guides,
        current_diet=current_diet,
        recent_workouts=recent_workouts,
        stats=stats
    )


@bp.route('/guides/<int:guide_id>')
@login_required
def view_assigned_guide(guide_id):
    """View details of an assigned workout guide with tips."""
    member = Member.query.filter_by(user_id=current_user.id).first_or_404()

    # Check if member has this guide assigned
    assignment = GuideAssignment.query.filter_by(
        guide_id=guide_id,
        member_id=member.id,
        is_active=True
    ).first_or_404()

    guide = assignment.guide
    tips = WorkoutTip.query.filter_by(guide_id=guide_id).order_by(
        WorkoutTip.exercise_name.asc()
    ).all()

    # Get workouts logged from this guide
    logged_workouts = Workout.query.filter_by(
        guide_assignment_id=assignment.id,
        member_id=member.id
    ).order_by(Workout.workout_date.desc()).all()

    # Calculate progress
    progress = assignment.calculate_progress()

    return render_template(
        'member_dashboard/guide_detail.html',
        guide=guide,
        assignment=assignment,
        tips=tips,
        logged_workouts=logged_workouts,
        progress=progress
    )


@bp.route('/guides/library')
@login_required
def browse_guides_library():
    """Browse all approved workout guides (read-only, for inspiration)."""
    member = Member.query.filter_by(user_id=current_user.id).first_or_404()
    page = request.args.get('page', 1, type=int)
    difficulty = request.args.get('difficulty', None)

    query = WorkoutGuide.query.filter_by(status='approved')

    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)

    guides = query.order_by(WorkoutGuide.created_at.desc()).paginate(page=page, per_page=12)

    # Get member's assigned guides for display
    assigned_guide_ids = [a.guide_id for a in GuideAssignment.query.filter_by(
        member_id=member.id,
        is_active=True
    ).all()]

    return render_template(
        'member_dashboard/guides_library.html',
        guides=guides,
        difficulty_filter=difficulty,
        assigned_guide_ids=assigned_guide_ids
    )


@bp.route('/guides/<int:guide_id>/request', methods=['POST'])
@login_required
def request_guide_assignment(guide_id):
    """Member can request trainer to assign a guide."""
    member = Member.query.filter_by(user_id=current_user.id).first_or_404()
    guide = WorkoutGuide.query.filter_by(id=guide_id, status='approved').first_or_404()

    # Get member's primary trainer
    trainer_assignment = TrainerAssignment.query.filter_by(
        member_id=member.id,
        is_active=True
    ).first()

    if not trainer_assignment:
        flash('You do not have an assigned trainer. Contact admin to request program.', 'warning')
        return redirect(url_for('member.browse_guides_library'))

    # Check if already assigned
    existing = GuideAssignment.query.filter_by(
        guide_id=guide_id,
        member_id=member.id,
        is_active=True
    ).first()

    if existing:
        flash('This guide is already assigned to you.', 'info')
        return redirect(url_for('member.view_assigned_guide', guide_id=guide_id))

    flash(f'Request sent to your trainer to assign "{guide.name}".', 'success')
    # In a real system, this might create a notification for the trainer
    # For now, just redirect back

    return redirect(url_for('member.browse_guides_library'))


# ==================== MEMBER DIET TRACKING ====================

@bp.route('/diet/current')
@login_required
def current_diet():
    """View current assigned diet plan and today's meals."""
    member = Member.query.filter_by(user_id=current_user.id).first_or_404()

    diet_assignment = DietAssignment.query.filter_by(
        member_id=member.id,
        is_active=True
    ).first()

    if not diet_assignment:
        flash('No diet plan currently assigned. Contact your trainer.', 'info')
        return render_template(
            'member_dashboard/diet/current.html',
            diet_assignment=None,
            meals_today=[],
            daily_totals={}
        )

    # Get meals for diet plan
    diet_plan = diet_assignment.diet
    meals_all = MealPlan.query.filter_by(diet_plan_id=diet_plan.id).all()

    # Get today's meal logs
    today = datetime.utcnow().date()
    meal_logs_today = MealLog.get_daily_logs(member.id, today)
    daily_totals = MealLog.calculate_daily_macros(member.id, today)
    daily_totals['calories'] = MealLog.calculate_daily_calories(member.id, today)

    # Calculate estimated calorie burn (from workout frequency)
    estimated_burn = diet_assignment.get_calorie_burn_recommendation()

    return render_template(
        'member_dashboard/diet/current.html',
        member=member,
        diet_assignment=diet_assignment,
        diet_plan=diet_plan,
        meals_all=meals_all,
        meal_logs_today=meal_logs_today,
        daily_totals=daily_totals,
        estimated_burn=estimated_burn
    )


@bp.route('/diet/log-meal', methods=['GET', 'POST'])
@login_required
def log_meal():
    """Log a meal consumed."""
    member = Member.query.filter_by(user_id=current_user.id).first_or_404()

    # Check if member has active diet
    diet_assignment = DietAssignment.query.filter_by(
        member_id=member.id,
        is_active=True
    ).first()

    if not diet_assignment:
        flash('No active diet plan. Contact your trainer.', 'warning')
        return redirect(url_for('member.current_diet'))

    if request.method == 'POST':
        try:
            meal_log = MealLog(
                member_id=member.id,
                diet_assignment_id=diet_assignment.id,
                meal_date=datetime.strptime(request.form.get('meal_date', ''), '%Y-%m-%d').date() if request.form.get('meal_date') else datetime.utcnow().date(),
                meal_type=request.form.get('meal_type'),
                meal_name=request.form.get('meal_name'),
                calories_actual=request.form.get('calories_actual', type=int),
                protein_g=request.form.get('protein_g', type=float),
                carbs_g=request.form.get('carbs_g', type=float),
                fats_g=request.form.get('fats_g', type=float),
                notes=request.form.get('notes')
            )
            db.session.add(meal_log)
            db.session.commit()
            flash(f'Meal "{meal_log.meal_name}" logged successfully!', 'success')
            return redirect(url_for('member.current_diet'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error logging meal: {str(e)}', 'danger')

    diet_plan = diet_assignment.diet
    meals_suggested = MealPlan.query.filter_by(diet_plan_id=diet_plan.id).all()

    return render_template(
        'member_dashboard/diet/log_meal.html',
        member=member,
        diet_assignment=diet_assignment,
        suggested_meals=meals_suggested
    )


@bp.route('/diet/progress')
@login_required
def diet_progress():
    """View nutrition progress (calorie tracking, adherence)."""
    member = Member.query.filter_by(user_id=current_user.id).first_or_404()

    diet_assignment = DietAssignment.query.filter_by(
        member_id=member.id,
        is_active=True
    ).first()

    if not diet_assignment:
        flash('No active diet plan.', 'info')
        return render_template(
            'member_dashboard/diet/progress.html',
            diet_assignment=None,
            daily_data=[],
            adherence_score=0
        )

    # Get meal logs for last 30 days
    start_date = (datetime.utcnow() - timedelta(days=30)).date()
    meal_logs = MealLog.get_date_range_logs(member.id, start_date, datetime.utcnow().date())

    # Organize by date
    from collections import defaultdict
    daily_data = defaultdict(lambda: {'calories': 0, 'protein_g': 0, 'carbs_g': 0, 'fats_g': 0})

    for log in meal_logs:
        daily_data[log.meal_date]['calories'] += log.calories_actual or 0
        daily_data[log.meal_date]['protein_g'] += log.protein_g or 0
        daily_data[log.meal_date]['carbs_g'] += log.carbs_g or 0
        daily_data[log.meal_date]['fats_g'] += log.fats_g or 0

    daily_data = sorted(daily_data.items(), key=lambda x: x[0], reverse=True)

    # Calculate adherence
    adherence_score = MealLog.get_adherence_score(member.id, diet_assignment.id, days=30)

    # Get average weekly calories
    avg_calories = MealLog.get_weekly_average_calories(member.id, weeks_back=4)

    return render_template(
        'member_dashboard/diet/progress.html',
        member=member,
        diet_assignment=diet_assignment,
        daily_data=daily_data,
        adherence_score=adherence_score,
        avg_weekly_calories=avg_calories
    )


@bp.route('/diet/history')
@login_required
def diet_history():
    """View past diet assignments."""
    member = Member.query.filter_by(user_id=current_user.id).first_or_404()

    diet_assignments = DietAssignment.query.filter_by(member_id=member.id).order_by(
        DietAssignment.start_date.desc()
    ).all()

    return render_template(
        'member_dashboard/diet/history.html',
        member=member,
        assignments=diet_assignments
    )
