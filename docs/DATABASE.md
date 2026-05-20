# GymTrack Pro - Database Schema

**Database Type**: SQLite (development), PostgreSQL (production ready)
**ORM**: SQLAlchemy 2.0.48
**Last Updated**: May 12, 2026

---

## Database Overview

```
Users (auth base)
├─ Members (profile extension)
│  ├─ Attendance (check-in logs)
│  ├─ FitnessMetrics (body measurements)
│  └─ TrainerAssignments (links to trainers)
├─ Trainers (profile extension)
│  └─ TrainerAssignments (links to members)
└─ AuditLog (compliance tracking)
```

---

## Table: users

**Purpose**: Authentication and base user data for all system participants

| Column | Type | Constraints | Description |
|--------|------|-----------|-------------|
| id | INTEGER | PRIMARY KEY | Unique user identifier |
| username | VARCHAR(80) | UNIQUE, NOT NULL, INDEX | Login username |
| email | VARCHAR(120) | UNIQUE, NOT NULL, INDEX | Email address |
| password_hash | VARCHAR(255) | NOT NULL | Bcrypt hashed password |
| full_name | VARCHAR(120) | NOT NULL | Display name |
| role | VARCHAR(20) | NOT NULL, DEFAULT='member' | admin \| staff \| trainer \| member |
| is_active | BOOLEAN | NOT NULL, DEFAULT=True | Account status |
| created_at | DATETIME | NOT NULL, DEFAULT=NOW() | Creation timestamp |
| updated_at | DATETIME | NOT NULL, DEFAULT=NOW() | Last update timestamp |

**Relationships**:
```
user.member      ← Foreign key from members.user_id
user.trainer     ← Foreign key from trainers.user_id
user.trainer_assignments_as_trainer ← Foreign key from trainer_assignments.trainer_id
user.fitness_records_created ← Foreign key from fitness_metrics.created_by_id
```

**Indexes**:
```sql
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

**Sample Data**:
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@gym.local",
  "password_hash": "$2b$12$...",
  "full_name": "System Administrator",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-05-12T08:00:00",
  "updated_at": "2026-05-12T08:00:00"
}
```

---

## Table: members

**Purpose**: Member profile with personal details and membership tracking

| Column | Type | Constraints | Description |
|--------|------|-----------|-------------|
| id | INTEGER | PRIMARY KEY | Unique member identifier |
| user_id | INTEGER | FOREIGN KEY (users.id), NOT NULL | Link to user account |
| date_of_birth | DATE | Optional | Member's birthdate |
| gender | VARCHAR(10) | Optional | M \| F \| Other |
| phone_number | VARCHAR(20) | Optional | Contact phone |
| emergency_contact | VARCHAR(120) | Optional | Emergency contact name/number |
| membership_type | VARCHAR(20) | NOT NULL, DEFAULT='monthly' | daily \| monthly \| quarterly \| annual |
| membership_start_date | DATE | NOT NULL | Membership start date |
| membership_expiry_date | DATE | NOT NULL | Membership expiration date |
| assigned_trainer_id | INTEGER | FOREIGN KEY (users.id), Optional | Primary trainer ID |
| profile_image_url | VARCHAR(255) | Optional | Image file path |
| notes | TEXT | Optional | Admin notes |
| is_active | BOOLEAN | NOT NULL, DEFAULT=True | Member status |
| created_at | DATETIME | NOT NULL, DEFAULT=NOW() | Creation time |
| updated_at | DATETIME | NOT NULL, DEFAULT=NOW() | Update time |

**Relationships**:
```
member.user ← One-to-one with users
member.trainer ← One-to-one foreign key to users (assigned_trainer_id)
member.attendance_records ← One-to-many with attendance
member.fitness_metrics ← One-to-many with fitness_metrics
member.trainer_assignments ← One-to-many with trainer_assignments
```

**Indexes**:
```sql
CREATE INDEX idx_members_user_id ON members(user_id);
CREATE INDEX idx_members_assigned_trainer_id ON members(assigned_trainer_id);
CREATE INDEX idx_members_membership_expiry ON members(membership_expiry_date);
```

**Methods** (SQLAlchemy):
```python
is_membership_active()           # Check if membership is still valid
is_membership_expiring_soon()    # Check if expiring within 7 days
days_until_expiry()              # Days until membership expires
days_since_last_visit()          # Last gym visit
```

