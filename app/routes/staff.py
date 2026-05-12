"""Staff routes."""
from flask import Blueprint

bp = Blueprint('staff', __name__, url_prefix='/staff')

@bp.route('/dashboard')
def dashboard():
    return "Staff Dashboard"
