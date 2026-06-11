#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Run migrations
python django_app/manage.py migrate

# Collect static files
python django_app/manage.py collectstatic --no-input