**Sample Data**:
```json
{
  "id": 1,
  "user_id": 10,
  "date_of_birth": "1990-05-15",
  "gender": "M",
  "phone_number": "555-1234",
  "membership_type": "monthly",
  "membership_start_date": "2026-05-12",
  "membership_expiry_date": "2026-06-12",
  "assigned_trainer_id": 2,
  "is_active": true
}
```

---

## Table: attendance

**Purpose**: Daily check-in and check-out logging for members

| Column | Type | Constraints | Description |
|--------|------|-----------|-------------|
| id | INTEGER | PRIMARY KEY | Unique record identifier |
| member_id | INTEGER | FOREIGN KEY (members.id), NOT NULL, INDEX | Member reference |
| check_in_time | DATETIME | NOT NULL, INDEX | Check-in timestamp |
| check_out_time | DATETIME | Optional | Check-out timestamp |
| duration_minutes | INTEGER | Optional | Calculated session duration |
| qr_code | VARCHAR(100) | UNIQUE, INDEX, Optional | QR session token |
| created_at | DATETIME | NOT NULL, DEFAULT=NOW() | Record creation time |

**Relationships**:
```
attendance.member ← Many-to-one with members
```

**Indexes**:
```sql
CREATE INDEX idx_attendance_member_id ON attendance(member_id);
CREATE INDEX idx_attendance_check_in_time ON attendance(check_in_time);
CREATE INDEX idx_attendance_qr_code ON attendance(qr_code);
```

**Methods**:
```python
calculate_duration()             # Calculate duration_minutes
is_duplicate_checkin()          # Check if member checked in today
get_attendance_stats()          # Get visit count and averages
```

**Sample Data**:
```json
{
  "id": 1,
  "member_id": 1,
  "check_in_time": "2026-05-12T09:30:00",
  "check_out_time": "2026-05-12T11:15:00",
  "duration_minutes": 105,
  "qr_code": "uuid-1234567890",
  "created_at": "2026-05-12T09:30:00"
}
```

---

## Table: fitness_metrics

**Purpose**: Track member body measurements and fitness progress

| Column | Type | Constraints | Description |
|--------|------|-----------|-------------|
| id | INTEGER | PRIMARY KEY | Unique metric record |
| member_id | INTEGER | FOREIGN KEY (members.id), NOT NULL, INDEX | Member reference |
| metric_date | DATE | NOT NULL | Date of measurement |
| weight | FLOAT | Optional | Weight in kg |
| height | FLOAT | Optional | Height in cm |
| bmi | FLOAT | Optional | Calculated BMI |
| chest | FLOAT | Optional | Chest measurement in cm |
| waist | FLOAT | Optional | Waist measurement in cm |
| hips | FLOAT | Optional | Hip measurement in cm |
| bicep | FLOAT | Optional | Bicep measurement in cm |
| thigh | FLOAT | Optional | Thigh measurement in cm |
| body_fat_percentage | FLOAT | Optional | Body fat % |
| muscle_mass | FLOAT | Optional | Muscle mass kg |
| notes | TEXT | Optional | Trainer notes |
| created_by_id | INTEGER | FOREIGN KEY (users.id) | Trainer/admin who entered |
| created_at | DATETIME | NOT NULL, DEFAULT=NOW() | Record time |

**Relationships**:
```
fitness_metric.member ← Many-to-one with members
fitness_metric.created_by ← Many-to-one with users
```

**Indexes**:
```sql
CREATE INDEX idx_fitness_member_id ON fitness_metrics(member_id);
CREATE INDEX idx_fitness_metric_date ON fitness_metrics(metric_date);
```

**Methods**:
```python
calculate_bmi()                 # Calculate BMI from weight/height
get_bmi_classification()        # Return classification string
get_weight_trend()              # Calculate % change over period
get_metric_history()            # Get historical data for charts
```

**Sample Data**:
```json
{
  "id": 1,
  "member_id": 1,
  "metric_date": "2026-05-12",
  "weight": 75.5,
  "height": 175,
  "bmi": 24.6,
  "waist": 85,
  "body_fat_percentage": 22.5,
  "created_by_id": 2,
  "notes": "Post-workout measurement"
}
```

