# GymTrack Pro - API Documentation

**API Version**: 1.0
**Base URL**: `http://127.0.0.1:8000` (development)
**Authentication**: Session-based (Django sessions)

---

## Authentication Endpoints

### POST /auth/login
**Description**: Authenticate user with email and password

**Request**:
```
POST /auth/login
Content-Type: application/x-www-form-urlencoded

email=admin@gym.local&password=password123&remember=on
```

**Response**:
```
Status: 302 (Redirect to dashboard)
or
Status: 200 (Show login page with error)
```

**Example cURL**:
```bash
curl -X POST http://localhost:5000/auth/login \
  -d "email=admin@gym.local&password=password123"
```

---

### GET /auth/logout
**Description**: Logout current user and clear session

**Request**:
```
GET /auth/logout
```

**Response**:
```
Status: 302 (Redirect to login)
```

---

### POST /auth/register
**Description**: Create new user (admin only)

**Request**:
```
POST /auth/register
Content-Type: application/x-www-form-urlencoded

username=john&email=john@gym.local&full_name=John Doe&password=password123&confirm_password=password123&role=staff
```

**Parameters**:
- `username` (string, required) - User login username
- `email` (string, required) - User email
- `full_name` (string, required) - Full name
- `password` (string, required) - Password (min 6 chars)
- `confirm_password` (string, required) - Password confirmation
- `role` (string, required) - `admin` | `staff` | `trainer` | `member`

**Response**:
```
Status: 200
{
  "success": true,
  "message": "User created successfully"
}
```

---

## Member Endpoints (Phase 2)

### GET /members
**Description**: List all members with pagination and filtering

**Query Parameters**:
- `page` (int, optional) - Page number (default: 1)
- `per_page` (int, optional) - Items per page (default: 20)
- `search` (string, optional) - Search by name/email
- `status` (string, optional) - `active` | `expiring_soon` | `expired`

**Request**:
```
GET /members?page=1&search=john&status=active
```

**Response**:
```json
{
  "members": [
    {
      "id": 1,
      "name": "John Doe",
      "email": "john@example.com",
      "membership_type": "monthly",
      "membership_expiry": "2026-06-12",
      "status": "active",
      "assigned_trainer": "Jane Smith"
    }
  ],
  "total": 150,
  "page": 1,
  "pages": 8
}
```

---

### POST /members
**Description**: Create new member

**Request**:
```
POST /members
Content-Type: application/json

{
  "full_name": "John Doe",
  "email": "john@gym.local",
  "phone": "555-1234",
  "date_of_birth": "1990-05-15",
  "gender": "M",
  "membership_type": "monthly",
  "membership_start_date": "2026-05-12",
  "membership_expiry_date": "2026-06-12"
}
```

**Response**:
```json
{
  "id": 101,
  "member_id": "MEM001",
  "name": "John Doe",
  "status": "success"
}
```

---

### GET /members/<id>
**Description**: Get member details

**Request**:
```
GET /members/101
```

**Response**:
```json
{
  "id": 101,
  "name": "John Doe",
  "email": "john@gym.local",
  "phone": "555-1234",
  "date_of_birth": "1990-05-15",
  "gender": "M",
  "membership_type": "monthly",
  "membership_start_date": "2026-05-12",
  "membership_expiry_date": "2026-06-12",
  "status": "active",
  "assigned_trainer": "Jane Smith",
  "profile_image_url": "/static/uploads/member_101.jpg"
}
```

---

### PUT /members/<id>
**Description**: Update member details

**Request**:
```
PUT /members/101
Content-Type: application/json

{
  "full_name": "John Doe Updated",
  "phone": "555-5678",
  "membership_type": "quarterly"
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Member updated"
}
```

---

### POST /members/<id>/archive
**Description**: Soft delete (archive) member

**Request**:
```
POST /members/101/archive
```

**Response**:
```json
{
  "status": "success",
  "message": "Member archived"
}
```

---

### POST /members/import
**Description**: Bulk import members from CSV

**Request**:
```
POST /members/import
Content-Type: multipart/form-data

[CSV file with columns: full_name, email, phone, membership_type, membership_expiry]
```

**Response**:
```json
{
  "status": "success",
  "imported": 150,
  "skipped": 5,
  "errors": [
    {"row": 3, "error": "Invalid email"},
    {"row": 7, "error": "Duplicate email"}
  ]
}
```

---

## Attendance Endpoints (Phase 3)

### GET /attendance/check-in
**Description**: Display QR code for check-in

**Request**:
```
GET /attendance/check-in
```

**Response**:
```
HTML page with QR code image
```

---

### POST /api/attendance/check-in
**Description**: Submit QR code or manual member ID for check-in

