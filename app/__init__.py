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

    # Create tables and seed data if needed
    with app.app_context():
        try:
            # Import models
            from app.models import user, member, attendance, fitness, trainer, assignment

            # Create all tables
            db.create_all()

            # Seed admin user if it doesn't exist
            seed_admin_user(db)
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
