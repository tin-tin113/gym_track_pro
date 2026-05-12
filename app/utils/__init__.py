"""Role-based access control decorators."""

from functools import wraps
from flask import abort
from flask_login import current_user


def role_required(*allowed_roles):
    """
    Decorator to enforce role-based access control.

    Usage:
        @role_required('admin')
        @role_required('admin', 'staff')
        def protected_route():
            pass

    Args:
        *allowed_roles: Variable length list of allowed roles

    Returns:
        Decorated function that checks user role before execution
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user is None or not current_user.is_authenticated:
                abort(401)  # Unauthorized
            if not current_user.has_any_role(*allowed_roles):
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """
    Decorator that requires admin role.

    Usage:
        @admin_required
        def admin_only_route():
            pass

    Returns:
        Decorated function that requires admin role
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user is None or not current_user.is_authenticated:
            abort(401)
        if not current_user.has_role('admin'):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def staff_or_admin_required(f):
    """
    Decorator that requires staff or admin role.

    Usage:
        @staff_or_admin_required
        def staff_area():
            pass

    Returns:
        Decorated function that requires staff or admin role
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user is None or not current_user.is_authenticated:
            abort(401)
        if not current_user.has_any_role('staff', 'admin'):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def trainer_or_admin_required(f):
    """
    Decorator that requires trainer or admin role.

    Usage:
        @trainer_or_admin_required
        def trainer_area():
            pass

    Returns:
        Decorated function that requires trainer or admin role
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user is None or not current_user.is_authenticated:
            abort(401)
        if not current_user.has_any_role('trainer', 'admin'):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
