"""Fitness tracking and metrics routes."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models.member import Member
from app.models.fitness import FitnessMetric
from app.models.user import User
from app.utils.decorators import trainer_or_admin_required

bp = Blueprint('fitness', __name__, url_prefix='/fitness')


@bp.route('/metrics', methods=['GET', 'POST'])
@login_required
@trainer_or_admin_required
def add_metrics():
    """Add or view fitness metrics for a member."""
    if request.method == 'POST':
        member_id = request.form.get('member_id', type=int)
        metric_date_str = request.form.get('metric_date', '')
        weight = request.form.get('weight', type=float)
        height = request.form.get('height', type=float)
        chest = request.form.get('chest', type=float)
        waist = request.form.get('waist', type=float)
        hips = request.form.get('hips', type=float)
        bicep = request.form.get('bicep', type=float)
        thigh = request.form.get('thigh', type=float)
        body_fat = request.form.get('body_fat_percentage', type=float)

        # Validate
        if not member_id or not metric_date_str or not weight or not height:
            flash('Member, date, weight, and height are required.', 'danger')
            return redirect(url_for('fitness.add_metrics'))

        member = Member.query.get(member_id)
        if not member:
            flash('Member not found.', 'danger')
            return redirect(url_for('fitness.add_metrics'))

        try:
            metric_date = datetime.strptime(metric_date_str, '%Y-%m-%d').date()

            # Create fitness metric
            metric = FitnessMetric(
                member_id=member_id,
                metric_date=metric_date,
                weight=weight,
                height=height,
                chest=chest,
                waist=waist,
                hips=hips,
                bicep=bicep,
                thigh=thigh,
                body_fat_percentage=body_fat,
                created_by_id=current_user.id,
                notes=request.form.get('notes', '')
            )

            # Auto-calculate BMI
            metric.calculate_bmi()

            db.session.add(metric)
            db.session.commit()

            flash(f'✓ Fitness metrics for {member.user.full_name} recorded successfully!', 'success')
            return redirect(url_for('fitness.member_progress', member_id=member_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error recording metrics: {str(e)}', 'danger')
            return redirect(url_for('fitness.add_metrics'))

    # Get members (filter by assigned trainer if not admin)
    if current_user.role == 'admin':
        members = Member.query.filter_by(is_active=True).all()
    else:
        # Trainer sees only assigned members
        from app.models.assignment import TrainerAssignment
        assignments = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.is_active == True
        ).all()
        members = [a.member for a in assignments]

    return render_template('fitness/metrics.html', members=members)


@bp.route('/progress/<int:member_id>')
@login_required
@trainer_or_admin_required
def member_progress(member_id):
    """View member's fitness progress and metrics."""
    member = Member.query.get_or_404(member_id)

    # Check authorization (trainer can only view assigned members)
    if current_user.role == 'trainer':
        from app.models.assignment import TrainerAssignment
        assignment = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('fitness.add_metrics'))

    # Get all metrics
    metrics = FitnessMetric.query.filter_by(member_id=member_id).order_by(
        FitnessMetric.metric_date.desc()
    ).all()

    # Get latest metric
    latest_metric = metrics[0] if metrics else None

    # Get progression data
    weight_trend = FitnessMetric.get_weight_trend(member_id, days=90)
    weight_history = FitnessMetric.get_metric_history(member_id, 'weight', days=90)
    bmi_history = FitnessMetric.get_metric_history(member_id, 'bmi', days=90)
    waist_history = FitnessMetric.get_metric_history(member_id, 'waist', days=90)

    return render_template(
        'fitness/progress.html',
        member=member,
        metrics=metrics,
        latest_metric=latest_metric,
        weight_trend=weight_trend,
        weight_history=weight_history,
        bmi_history=bmi_history,
        waist_history=waist_history
    )


@bp.route('/edit/<int:metric_id>', methods=['GET', 'POST'])
@login_required
@trainer_or_admin_required
def edit_metric(metric_id):
    """Edit an existing fitness metric."""
    metric = FitnessMetric.query.get_or_404(metric_id)
    member = metric.member

    # Check authorization
    if current_user.role == 'trainer' and metric.created_by_id != current_user.id:
        flash('You can only edit metrics you created.', 'danger')
        return redirect(url_for('fitness.member_progress', member_id=member.id))

    if request.method == 'POST':
        try:
            metric.weight = request.form.get('weight', type=float)
            metric.height = request.form.get('height', type=float)
            metric.chest = request.form.get('chest', type=float)
            metric.waist = request.form.get('waist', type=float)
            metric.hips = request.form.get('hips', type=float)
            metric.bicep = request.form.get('bicep', type=float)
            metric.thigh = request.form.get('thigh', type=float)
            metric.body_fat_percentage = request.form.get('body_fat_percentage', type=float)
            metric.notes = request.form.get('notes', '')

            # Recalculate BMI
            metric.calculate_bmi()

            db.session.commit()
            flash('✓ Metrics updated successfully!', 'success')
            return redirect(url_for('fitness.member_progress', member_id=member.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating metrics: {str(e)}', 'danger')

    return render_template('fitness/edit_metric.html', metric=metric, member=member)


@bp.route('/delete/<int:metric_id>', methods=['POST'])
@login_required
@trainer_or_admin_required
def delete_metric(metric_id):
    """Delete a fitness metric record."""
    metric = FitnessMetric.query.get_or_404(metric_id)
    member = metric.member

    # Check authorization
    if current_user.role == 'trainer' and metric.created_by_id != current_user.id:
        flash('You can only delete metrics you created.', 'danger')
        return redirect(url_for('fitness.member_progress', member_id=member.id))

    try:
        db.session.delete(metric)
        db.session.commit()
        flash('✓ Metric deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting metric: {str(e)}', 'danger')

    return redirect(url_for('fitness.member_progress', member_id=member.id))


@bp.route('/api/trends/<int:member_id>')
@login_required
@trainer_or_admin_required
def api_trends(member_id):
    """API endpoint for trend data (JSON for charts)."""
    member = Member.query.get_or_404(member_id)

    # Check authorization
    if current_user.role == 'trainer':
        from app.models.assignment import TrainerAssignment
        assignment = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()
        if not assignment:
            return jsonify({'error': 'Unauthorized'}), 403

    weight_data = FitnessMetric.get_metric_history(member_id, 'weight', days=90)
    bmi_data = FitnessMetric.get_metric_history(member_id, 'bmi', days=90)

    return jsonify({
        'weight': weight_data,
        'bmi': bmi_data
    })


@bp.route('/report/<int:member_id>')
@login_required
@trainer_or_admin_required
def fitness_report(member_id):
    """Generate fitness progress report for printing."""
    member = Member.query.get_or_404(member_id)

    # Check authorization
    if current_user.role == 'trainer':
        from app.models.assignment import TrainerAssignment
        assignment = TrainerAssignment.query.filter(
            TrainerAssignment.trainer_id == current_user.id,
            TrainerAssignment.member_id == member_id,
            TrainerAssignment.is_active == True
        ).first()
        if not assignment:
            flash('You do not have access to this member.', 'danger')
            return redirect(url_for('fitness.add_metrics'))

    # Get all metrics
    metrics = FitnessMetric.query.filter_by(member_id=member_id).order_by(
        FitnessMetric.metric_date
    ).all()

    weight_trend = FitnessMetric.get_weight_trend(member_id, days=90)

    return render_template(
        'fitness/report.html',
        member=member,
        metrics=metrics,
        weight_trend=weight_trend,
        report_date=datetime.utcnow()
    )
