"""Admin routes and dashboard."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.utils.decorators import admin_required
from app.models.user import User
from app.models.member import Member
from app.models.trainer import Trainer
from app import db

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard with system statistics."""
    total_members = Member.query.count()
    active_members = Member.query.filter_by(is_active=True).count()
    total_trainers = Trainer.query.count()
    total_users = User.query.count()

    stats = {
        'total_members': total_members,
        'active_members': active_members,
        'total_trainers': total_trainers,
        'total_users': total_users,
    }

    return render_template('admin/dashboard.html', stats=stats)
