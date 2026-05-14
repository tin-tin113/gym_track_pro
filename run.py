"""Application entry point."""

import os
from app import create_app, db

# Get configuration name from environment
config_name = os.getenv('FLASK_ENV', 'development')

# Create Flask app
app = create_app(config_name)

if __name__ == '__main__':
    with app.app_context():
        # Create instance folder if it doesn't exist
        instance_path = os.path.join(os.path.dirname(__file__), 'instance')
        os.makedirs(instance_path, exist_ok=True)

        # Import all models to ensure they are registered with SQLAlchemy
        from app.models import user, member, attendance, fitness, trainer, assignment, workout
        from app.models.user import User

        try:
            # Create database tables
            db.create_all()
        except Exception as e:
            print(f"Warning: Could not create database tables: {e}")

        # Seed default staff account if no staff exists
        try:
            existing_staff = User.query.filter_by(role='staff').first()
            if not existing_staff:
                staff_user = User(
                    username='staff',
                    email='staff@gymtrack.local',
                    full_name='Default Staff',
                    role='staff',
                    is_active=True
                )
                staff_user.set_password('GymTrack2026!')
                db.session.add(staff_user)
                db.session.commit()
                print("✓ Default staff account created: username 'staff', password 'GymTrack2026!'")
        except Exception as e:
            print(f"Note: Could not seed default staff (may already exist): {e}")

    # Run development server
    app.run(debug=True, host='0.0.0.0', port=5000)