---

## Table: trainers

**Purpose**: Trainer profiles with specializations and certifications

| Column | Type | Constraints | Description |
|--------|------|-----------|-------------|
| id | INTEGER | PRIMARY KEY | Trainer ID |
| user_id | INTEGER | FOREIGN KEY (users.id), NOT NULL | Link to user |
| specialization | TEXT | Optional | Comma-separated specializations |
| certifications | TEXT | Optional | Trainer certifications |
| bio | TEXT | Optional | Trainer biography |
| phone_number | VARCHAR(20) | Optional | Contact number |
| profile_image_url | VARCHAR(255) | Optional | Photo URL |
| hourly_rate | FLOAT | Optional | Hourly training rate |
| max_clients | INTEGER | NOT NULL, DEFAULT=10 | Maximum client capacity |
| created_at | DATETIME | NOT NULL, DEFAULT=NOW() | Creation time |
| updated_at | DATETIME | NOT NULL, DEFAULT=NOW() | Update time |

**Relationships**:
```
trainer.user ← One-to-one with users
trainer.trainer_assignments ← One-to-many with trainer_assignments
```

**Methods**:
```python
get_assigned_members_count()    # Get number of active assignments
is_at_capacity()                # Check if max clients reached
get_specializations_list()      # Parse specializations to list
```

**Sample Data**:
```json
{
  "id": 1,
  "user_id": 2,
  "specialization": "Strength, CrossFit, Yoga",
  "certifications": "NASM-CPT, CrossFit Level 1",
  "bio": "Experienced fitness trainer...",
  "max_clients": 10,
  "hourly_rate": 50.0
}
```

---

## Table: trainer_assignments

**Purpose**: Link trainers to members with assignment metadata

| Column | Type | Constraints | Description |
|--------|------|-----------|-------------|
| id | INTEGER | PRIMARY KEY | Assignment ID |
| trainer_id | INTEGER | FOREIGN KEY (users.id), NOT NULL, INDEX | Trainer ID |
| member_id | INTEGER | FOREIGN KEY (members.id), NOT NULL, INDEX | Member ID |
| assignment_date | DATE | NOT NULL | When assignment was made |
| start_date | DATE | NOT NULL | Assignment start date |
| end_date | DATE | Optional | Assignment end date (if ended) |
| assignment_type | VARCHAR(20) | NOT NULL, DEFAULT='primary' | primary \| secondary \| temporary |
| is_active | BOOLEAN | NOT NULL, DEFAULT=True | Active status |
| notes | TEXT | Optional | Notes about assignment |
| created_at | DATETIME | NOT NULL, DEFAULT=NOW() | Creation time |
| updated_at | DATETIME | NOT NULL, DEFAULT=NOW() | Update time |

**Relationships**:
```
assignment.trainer ← Many-to-one with users
assignment.member ← Many-to-one with members
```

**Unique Constraints**:
```sql
UNIQUE(trainer_id, member_id) WHERE is_active=True
-- Ensures one active trainer per member
```

**Indexes**:
```sql
CREATE INDEX idx_assignments_trainer_id ON trainer_assignments(trainer_id);
CREATE INDEX idx_assignments_member_id ON trainer_assignments(member_id);
CREATE INDEX idx_assignments_is_active ON trainer_assignments(is_active);
```

**Methods**:
```python
get_active_assignment()         # Get current trainer for member
get_trainer_members()           # Get all assigned members for trainer
```

**Sample Data**:
```json
{
  "id": 1,
  "trainer_id": 2,
  "member_id": 1,
  "assignment_date": "2026-03-01",
  "start_date": "2026-03-01",
  "end_date": null,
  "assignment_type": "primary",
  "is_active": true
}
```

---

## Table: audit_log

**Purpose**: Track all important system actions for compliance

| Column | Type | Constraints | Description |
|--------|------|-----------|-------------|
| id | INTEGER | PRIMARY KEY | Log entry ID |
| user_id | INTEGER | FOREIGN KEY (users.id), Optional | User performing action |
| action | VARCHAR(255) | NOT NULL | Action performed |
| entity_type | VARCHAR(50) | NOT NULL | Type of entity (Member, Trainer, etc) |
| entity_id | INTEGER | NOT NULL | ID of affected entity |
| old_values | JSON | Optional | Previous values |
| new_values | JSON | Optional | New values |
| ip_address | VARCHAR(50) | Optional | Client IP |
| user_agent | TEXT | Optional | Browser user agent |
| created_at | DATETIME | NOT NULL, DEFAULT=NOW(), INDEX | Timestamp |

