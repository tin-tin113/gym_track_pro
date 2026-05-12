"""Member management routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models.user import User
from app.models.member import Member
from app.models.trainer import Trainer
from app.models.assignment import TrainerAssignment
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

    # Build query
    query = Member.query.filter_by(is_active=True)

    # Apply search filter
    if search:
        query = query.filter(
            (Member.user.has(User.full_name.ilike(f'%{search}%'))) |
            (Member.user.has(User.email.ilike(f'%{search}%')))
        )

    # Apply status filter
    if status == 'expiring_soon':
        expiry_threshold = datetime.utcnow().date() + timedelta(days=7)
        query = query.filter(
            Member.membership_expiry_date <= expiry_threshold,
            Member.membership_expiry_date >= datetime.utcnow().date()
        )
    elif status == 'expired':
        query = query.filter(Member.membership_expiry_date < datetime.utcnow().date())
    elif status == 'active':
        query = query.filter(Member.membership_expiry_date >= datetime.utcnow().date())

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

    members = Member.query.join(User).filter(
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
