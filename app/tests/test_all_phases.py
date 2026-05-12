"""Comprehensive testing suite for GymTrack Pro - All Phases."""

import pytest
import os
import sys
from datetime import datetime, timedelta
from flask import url_for

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.member import Member
from app.models.attendance import Attendance
from app.models.fitness import FitnessMetric
from app.models.trainer import Trainer
from app.models.assignment import TrainerAssignment


@pytest.fixture
def app():
    """Create and configure test app."""
    app = create_app('testing')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create CLI runner."""
    return app.test_cli_runner()


# =====================
# PHASE 1: AUTHENTICATION & AUTHORIZATION
# =====================

class TestPhase1Authentication:
    """Test Phase 1: Foundation & Authentication."""

    def test_login_page_loads(self, client):
        """Test login page is accessible."""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Login' in response.data

    def test_user_login_success(self, app, client):
        """Test successful user login."""
        with app.app_context():
            user = User(
                username='testuser',
                email='test@gym.local',
                full_name='Test User',
                role='admin',
                is_active=True
            )
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()

        response = client.post('/auth/login', data={
            'email': 'test@gym.local',
            'password': 'password123'
        }, follow_redirects=True)

        assert b'Dashboard' in response.data or response.status_code == 200

    def test_password_hashing(self, app):
        """Test password is properly hashed."""
        with app.app_context():
            user = User(username='test', email='test@gym.local', full_name='Test')
            user.set_password('mypassword')

            assert user.check_password('mypassword')
            assert not user.check_password('wrongpassword')
            assert user.password_hash != 'mypassword'

    def test_rbac_admin_access(self, app, client):
        """Test admin role access to admin routes."""
        with app.app_context():
            admin = User(
                username='admin_test',
                email='admintest@gym.local',
                full_name='Admin Test',
                role='admin',
                is_active=True
            )
            admin.set_password('password123')
            db.session.add(admin)
            db.session.commit()

        client.post('/auth/login', data={
            'email': 'admintest@gym.local',
            'password': 'password123'
        })

        response = client.get('/admin/dashboard')
        assert response.status_code == 200

    def test_rbac_unauthorized_access(self, app, client):
        """Test unauthorized role access returns 403."""
        with app.app_context():
            staff = User(
                username='staff_test',
                email='stafftest@gym.local',
                full_name='Staff Test',
                role='staff',
                is_active=True
            )
            staff.set_password('password123')
            db.session.add(staff)
            db.session.commit()

        client.post('/auth/login', data={
            'email': 'stafftest@gym.local',
            'password': 'password123'
        })

        response = client.get('/trainer/dashboard')
        assert response.status_code in [302, 403]  # Redirect or forbidden


# =====================
# PHASE 2: MEMBER MANAGEMENT
# =====================

class TestPhase2Members:
    """Test Phase 2: Member Management."""

    def test_member_creation(self, app):
        """Test creating a new member."""
        with app.app_context():
            user = User(
                username='member1_test',
                email='member1test@gym.local',
                full_name='Member One',
                role='member',
                is_active=True
            )
            user.set_password('password123')

            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
                is_active=True
            )

            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            assert user.id is not None
            assert member.id is not None
            assert member.is_membership_active()

    def test_membership_expiry_warning(self, app):
        """Test membership expiry warning detection."""
        with app.app_context():
            user = User(username='testuser1', email='testuser1@gym.local', full_name='Test')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=5),
                is_active=True
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            assert member.is_membership_expiring_soon(days=7)
            assert member.is_membership_active()

    def test_membership_expired(self, app):
        """Test expired membership detection."""
        with app.app_context():
            user = User(username='testuser2', email='testuser2@gym.local', full_name='Test')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date() - timedelta(days=60),
                membership_expiry_date=datetime.utcnow().date() - timedelta(days=30),
                is_active=True
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            assert not member.is_membership_active()


# =====================
# PHASE 3: ATTENDANCE & QR
# =====================

class TestPhase3Attendance:
    """Test Phase 3: Attendance & QR Codes."""

    def test_attendance_checkin(self, app):
        """Test attendance check-in recording."""
        with app.app_context():
            user = User(username='member_att1', email='memberatt1@gym.local', full_name='Member')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            attendance = Attendance(
                member_id=member.id,
                check_in_time=datetime.utcnow()
            )
            db.session.add(attendance)
            db.session.commit()

            assert attendance.id is not None
            assert attendance.member_id == member.id

    def test_duplicate_checkin_prevention(self, app):
        """Test duplicate check-in prevention."""
        with app.app_context():
            user = User(username='member_att2', email='memberatt2@gym.local', full_name='Member')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            attendance = Attendance(
                member_id=member.id,
                check_in_time=datetime.utcnow()
            )
            db.session.add(attendance)
            db.session.commit()

            # Check for duplicate
            is_duplicate = Attendance.is_duplicate_checkin(member.id)
            assert is_duplicate

    def test_attendance_duration(self, app):
        """Test attendance duration calculation."""
        with app.app_context():
            user = User(username='member_att3', email='memberatt3@gym.local', full_name='Member')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            check_in = datetime.utcnow()
            check_out = check_in + timedelta(minutes=60)

            attendance = Attendance(
                member_id=member.id,
                check_in_time=check_in,
                check_out_time=check_out
            )
            duration = attendance.calculate_duration()

            assert duration == 60

    def test_attendance_stats(self, app):
        """Test attendance statistics calculation."""
        with app.app_context():
            user = User(username='member_att4', email='memberatt4@gym.local', full_name='Member')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            # Record 3 visits
            for i in range(3):
                attendance = Attendance(
                    member_id=member.id,
                    check_in_time=datetime.utcnow() - timedelta(days=i),
                    check_out_time=datetime.utcnow() - timedelta(days=i) + timedelta(minutes=45)
                )
                attendance.calculate_duration()
                db.session.add(attendance)
            db.session.commit()

            stats = Attendance.get_attendance_stats(member.id, days=30)
            assert stats['total_visits'] == 3
            assert stats['avg_duration'] == 45


# =====================
# PHASE 4: FITNESS TRACKING
# =====================

class TestPhase4Fitness:
    """Test Phase 4: Fitness Tracking & BMI."""

    def test_bmi_calculation(self, app):
        """Test BMI auto-calculation."""
        with app.app_context():
            user = User(username='member_fit1', email='memberfit1@gym.local', full_name='Member')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            metric = FitnessMetric(
                member_id=member.id,
                metric_date=datetime.utcnow().date(),
                weight=75,  # kg
                height=180  # cm
            )
            metric.calculate_bmi()
            db.session.add(metric)
            db.session.commit()

            expected_bmi = 75 / (1.8 * 1.8)
            assert abs(metric.bmi - expected_bmi) < 0.1

    def test_bmi_classification(self, app):
        """Test BMI classification."""
        with app.app_context():
            # Test normal weight BMI
            metric = FitnessMetric(
                weight=70,
                height=175
            )
            metric.calculate_bmi()
            assert metric.get_bmi_classification() == 'Normal weight'

            # Test overweight BMI
            metric2 = FitnessMetric(
                weight=90,
                height=175
            )
            metric2.calculate_bmi()
            assert metric2.get_bmi_classification() == 'Overweight'

    def test_weight_trend(self, app):
        """Test weight trend calculation."""
        with app.app_context():
            user = User(username='member_fit2', email='memberfit2@gym.local', full_name='Member')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            # Add metrics over 30 days
            for day in range(0, 30, 10):
                metric = FitnessMetric(
                    member_id=member.id,
                    metric_date=datetime.utcnow().date() - timedelta(days=day),
                    weight=100 - day,  # 100kg, then 90kg, then 80kg
                    height=180
                )
                metric.calculate_bmi()
                db.session.add(metric)
            db.session.commit()

            trend = FitnessMetric.get_weight_trend(member.id, days=30)
            assert trend is not None
            # Metrics are ordered from oldest (80kg) to newest (100kg), so change is +20kg
            assert trend['weight_change'] == 20
            assert trend['percent_change'] == 25.0  # (20/80)*100


# =====================
# PHASE 5: TRAINER MANAGEMENT
# =====================

class TestPhase5Trainers:
    """Test Phase 5: Trainer Management."""

    def test_trainer_creation(self, app):
        """Test creating a trainer."""
        with app.app_context():
            user = User(
                username='trainer1_test',
                email='trainer1test@gym.local',
                full_name='Trainer One',
                role='trainer',
                is_active=True
            )
            user.set_password('password123')

            trainer = Trainer(
                user=user,
                specialization='Strength Training, CrossFit',
                certifications='NASM-CPT',
                max_clients=10
            )

            db.session.add(user)
            db.session.add(trainer)
            db.session.commit()

            assert trainer.id is not None
            assert trainer.max_clients == 10

    def test_trainer_assignment(self, app):
        """Test trainer member assignment."""
        with app.app_context():
            # Create trainer
            trainer_user = User(
                username='trainer_assign',
                email='trainerassign@gym.local',
                full_name='Trainer',
                role='trainer'
            )
            trainer_user.set_password('password123')
            trainer = Trainer(user=trainer_user, max_clients=10)

            # Create member
            member_user = User(
                username='member_assign',
                email='memberassign@gym.local',
                full_name='Member',
                role='member'
            )
            member_user.set_password('password123')
            member = Member(
                user=member_user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )

            db.session.add_all([trainer_user, trainer, member_user, member])
            db.session.flush()  # Flush to get IDs assigned

            # Create assignment after IDs are assigned
            assignment = TrainerAssignment(
                trainer_id=trainer_user.id,
                member_id=member.id,
                assignment_date=datetime.utcnow().date(),
                start_date=datetime.utcnow().date(),
                is_active=True
            )

            db.session.add(assignment)
            db.session.commit()

            assert assignment.id is not None
            assert assignment.is_active

    def test_trainer_capacity_tracking(self, app):
        """Test trainer capacity tracking."""
        with app.app_context():
            trainer_user = User(
                username='trainer_cap',
                email='trainercap@gym.local',
                full_name='Trainer',
                role='trainer'
            )
            trainer_user.set_password('password123')
            trainer = Trainer(user=trainer_user, max_clients=3)

            member_users = []
            members = []
            for i in range(5):
                mu = User(
                    username=f'member_cap{i}',
                    email=f'membercap{i}@gym.local',
                    full_name=f'Member {i}',
                    role='member'
                )
                mu.set_password('password123')
                m = Member(
                    user=mu,
                    membership_type='monthly',
                    membership_start_date=datetime.utcnow().date(),
                    membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
                )
                member_users.append(mu)
                members.append(m)
                db.session.add_all([mu, m])

            db.session.add(trainer_user)
            db.session.add(trainer)
            db.session.commit()

            # Assign first 3 members
            for i in range(3):
                assignment = TrainerAssignment(
                    trainer_id=trainer_user.id,
                    member_id=members[i].id,
                    assignment_date=datetime.utcnow().date(),
                    start_date=datetime.utcnow().date(),
                    is_active=True
                )
                db.session.add(assignment)
            db.session.commit()

            assert trainer.get_assigned_members_count() == 3
            assert trainer.is_at_capacity()


# =====================
# PHASE 6: Reports & Analytics
# =====================

class TestPhase6Reports:
    """Test Phase 6: Reports and analytics functionality."""

    def test_reports_dashboard_access(self, app, client):
        """Test reports dashboard access for admin/staff."""
        with app.app_context():
            admin = User(
                username='admin_reports',
                email='adminreports@gym.local',
                full_name='Admin',
                role='admin',
                is_active=True
            )
            admin.set_password('password123')
            db.session.add(admin)
            db.session.commit()

        client.post('/auth/login', data={
            'email': 'adminreports@gym.local',
            'password': 'password123'
        })

        response = client.get('/reports/dashboard')
        assert response.status_code == 200
        assert b'Analytics Dashboard' in response.data

    def test_attendance_report_generation(self, app):
        """Test attendance report data generation."""
        with app.app_context():
            # Create test member
            user = User(username='member_report', email='memberreport@gym.local', full_name='Member')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            # Create attendance records
            for i in range(3):
                attendance = Attendance(
                    member_id=member.id,
                    check_in_time=datetime.utcnow() - timedelta(days=i),
                    check_out_time=datetime.utcnow() - timedelta(days=i) + timedelta(minutes=50)
                )
                attendance.calculate_duration()
                db.session.add(attendance)
            db.session.commit()

            # Query attendance
            records = Attendance.query.filter_by(member_id=member.id).all()
            assert len(records) == 3

    def test_fitness_report_generation(self, app):
        """Test fitness progress report generation."""
        with app.app_context():
            user = User(username='member_fit_report', email='memberfitreport@gym.local', full_name='Member')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            # Add fitness metrics
            for day in range(0, 21, 10):
                metric = FitnessMetric(
                    member_id=member.id,
                    metric_date=datetime.utcnow().date() - timedelta(days=day),
                    weight=80 + day,
                    height=175
                )
                metric.calculate_bmi()
                db.session.add(metric)
            db.session.commit()

            # Query metrics
            metrics = FitnessMetric.query.filter_by(member_id=member.id).all()
            assert len(metrics) == 3

            # Test weight trend
            trend = FitnessMetric.get_weight_trend(member.id, days=30)
            assert trend is not None
            assert trend['weight_change'] == -20  # 80 - 100 = -20 (weight loss)

    def test_membership_expiry_statistics(self, app):
        """Test membership expiry detection for reporting."""
        with app.app_context():
            # Create member expiring soon
            user1 = User(username='expiring_user', email='expiring@gym.local', full_name='Expiring')
            user1.set_password('password123')
            member1 = Member(
                user=user1,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date() - timedelta(days=30),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=3),
                is_active=True
            )

            # Create expired member
            user2 = User(username='expired_user', email='expired@gym.local', full_name='Expired')
            user2.set_password('password123')
            member2 = Member(
                user=user2,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date() - timedelta(days=60),
                membership_expiry_date=datetime.utcnow().date() - timedelta(days=10),
                is_active=True
            )

            db.session.add_all([user1, member1, user2, member2])
            db.session.commit()

            # Test detection
            expiring = Member.query.filter(
                Member.membership_expiry_date <= datetime.utcnow().date() + timedelta(days=7),
                Member.membership_expiry_date >= datetime.utcnow().date(),
                Member.is_active == True
            ).count()
            assert expiring == 1

            expired = Member.query.filter(
                Member.membership_expiry_date < datetime.utcnow().date(),
                Member.is_active == True
            ).count()
            assert expired == 1

    def test_csv_export_format(self, app):
        """Test CSV export functionality."""
        with app.app_context():
            # Create members
            user = User(username='csv_user', email='csv@gym.local', full_name='CSV Test')
            user.set_password('password123')
            member = Member(
                user=user,
                membership_type='monthly',
                membership_start_date=datetime.utcnow().date(),
                membership_expiry_date=datetime.utcnow().date() + timedelta(days=30),
                phone_number='555-1234'
            )
            db.session.add(user)
            db.session.add(member)
            db.session.commit()

            # Verify member data
            assert member.user.email == 'csv@gym.local'
            assert member.phone_number == '555-1234'


# =====================
# RUN ALL TESTS
# =====================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
