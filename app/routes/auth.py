"""Authentication routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.models.user import User
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


@bp.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


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
