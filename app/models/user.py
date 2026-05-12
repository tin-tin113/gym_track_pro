"""User and Role models."""

from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User(UserMixin, db.Model):
    """User model for authentication and role-based access control."""

    __tablename__ = 'users'

    # Role enum values
    ROLES = {
        'admin': 'Administrator',
        'staff': 'Staff',
        'trainer': 'Trainer',
        'member': 'Member'
    }

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    member = db.relationship('Member', backref='user', uselist=False, foreign_keys='Member.user_id')
    trainer = db.relationship('Trainer', backref='user', uselist=False, foreign_keys='Trainer.user_id')

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        """
        Hash and set the user's password.

        Args:
            password: Plain text password to hash
        """
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        """
        Verify a plain text password against the stored hash.

        Args:
            password: Plain text password to verify

        Returns:
            Boolean indicating if password is correct
        """
        return check_password_hash(self.password_hash, password)

    def has_role(self, role):
        """
        Check if user has a specific role.

        Args:
            role: Role to check (admin, staff, trainer, member)

        Returns:
            Boolean indicating if user has the role
        """
        return self.role == role

    def has_any_role(self, *roles):
        """
        Check if user has any of the specified roles.

        Args:
            *roles: Variable length argument list of roles to check

        Returns:
            Boolean indicating if user has any of the roles
        """
        return self.role in roles

    def get_role_display(self):
        """Get human-readable role name."""
        return self.ROLES.get(self.role, self.role)


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))
