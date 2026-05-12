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
        from app.models import user, member, attendance, fitness, trainer, assignment

        try:
            # Create database tables
            db.create_all()
        except Exception as e:
            print(f"Warning: Could not create database tables: {e}")

    # Run development server
    app.run(debug=True, host='0.0.0.0', port=5000)

