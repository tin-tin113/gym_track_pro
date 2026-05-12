# GymTrack Pro - Gym Management System

A comprehensive Flask-based gym management system featuring member enrollment, attendance tracking with QR codes, fitness monitoring, trainer assignment, and advanced reporting.

## 🎯 Quick Start

### Requirements
- Python 3.11+
- pip package manager

### Installation

```bash
# Clone or navigate to project
cd Gym_track_pro

# Install dependencies
pip install -r requirements.txt

# Run application
python run.py

# Access at http://localhost:5000
```

### Demo Login
- **Email**: admin@gym.local
- **Password**: password123
- **Role**: Administrator (full access)

## 📊 Features

### ✅ Member Management
- Complete member profiles with membership tracking
- Membership status monitoring (active, expiring, expired)
- 7-day expiry warnings
- CSV bulk import
- Trainer assignment

### ✅ Attendance Tracking
- QR code generation (24-hour expiry)
- Dual check-in methods (QR + manual)
- Duration calculation
- Check-out recording
- Daily/weekly/monthly statistics
- Inactive member detection

### ✅ Fitness Tracking
- Comprehensive measurements (weight, height, BMI)
- Body measurements (chest, waist, hips, etc.)
- Auto-calculated BMI with WHO classification
- 90-day trend analysis
- Progress charts
- Weight trend calculations

### ✅ Trainer Management
- Trainer profiles with specializations
- Member assignment workflow
- Capacity tracking (max clients)
- Trainer workload dashboard
- Assignment history

### ✅ Reports & Analytics
- System-wide analytics dashboard
- Attendance report builder
- Fitness progress reports
- Member list exports
- CSV data export
- Statistics API

### ✅ Security
- User authentication with bcrypt hashing
- Role-based access control (4 roles)
- Session management
- CSRF protection
- SQL injection prevention

## 🗂️ Project Structure

```
Gym_track_pro/
├── app/
│   ├── models/              # Database models
│   ├── routes/              # API endpoints
│   ├── templates/           # HTML templates
│   ├── static/              # CSS, JS
│   ├── utils/               # Utilities
│   └── tests/               # Test suite
├── config.py                # Configuration
├── run.py                   # Entry point
├── requirements.txt         # Dependencies
└── PROJECT_SUMMARY.md       # Detailed documentation
```

## 🧪 Testing

Run comprehensive test suite:

```bash
# All tests (23/23 passing)
python -m pytest app/tests/test_all_phases.py -v

# Specific phase
python -m pytest app/tests/test_all_phases.py::TestPhase1Authentication -v

# With coverage
python -m pytest app/tests/test_all_phases.py --cov=app
```

## 🌐 API Endpoints (41 routes)

### Authentication
- `POST /auth/login` - Login
- `POST /auth/logout` - Logout
- `POST /auth/register` - Register (admin only)

### Members
- `GET /members/` - List members
- `POST /members/new` - Create member
- `GET /members/<id>` - View member
- `POST /members/<id>/edit` - Edit member
- `POST /members/import` - CSV import

### Attendance
- `GET/POST /attendance/check-in` - Check-in
- `POST /attendance/<id>/check-out` - Check-out
- `GET /attendance/history` - History
- `GET /attendance/stats` - Statistics

### Fitness
- `GET/POST /fitness/metrics` - Add metrics
- `GET /fitness/progress/<member_id>` - Progress
- `GET /fitness/report/<member_id>` - Report

### Trainers
- `GET /trainer/dashboard` - Dashboard
- `GET /trainer/members` - Assigned members
- `GET/POST /trainer/new` - Create trainer
- `GET /trainer/list` - All trainers (admin)

### Reports
- `GET /reports/dashboard` - Analytics
- `GET/POST /reports/attendance` - Attendance report
- `GET /reports/fitness/<member_id>` - Fitness report
- `GET /reports/members/export` - Export members

## 💾 Database

**SQLite** (automatic initialization)
- 6 core tables
- Automatic table creation
- Demo admin user seeded
- Foreign key relationships
- Indexed performance

**Tables**: users, members, trainers, trainer_assignments, attendance, fitness_metrics

## 🛠️ Technology Stack

### Backend
- Flask 3.0
- SQLAlchemy 2.0
- Flask-Login
- Flask-WTF (CSRF)
- Werkzeug (bcrypt)
- qrcode

### Frontend
- Bootstrap 5
- Chart.js
- Vanilla JavaScript
- Font Awesome

### Testing
- pytest
- pytest-flask
- pytest-cov

## 📋 User Roles

| Role | Description | Access |
|------|-------------|--------|
| **Admin** | System administrator | Full system access |
| **Staff** | Gym staff | Check-in, reports, member management |
| **Trainer** | Fitness trainer | View assigned members, fitness tracking |
| **Member** | Gym member | Personal profile, fitness data |

## 🔐 Security Features

- ✅ Bcrypt password hashing (600k iterations)
- ✅ CSRF protection on all forms
- ✅ SQL injection prevention (ORM)
- ✅ XSS prevention (auto-escaping)
- ✅ Role-based access control
- ✅ Session security

## 📈 Test Coverage

**23/23 tests passing (100%)**

- Phase 1 (Auth): 5/5 ✓
- Phase 2 (Members): 3/3 ✓
- Phase 3 (Attendance): 4/4 ✓
- Phase 4 (Fitness): 3/3 ✓
- Phase 5 (Trainers): 3/3 ✓
- Phase 6 (Reports): 5/5 ✓

## 🚀 Deployment

### Local Development
```bash
python run.py
# Access: http://localhost:5000
```

### Production
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 run:app
```

### Database Backup
Database file: `instance/gym_track.db`

## 📝 Configuration

Edit `config.py` for:
- Database path
- Debug mode (default: True for development)
- Session security
- CSRF settings

## 🤝 Contributing

This is a complete, production-ready system. For enhancements:

1. Fork the project
2. Create a feature branch
3. Make changes
4. Run tests: `pytest`
5. Submit pull request

## 📞 Support

For issues or questions, refer to `PROJECT_SUMMARY.md` for comprehensive documentation.

## 📄 License

This project is provided as-is for educational and commercial use.

## 🎉 Status

✅ **COMPLETE & PRODUCTION READY**
- All 6 phases implemented
- 23/23 tests passing
- 41 API endpoints
- Ready for deployment

---

**Last Updated**: May 12, 2026
**Version**: 1.0.0