**Request Option 1 - QR Code**:
```
POST /api/attendance/check-in
Content-Type: application/json

{
  "qr_token": "uuid-string-here"
}
```

**Request Option 2 - Manual Entry**:
```
POST /api/attendance/check-in
Content-Type: application/json

{
  "member_id": 101
}
```

**Response**:
```json
{
  "status": "success",
  "member": "John Doe",
  "check_in_time": "2026-05-12T09:30:00",
  "message": "Check-in successful"
}
```

**Error Response**:
```json
{
  "status": "error",
  "message": "Duplicate check-in today",
  "code": "DUPLICATE_CHECKIN"
}
```

---

### POST /api/attendance/check-out
**Description**: Record member check-out

**Request**:
```
POST /api/attendance/check-out
Content-Type: application/json

{
  "member_id": 101
}
```

**Response**:
```json
{
  "status": "success",
  "member": "John Doe",
  "check_in_time": "2026-05-12T09:30:00",
  "check_out_time": "2026-05-12T11:15:00",
  "duration_minutes": 105,
  "message": "Check-out recorded"
}
```

---

### GET /attendance/history
**Description**: Get attendance history for a member

**Query Parameters**:
- `member_id` (int, required)
- `limit` (int, optional) - Number of records (default: 30)
- `offset` (int, optional) - Starting position

**Request**:
```
GET /attendance/history?member_id=101&limit=30
```

**Response**:
```json
{
  "member_id": 101,
  "records": [
    {
      "date": "2026-05-12",
      "check_in": "09:30:00",
      "check_out": "11:15:00",
      "duration_minutes": 105
    },
    {
      "date": "2026-05-10",
      "check_in": "18:00:00",
      "check_out": "19:45:00",
      "duration_minutes": 105
    }
  ],
  "total_records": 45
}
```

---

## Fitness Endpoints (Phase 4)

### POST /fitness/metrics
**Description**: Add fitness metrics for member

**Request**:
```
POST /fitness/metrics
Content-Type: application/json

{
  "member_id": 101,
  "metric_date": "2026-05-12",
  "weight": 75.5,
  "height": 175,
  "waist": 85,
  "body_fat_percentage": 22.5,
  "notes": "Post-workout measurement"
}
```

**Response**:
```json
{
  "status": "success",
  "metric_id": 201,
  "bmi": 24.6,
  "bmi_classification": "Normal weight",
  "message": "Metrics recorded"
}
```

---

### GET /fitness/progress/<member_id>
**Description**: Get member fitness progress and metrics

**Request**:
```
GET /fitness/progress/101
```

**Response**:
```json
{
  "member_id": 101,
  "latest_metrics": {
    "weight": 75.5,
    "height": 175,
    "bmi": 24.6,
    "bmi_classification": "Normal weight",
    "waist": 85,
    "body_fat": 22.5
  },
  "trends": {
    "weight_change": -2.5,
    "weight_change_percent": -3.2,
    "trend": "down"
  },
  "history": [
    {
      "date": "2026-05-12",
      "weight": 75.5
    },
    {
      "date": "2026-05-05",
      "weight": 78.0
    }
  ]
}
```

---

### GET /fitness/trends/<member_id>
**Description**: Get trend data for charting

**Query Parameters**:
- `metric` (string) - `weight` | `bmi` | `body_fat` | `waist`
- `days` (int) - 30 | 60 | 90

**Request**:
```
GET /fitness/trends/101?metric=weight&days=30
```

**Response**:
```json
{
  "metric": "weight",
  "period_days": 30,
  "data": [
    {"date": "2026-04-12", "value": 80.0},
    {"date": "2026-04-19", "value": 79.2},
    {"date": "2026-04-26", "value": 78.5},
    {"date": "2026-05-03", "value": 77.0},
    {"date": "2026-05-10", "value": 75.8},
    {"date": "2026-05-12", "value": 75.5}
  ]
}
```

---

## Trainer Endpoints (Phase 5)

### GET /trainer/dashboard
**Description**: Get trainer dashboard information

**Request**:
```
GET /trainer/dashboard
```

**Response**:
```json
{
  "trainer_id": 5,
  "name": "Jane Smith",
  "specialization": ["Strength", "CrossFit"],
  "assigned_members": 8,
  "max_capacity": 10,
  "members": [
    {
      "id": 101,
      "name": "John Doe",
      "last_visit": "2026-05-12",
      "visits_this_month": 12,
      "latest_weight": 75.5,
      "assigned_date": "2026-03-01"
    }
  ]
}
```

---

### GET /trainer/members
**Description**: List members assigned to trainer

**Request**:
```
GET /trainer/members
```

