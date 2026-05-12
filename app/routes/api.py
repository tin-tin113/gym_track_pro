"""API routes for mobile and QR code scanning."""
from flask import Blueprint

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/health')
def health():
    return {"status": "ok"}
