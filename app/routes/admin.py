"""Admin routes and dashboard."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.utils.decorators import admin_required, staff_or_admin_required
from app.models.user import User
from app.models.member import Member
from app.models.trainer import Trainer
from app import db
from datetime import datetime

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
    pending_approvals = Member.query.filter_by(is_approved=False).count()

    stats = {
        'total_members': total_members,
        'active_members': active_members,
        'total_trainers': total_trainers,
        'total_users': total_users,
        'pending_approvals': pending_approvals,
    }

    return render_template('admin/dashboard.html', stats=stats)


@bp.route('/pending-approvals')
@login_required
@staff_or_admin_required
def pending_approvals():
    """List members pending admin approval."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)

    query = Member.query.filter_by(is_approved=False).join(User, Member.user_id == User.id).filter(User.is_active == True)

    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )

    pagination = query.paginate(page=page, per_page=20)
    pending_members = pagination.items

    return render_template(
        'admin/pending_approvals.html',
        pending_members=pending_members,
        pagination=pagination,
        search=search
    )


@bp.route('/member/<int:member_id>/approve', methods=['POST'])
@login_required
@staff_or_admin_required
def approve_member(member_id):
    """Approve a member's signup (admin only)."""
    member = Member.query.get_or_404(member_id)

    try:
        member.is_approved = True
        member.approval_date = datetime.utcnow()
        db.session.commit()
        flash(f'Member {member.user.full_name} approved successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving member: {str(e)}', 'danger')

    return redirect(url_for('admin.pending_approvals'))


@bp.route('/member/<int:member_id>/reject', methods=['POST'])
@login_required
@staff_or_admin_required
def reject_member(member_id):
    """Reject and delete a member's pending signup (admin only)."""
    member = Member.query.get_or_404(member_id)
    user = member.user

    try:
        # Delete the member profile
        db.session.delete(member)
        # Delete the user
        db.session.delete(user)
        db.session.commit()
        flash(f'Member {user.full_name} rejected and removed from system.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error rejecting member: {str(e)}', 'danger')

    return redirect(url_for('admin.pending_approvals'))