**Indexes**:
```sql
CREATE INDEX idx_audit_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_created_at ON audit_log(created_at);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
```

**Sample Data**:
```json
{
  "id": 1,
  "user_id": 1,
  "action": "MEMBER_CREATED",
  "entity_type": "Member",
  "entity_id": 10,
  "new_values": {
    "name": "John Doe",
    "email": "john@gym.local"
  },
  "created_at": "2026-05-12T10:30:00"
}
```

---

## Relationships Diagram

```
┌──────────┐
│  users   │ (id, username, email, role, password_hash)
└────┬─────┘
     │
     ├──────────────────┬──────────────────┐
     │                  │                  │
     ▼                  ▼                  ▼
┌──────────┐      ┌─────────┐      ┌──────────────────┐
│ members  │      │ trainers │      │ trainer_assignments
│ (1-to-1) │      │(1-to-1)  │      │ (junction table)
└────┬─────┘      └─────────┘      └──────────────────┘
     │                                     │
     ├──────────┬──────────┐              │
     │          │          │              │
     ▼          ▼          ▼              ▼
┌──────────┐ ┌─────────┐ ┌──────────────────────┐
│attendance│ │fitness_ │ │trainer_              │
│          │ │metrics  │ │assignments (members) │
└──────────┘ └─────────┘ └──────────────────────┘


audit_log
   └─ references all actions across system
```

---

## Query Examples

### Get Active Members Count
```sql
SELECT COUNT(*) FROM members
WHERE is_active = True
AND membership_expiry_date >= DATE('now');
```

### Get Expiring Memberships (Next 7 Days)
```sql
SELECT m.* FROM members m
WHERE m.membership_expiry_date <= DATE('now', '+7 days')
AND m.membership_expiry_date >= DATE('now')
AND m.is_active = True;
```

### Get Member Attendance This Month
```sql
SELECT COUNT(*) as visits
FROM attendance
WHERE member_id = 1
AND strftime('%Y-%m', check_in_time) = strftime('%Y-%m', 'now');
```

### Get Trainer Workload
```sql
SELECT u.full_name, COUNT(ta.member_id) as member_count
FROM users u
JOIN trainer_assignments ta ON u.id = ta.trainer_id
WHERE ta.is_active = True
GROUP BY u.id
ORDER BY member_count DESC;
```

### Get Member's Weight Trend (30 Days)
```sql
SELECT metric_date, weight
FROM fitness_metrics
WHERE member_id = 1
AND metric_date >= DATE('now', '-30 days')
ORDER BY metric_date ASC;
```

---

## Database Migrations

Using Django migrations:

```bash
# Create migrations (if you change models)
python django_app/manage.py makemigrations

# Apply migrations
python django_app/manage.py migrate
```

---

## Backup & Recovery

### Backup SQLite Database
```bash
cp django_app/db.sqlite3 django_app/db.sqlite3.backup
```

### For Production (PostgreSQL)
```bash
pg_dump -U postgres gym_track > backup.sql
```

### Restore
```bash
psql -U postgres < backup.sql
```

---

## Performance Considerations

### Indexing Strategy
- All foreign keys indexed
- Commonly filtered columns indexed
- Timestamp columns indexed for range queries

### Query Optimization
- Use database-level sorting when possible
- Paginate large result sets
- Use SELECT specific columns instead of SELECT *

### Connection Pooling
```python
# Production config
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True,
}
```

---

## Data Validation

### At Model Level
```python
# Validate membership dates
assert member.membership_start_date <= member.membership_expiry_date

# Validate BMI
assert fitness_metric.weight > 0 and fitness_metric.height > 0

# Validate role
assert user.role in ['admin', 'staff', 'trainer', 'member']
```

---

**Database Schema Version**: 1.0
**Last Updated**: May 12, 2026
**Compatibility**: SQLAlchemy 2.0.48+
