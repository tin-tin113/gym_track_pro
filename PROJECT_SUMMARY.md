# GymTrack Pro — Django Project Summary

GymTrack Pro is a Django-based gym management system.

## What Runs the App

- Django project: `django_app/gymtrack_django/`
- Main Django app: `django_app/tracker/`
- Templates: `django_app/tracker/templates/`
- Static assets: `django_app/tracker/static/`

## Core Features (Django)

- Authentication + role-based access control (Admin/Staff/Trainer/Member)
- Member management (CRUD, CSV import, trainer assignment)
- Attendance (check-in/out, history, stats)
- Fitness metrics + progress views
- Trainer dashboards + assignments
- Reports (dashboard, attendance, fitness)

## How to Run (Local)

1) Install dependencies

```bash
pip install -r requirements.txt
```

2) Configure `.env`

Copy `.env.example` to `.env` and set `DATABASE_URL` (or set `DJANGO_USE_SQLITE=true`).

3) Migrate + run

```bash
python django_app/manage.py migrate
python django_app/manage.py runserver
```

4) Optional demo data

```bash
python django_app/manage.py seed_demo
```

## Testing

```bash
python django_app/manage.py test
```
