"""Staff management and dashboard routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models.user import User
from app.utils.decorators import admin_required
import secrets
import string

bp = Blueprint('staff', __name__, url_prefix='/staff')


def generate_secure_password(length=12):
    """Generate a secure random password."""
    characters = string.ascii_letters + string.digits + string.punctuation
    # Avoid confusing characters
    characters = characters.replace("'", "").replace('"', "").replace("\\", "").replace("`", "")
    password = ''.join(secrets.choice(characters) for _ in range(length))
    return password


@bp.route('/dashboard')
@login_required
def dashboard():
    """Staff dashboard placeholder."""
    return render_template('staff/dashboard.html')


@bp.route('/list')
@login_required
@admin_required
def list_staff():
    """Admin view of all staff members."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)

    query = User.query.filter_by(role='staff')

    if search:
        query = query.filter(User.full_name.ilike(f'%{search}%') | User.email.ilike(f'%{search}%'))

    pagination = query.paginate(page=page, per_page=20)
    staff = pagination.items

    return render_template(
        'staff/list.html',
        staff=staff,
        pagination=pagination,
        search=search
    )


@bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_staff():
    """Create new staff member (admin only)."""
    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone_number', '').strip()

            if not all([full_name, email]):
                flash('Full name and email are required.', 'danger')
                return redirect(url_for('staff.create_staff'))

            if User.query.filter_by(email=email).first():
                flash('Email already registered.', 'danger')
                return redirect(url_for('staff.create_staff'))

            # Create staff user
            user = User(
                username=email.split('@')[0],
                email=email,
                full_name=full_name,
                role='staff',
                is_active=True
            )
            # Set a placeholder password (will be replaced by staff during setup)
            user.set_password(secrets.token_urlsafe(32))

            # Generate one-time setup token (valid for 24 hours)
            from datetime import timedelta
            setup_token = secrets.token_urlsafe(32)
            user.setup_token = setup_token
            user.setup_token_expiry = datetime.utcnow() + timedelta(hours=24)

            db.session.add(user)
            db.session.commit()

            # Generate setup link
            from flask import url_for
            setup_link = url_for('auth.setup_password', token=setup_token, _external=True)
            flash(f'Staff member {full_name} created! <a href="{setup_link}" target="_blank" class="alert-link">Click here for setup link</a>', 'success')
            return redirect(url_for('staff.list_staff'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating staff member: {str(e)}', 'danger')
            return redirect(url_for('staff.create_staff'))

    return render_template('staff/edit.html', staff_user=None, action='Create')


@bp.route('/<int:staff_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_staff(staff_id):
    """Edit staff member details (admin only)."""
    staff_user = User.query.filter_by(id=staff_id, role='staff').first_or_404()

    if request.method == 'POST':
        try:
            staff_user.full_name = request.form.get('full_name', staff_user.full_name).strip()
            staff_user.email = request.form.get('email', staff_user.email).strip()

            # Check if email changed and if new email is unique
            if staff_user.email != request.form.get('email', '').strip():
                if User.query.filter_by(email=staff_user.email).first():
                    flash('Email already registered.', 'danger')
                    return redirect(url_for('staff.edit_staff', staff_id=staff_id))

            db.session.commit()
            flash(f'Staff member {staff_user.full_name} updated successfully!', 'success')
            return redirect(url_for('staff.list_staff'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating staff member: {str(e)}', 'danger')

    return render_template('staff/edit.html', staff_user=staff_user, action='Edit')


@bp.route('/<int:staff_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_staff(staff_id):
    """Soft delete staff member (deactivate)."""
    staff_user = User.query.filter_by(id=staff_id, role='staff').first_or_404()

    try:
        staff_user.is_active = False
        db.session.commit()
        flash(f'Staff member {staff_user.full_name} has been deactivated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deactivating staff member: {str(e)}', 'danger')

    return redirect(url_for('staff.list_staff'))
