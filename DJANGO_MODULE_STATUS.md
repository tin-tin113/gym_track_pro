# Django Migration Status (GymTrack Pro)

This repo is now **Django-only**. The legacy Flask code has been removed.

Templates and static assets live under:
- `django_app/tracker/templates/**`
- `django_app/tracker/static/**`

Routes are implemented to satisfy the templates (with legacy `url_for()` compatibility in Jinja).

---

## ✅ Implemented (Django)

### Authentication
- Login / Logout
- Profile
- Public signup (member self-registration)
- Admin register (create users)
- Pending approval status page
- One-time password setup (`setup_token` + expiry)

### Member Management (Admin/Staff)
- Member list + search + status filters
- Create member
- Edit member
- Member detail
- Import members from CSV
- Assign trainer to member

### Member Dashboard (Member)
- Dashboard home
- Profile view + profile edit
- Workouts: list, create, edit, delete
- Programs page
- Guides: library, guide detail (assigned), request guide assignment
- Diet: current diet, meal log, progress, history

### Attendance
- Dashboard
- Check-in / check-out
- History
- Stats page
- API endpoints used by attendance pages (active-today, check-out, stats)

### Fitness
- Metrics add/view page (basic support)

### Trainer
- Trainer dashboard (stats + member list)
- Trainer members list with attendance-based stats
- Member drill-down:
  - Member progress
  - Member workouts list
  - Assign workout / edit assigned workout / delete assigned workout
- Trainer management (Admin):
  - List trainers
  - Create trainer
  - Edit trainer
  - Deactivate trainer
  - Manage assignments (assign/unassign members)
  - Regenerate setup link
- Guides (Trainer/Admin):
  - List guides (trainer’s own)
  - Create/edit/delete guide
  - Submit guide for approval
  - Add/delete guide tips
  - Browse approved guide library
  - Member guide assignment + unassignment
- Diets (Trainer/Admin):
  - List diet plans
  - Diet plan detail
  - Member diet page
  - Assign diet to member
  - Remove member diet

### Admin
- Admin dashboard (basic stats)
- Pending member approvals list + search + pagination
- Approve member
- Reject member

### Seeding (Django)
Management command: `python django_app/manage.py seed_demo`
Creates/updates demo accounts (password is `password123`):
- Admin: `admin@gym.local`
- Staff: `staff@gym.local`
- Trainer: `trainer@gym.local`
- Member: `member@gym.local`
Also creates the trainer/member profiles and assigns the demo member to the demo trainer.

---

## 🟡 Partially Implemented

### Admin Guides
Templates exist but Django logic is not fully wired:
- `django_app/tracker/templates/admin/guides/pending.html`
- `django_app/tracker/templates/admin/guides/all.html`
- `django_app/tracker/templates/admin/guides/review.html`

Current Django status:
- ✅ Fully wired: pending/all lists, review page, approve/reject actions.

### Reports
Templates exist but Django logic is not fully wired:
- ✅ Wired:
  - `django_app/tracker/templates/reports/dashboard.html` (stats + top attendees)
  - `django_app/tracker/templates/reports/daily_attendance.html` (HTML + CSV export)
  - `django_app/tracker/templates/reports/attendance_report.html` (HTML + CSV export)
  - `django_app/tracker/templates/reports/fitness_report.html` (HTML + CSV export)

---

## ❌ Not Implemented Yet

### Staff Module
Templates exist but Django support is incomplete:
- ✅ Implemented:
  - `django_app/tracker/templates/staff/dashboard.html` wired (landing page)
  - `django_app/tracker/templates/staff/list.html` wired (pagination + search)
  - `django_app/tracker/templates/staff/edit.html` wired (create + edit)
  - Deactivate staff user
  - Create staff user generates 24h setup link

### API Module
Django equivalents are implemented only where needed by pages (attendance has a few JSON endpoints).

Implemented:
- `/api/health` (basic health check)

---

## Quick Verification Checklist

1) Seed demo accounts:
- `python django_app/manage.py seed_demo`

2) Run Django checks:
- `python django_app/manage.py check`

3) Run Django tests (trainer smoke tests included):
- `python django_app/manage.py test tracker -v 0`
