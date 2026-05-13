"""Flask application factory and initialization."""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from flask_wtf import FlaskForm
import os
from datetime import datetime

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()


def create_app(config_name='development'):
    """
    Create and configure the Flask application.

    Args:
        config_name: Configuration environment (development, testing, production)

    Returns:
        Configured Flask application
    """
    app = Flask(__name__)

    # Load configuration
    from config import config_by_name
    config_class = config_by_name.get(config_name, 'development')
    app.config.from_object(config_class)

    # Ensure instance folder exists
    instance_path = os.path.join(os.path.dirname(__file__), '../instance')
    os.makedirs(instance_path, exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Configure Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # Register blueprints
    register_blueprints(app)

    # Register CLI commands
    register_cli_commands(app)

    # Error handlers
    register_error_handlers(app)

    # Root route redirect
    @app.route('/')
    def index():
        """Redirect root to login or dashboard based on authentication."""
        from flask_login import current_user
        from flask import redirect, url_for
        if current_user.is_authenticated:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('auth.login'))

    # Create tables and seed data if needed
    with app.app_context():
        try:
            # Import models
            from app.models import user, member, attendance, fitness, trainer, assignment, workout

            # Create all tables
            db.create_all()

            # Upgrade database schema if needed (add missing columns to existing tables)
            upgrade_database_schema(db)

            # Seed admin user if it doesn't exist
            seed_admin_user(db)
            # Seed default staff user if it doesn't exist
            seed_default_staff(db)
        except Exception as e:
            print(f"Warning: Could not initialize database: {e}")

    return app


def register_blueprints(app):
    """Register Flask blueprints for different modules."""
    from app.routes import auth, admin, staff, member, trainer, attendance, fitness, api, reports

    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(staff.bp)
    app.register_blueprint(member.bp)
    app.register_blueprint(trainer.bp)
    app.register_blueprint(attendance.bp)
    app.register_blueprint(fitness.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(reports.bp)


def register_error_handlers(app):
    """Register error handlers for common HTTP errors."""

    @app.errorhandler(404)
    def not_found_error(error):
        return ({
            'error': 'Page not found',
            'status': 404
        }, 404)

    @app.errorhandler(403)
    def forbidden_error(error):
        return ({
            'error': 'Access forbidden',
            'status': 403
        }, 403)

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return ({
            'error': 'Internal server error',
            'status': 500
        }, 500)


def register_cli_commands(app):
    """Register custom Flask CLI commands."""

    @app.cli.command()
    def seed_admin():
        """Seed the database with an admin user."""
        seed_admin_user(db)
        print("Admin user seeded successfully!")

    @app.cli.command()
    def init_db():
        """Initialize the database."""
        db.create_all()
        print("Database initialized!")

    @app.cli.command()
    def drop_db():
        """Drop all database tables."""
        if input("Are you sure? This will delete all data! (yes/no): ").lower() == 'yes':
            db.drop_all()
            print("Database dropped!")
        else:
            print("Cancelled.")


def upgrade_database_schema(db):
    """Upgrade existing database schema by adding missing columns."""
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import OperationalError

    try:
        # Get the database inspector
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        # Upgrade members table
        if 'members' in table_names:
            existing_columns = [col['name'] for col in inspector.get_columns('members')]
            with db.engine.connect() as connection:
                if 'is_approved' not in existing_columns:
                    try:
                        connection.execute(text('ALTER TABLE members ADD COLUMN is_approved BOOLEAN DEFAULT 0'))
                        connection.commit()
                        print("  - Added is_approved column to members table")
                    except OperationalError as e:
                        if 'duplicate column' not in str(e).lower():
                            print(f"    Note: {e}")

                if 'approval_date' not in existing_columns:
                    try:
                        connection.execute(text('ALTER TABLE members ADD COLUMN approval_date DATETIME'))
                        connection.commit()
                        print("  - Added approval_date column to members table")
                    except OperationalError as e:
                        if 'duplicate column' not in str(e).lower():
                            print(f"    Note: {e}")

        # Refresh inspector after potential schema changes
        inspector = inspect(db.engine)

        # Upgrade users table
        if 'users' in table_names:
            existing_users_columns = [col['name'] for col in inspector.get_columns('users')]
            with db.engine.connect() as connection:
                if 'setup_token' not in existing_users_columns:
                    try:
                        connection.execute(text('ALTER TABLE users ADD COLUMN setup_token VARCHAR(255)'))
                        connection.commit()
                        print("  - Added setup_token column to users table")
                    except OperationalError as e:
                        if 'duplicate column' not in str(e).lower():
                            pass

                if 'setup_token_expiry' not in existing_users_columns:
                    try:
                        connection.execute(text('ALTER TABLE users ADD COLUMN setup_token_expiry DATETIME'))
                        connection.commit()
                        print("  - Added setup_token_expiry column to users table")
                    except OperationalError as e:
                        if 'duplicate column' not in str(e).lower():
                            pass

        # Refresh inspector after schema changes
        inspector = inspect(db.engine)

        # Upgrade workouts table
        if 'workouts' in table_names:
            existing_workouts_columns = [col['name'] for col in inspector.get_columns('workouts')]
            with db.engine.connect() as connection:
                if 'trainer_id' not in existing_workouts_columns:
                    try:
                        connection.execute(text('ALTER TABLE workouts ADD COLUMN trainer_id INTEGER'))
                        connection.commit()
                        print("  - Added trainer_id column to workouts table")
                    except OperationalError as e:
                        if 'duplicate column' not in str(e).lower():
                            print(f"    Note: {e}")

                if 'assigned_date' not in existing_workouts_columns:
                    try:
                        connection.execute(text('ALTER TABLE workouts ADD COLUMN assigned_date DATETIME'))
                        connection.commit()
                        print("  - Added assigned_date column to workouts table")
                    except OperationalError as e:
                        if 'duplicate column' not in str(e).lower():
                            print(f"    Note: {e}")
    except Exception as e:
        print(f"  Schema upgrade note: {e}")


def seed_admin_user(db):
    """Seed the database with a default admin user if it doesn't exist."""
    from app.models.user import User

    # Check if admin user already exists
    admin = User.query.filter_by(email='admin@gym.local').first()
    if admin:
        return

    # Create admin user
    admin = User(
        username='admin',
        email='admin@gym.local',
        full_name='System Administrator',
        role='admin',
        is_active=True
    )
    admin.set_password('password123')  # Default password - should be changed after first login

    db.session.add(admin)
    try:
        db.session.commit()
        print("Admin user created: admin@gym.local")
    except Exception as e:
        db.session.rollback()
        print(f"Error creating admin user: {e}")


def seed_default_staff(db):
    """Seed the database with a default staff user if it doesn't exist."""
    from app.models.user import User

    # Check if staff user already exists
    staff = User.query.filter_by(email='staff@gymtrack.local').first()
    if staff:
        return

    # Create default staff user
    staff = User(
        username='staff',
        email='staff@gymtrack.local',
        full_name='Default Staff',
        role='staff',
        is_active=True
    )
    staff.set_password('GymTrack2026!')  # Default password

    db.session.add(staff)
    try:
        db.session.commit()
        print("Default staff user created: staff@gymtrack.local")
    except Exception as e:
        db.session.rollback()
        print(f"Error creating default staff user: {e}")
