"""Authentication routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime
from app import db
from app.models.user import User
from app.models.member import Member
from app.utils.decorators import admin_required
from werkzeug.security import generate_password_hash

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('auth.login'))

        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('This account has been deactivated.', 'warning')
            return redirect(url_for('auth.login'))

        # Check if member is approved (if member role)
        if user.role == 'member':
            from app.models.member import Member
            member = Member.query.filter_by(user_id=user.id).first()
            if member and not member.is_approved:
                # Allow login so they can see pending status page
                login_user(user, remember=request.form.get('remember', False))
                return redirect(url_for('auth.pending_status'))

        login_user(user, remember=request.form.get('remember', False))
        flash(f'Welcome back, {user.full_name}!', 'success')

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)

        # Role-aware redirect
        if user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'staff':
            return redirect(url_for('reports.dashboard'))
        elif user.role == 'trainer':
            return redirect(url_for('trainer.dashboard'))
        elif user.role == 'member':
            # Members redirect to their own fitness report
            from app.models.member import Member
            member = Member.query.filter_by(user_id=user.id).first()
            if member:
                return redirect(url_for('reports.fitness_report', member_id=member.id))

        # Fallback for any role without specific redirect
        return redirect(url_for('admin.dashboard'))

    return render_template('auth/login.html')


@bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle public member self-registration (no login required)."""
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # Validation
        if not all([email, full_name, password, confirm_password]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth.signup'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.signup'))

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('auth.signup'))

        # Check if email already exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login instead.', 'danger')
            return redirect(url_for('auth.signup'))

        try:
            # Create new member user
            username = email.split('@')[0]

            # Ensure unique username
            base_username = username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1

            user = User(
                username=username,
                email=email,
                full_name=full_name,
                role='member',
                is_active=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()  # Get the user ID without committing

            # Create member profile (pending approval)
            from app.models.member import Member
            from datetime import datetime, timedelta

            member = Member(
                user_id=user.id,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
                is_approved=False,  # Require admin approval
                is_active=True
            )
            db.session.add(member)
            db.session.commit()

            flash('Account created successfully! An admin will review and approve your membership shortly. You will receive a confirmation email once approved.', 'info')
            return redirect(url_for('auth.pending_status'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account: {str(e)}', 'danger')
            return redirect(url_for('auth.signup'))

    return render_template('auth/signup.html')


@bp.route('/pending-status', methods=['GET'])
def pending_status():
    """Show pending approval status for unapproved member accounts."""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    # Only members can view pending status
    from app.models.member import Member
    member = Member.query.filter_by(user_id=current_user.id).first()

    if not member or member.is_approved:
        # If approved or no member record, redirect to appropriate dashboard
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'staff':
            return redirect(url_for('reports.dashboard'))
        elif current_user.role == 'trainer':
            return redirect(url_for('trainer.dashboard'))
        else:
            return redirect(url_for('auth.login'))

    return render_template('auth/pending_status.html', member=member)


@bp.route('/register', methods=['GET', 'POST'])
@login_required
@admin_required
def register():
    """Handle user registration (admin only)."""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role', 'member')

        # Validation
        if not all([username, email, full_name, password, confirm_password]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth.register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('auth.register'))

        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('auth.register'))

        # Create new user
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role=role,
            is_active=True
        )
        user.set_password(password)

        db.session.add(user)
        try:
            db.session.commit()
            flash(f'User {username} created successfully!', 'success')
            return redirect(url_for('auth.register'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')
            return redirect(url_for('auth.register'))

    return render_template('auth/register.html')


@bp.route('/setup-password/<token>', methods=['GET', 'POST'])
def setup_password(token):
    """Handle one-time password setup for new trainers/staff."""
    user = User.query.filter_by(setup_token=token).first()

    if not user:
        flash('Invalid setup link.', 'danger')
        return redirect(url_for('auth.login'))

    # Check if token has expired
    if user.setup_token_expiry < datetime.utcnow():
        flash('Setup link has expired. Please contact admin for a new link.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not all([password, confirm_password]):
            flash('Password fields are required.', 'danger')
            return redirect(url_for('auth.setup_password', token=token))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.setup_password', token=token))

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('auth.setup_password', token=token))

        try:
            # Set password and clear setup token
            user.set_password(password)
            user.setup_token = None
            user.setup_token_expiry = None
            db.session.commit()

            flash('Password set successfully! You can now login.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error setting password: {str(e)}', 'danger')
            return redirect(url_for('auth.setup_password', token=token))

    return render_template('auth/setup_password.html', token=token)


@bp.route('/profile')
@login_required
def profile():
    """View current user's profile (works for all roles)."""
    user = current_user

    # Get role-specific additional info if available
    member = None
    trainer = None

    if user.role == 'member':
        from app.models.member import Member
        member = Member.query.filter_by(user_id=user.id).first()
    elif user.role == 'trainer':
        from app.models.trainer import Trainer
        trainer = Trainer.query.filter_by(user_id=user.id).first()

    return render_template(
        'auth/profile.html',
        user=user,
        member=member,
        trainer=trainer
    )
