#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Run migrations
python django_app/manage.py migrate

# Collect static files
python django_app/manage.py collectstatic --no-input

# Seed demo data (needed for Render Free Tier since interactive shell is disabled)
python django_app/manage.py seed_demo