**Response**:
```json
{
  "trainer_id": 5,
  "members": [
    {"id": 101, "name": "John", "last_visit": "2026-05-12"},
    {"id": 102, "name": "Jane", "last_visit": "2026-05-11"}
  ],
  "total": 8
}
```

---

### GET /trainer/members/<member_id>/progress
**Description**: Get assigned member's progress

**Request**:
```
GET /trainer/members/101/progress
```

**Response**:
```json
{
  "member": "John Doe",
  "metrics": {
    "latest_weight": 75.5,
    "bmi": 24.6,
    "weight_trend": -3.2
  },
  "attendance": {
    "visits_this_month": 12,
    "last_visit": "2026-05-12",
    "avg_visit_duration": 105
  }
}
```

---

## Reports Endpoints (Phase 6)

### GET /reports
**Description**: Get available reports

**Request**:
```
GET /reports
```

**Response**:
```json
{
  "reports": [
    {"id": 1, "type": "attendance", "name": "Daily Attendance Report"},
    {"id": 2, "type": "membership", "name": "Membership Status Report"},
    {"id": 3, "type": "fitness", "name": "Fitness Progress Report"}
  ]
}
```

---

### POST /reports/generate
**Description**: Generate custom report

**Request**:
```
POST /reports/generate
Content-Type: application/json

{
  "report_type": "attendance",
  "start_date": "2026-05-01",
  "end_date": "2026-05-31",
  "format": "pdf"
}
```

**Response**:
```json
{
  "status": "success",
  "report_id": 42,
  "file_url": "/reports/download/42",
  "format": "pdf"
}
```

---

### GET /reports/download/<id>
**Description**: Download generated report

**Request**:
```
GET /reports/download/42
```

**Response**:
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="attendance_report_2026-05.pdf"

[PDF file data]
```

---

## Admin Endpoints (Phase 7)

### GET /admin/dashboard
**Description**: Admin dashboard with system statistics

**Request**:
```
GET /admin/dashboard
```

**Response**:
```json
{
  "stats": {
    "total_members": 350,
    "active_members": 298,
    "expiring_soon": 12,
    "total_trainers": 8,
    "today_checkins": 127,
    "avg_monthly_visits": 2850
  }
}
```

---

### GET /admin/users
**Description**: List all system users

**Request**:
```
GET /admin/users?page=1&role=staff
```

**Response**:
```json
{
  "users": [
    {
      "id": 2,
      "username": "john",
      "email": "john@gym.local",
      "role": "staff",
      "is_active": true,
      "created_at": "2026-04-01"
    }
  ],
  "total": 45
}
```

---

### POST /admin/users
**Description**: Create new user (same as /auth/register)

---

### PUT /admin/users/<id>
**Description**: Update user

**Request**:
```
PUT /admin/users/5
Content-Type: application/json

{
  "email": "newemail@gym.local",
  "is_active": false
}
```

---

## Error Responses

### 401 Unauthorized
```json
{
  "error": "Unauthorized",
  "status": 401,
  "message": "Please log in first"
}
```

### 403 Forbidden
```json
{
  "error": "Forbidden",
  "status": 403,
  "message": "You do not have permission to access this resource"
}
```

### 404 Not Found
```json
{
  "error": "Not Found",
  "status": 404,
  "message": "Resource not found"
}
```

### 422 Validation Error
```json
{
  "error": "Validation Error",
  "status": 422,
  "errors": {
    "email": "Invalid email format",
    "password": "Password must be at least 6 characters"
  }
}
```

### 500 Server Error
```json
{
  "error": "Internal Server Error",
  "status": 500,
  "message": "An unexpected error occurred"
}
```

---

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request successful |
| 201 | Created - Resource created |
| 302 | Redirect - (Login redirects) |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Not authenticated |
| 403 | Forbidden - Permission denied |
| 404 | Not Found - Resource doesn't exist |
| 422 | Unprocessable - Validation failed |
| 500 | Server Error - Internal error |

---

## Rate Limiting

- **Limit**: 100 requests per minute per IP
- **Header**: `X-RateLimit-Remaining`
- **Status**: 429 when limit exceeded

---

## Pagination

Standard pagination parameters:
```
?page=1&per_page=20
```

Response includes:
```json
{
  "data": [...],
  "pagination": {
    "total": 150,
    "page": 1,
    "per_page": 20,
    "pages": 8
  }
}
```

---

## Authentication

All endpoints (except `/auth/login` and `/auth/register`) require:
- Valid session cookie (Django sessions)
- Appropriate role permissions (RBAC)

---

**API Documentation Version**: 1.0
**Last Updated**: May 12, 2026
