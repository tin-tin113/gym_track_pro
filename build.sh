#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Ensure media directory exists and copy guide images from tracked static files
mkdir -p django_app/media/guide_images
cp django_app/tracker/static/images/*.jpg django_app/media/
cp django_app/tracker/static/images/*.jpg django_app/media/guide_images/



# Run migrations
python django_app/manage.py migrate

# Collect static files
python django_app/manage.py collectstatic --no-input

# Seed demo data (needed for Render Free Tier since interactive shell is disabled)
python django_app/manage.py seed_demo
python django_app/manage.py seed_approved_guides
python django_app/manage.py seed_guides


