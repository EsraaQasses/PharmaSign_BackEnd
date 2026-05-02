# PharmaSign Frontend Backend API Contract

This document describes the backend contract the frontend should use after the security finalization work.

## Base URL

Local development:

```text
http://127.0.0.1:8000
```

All API paths start with:

```text
/api
```

Example full URL:

```text
http://127.0.0.1:8000/api/auth/login/
```

## Authentication Header

Protected endpoints use:

```text
Authorization: Bearer <access_token>
```

Rules:

- `patient_access_token` is used only for patient endpoints.
- `pharmacist_access_token` is used only for pharmacist endpoints.
- `admin_access_token` is used for admin/organization approval endpoints.
- `qr_token` is not an auth token.
- `qr_token` must never be sent in the `Authorization` header.
- `qr_token` is sent only in request bodies for QR-related endpoints.

If a user becomes pending, rejected, or inactive after a token was issued, protected API requests with that old access token are blocked.

## Final Registration And Auth Flow

This flow applies to both patients and pharmacists:

1. User requests registration OTP using phone number.
2. User submits registration data with OTP.
3. Backend creates the account with `approval_status: "pending"`.
4. Registration response does not include `access` or `refresh`.
5. User cannot log in until organization/admin approves the account.
6. Pending login returns `403 Forbidden`:

```json
{
  "detail": "حسابك قيد مراجعة المنظمة. سيتم تفعيله بعد الموافقة.",
  "approval_status": "pending"
}
```

7. After approval, user logs in with `phone_number` and `password`.
8. OTP is not used during login.
9. Login success returns `access` and `refresh` tokens.

Rejected login returns `403 Forbidden`:

```json
{
  "detail": "تم رفض طلب إنشاء الحساب. يرجى مراجعة المنظمة.",
  "approval_status": "rejected",
  "rejection_reason": "..."
}
```

## OTP Endpoints

### Patient Registration OTP

```text
POST /api/auth/patient/register/request-otp/
```

Request:

```json
{
  "phone_number": "0999000001"
}
```

Alternative field:

```json
{
  "phone": "0999000001"
}
```

Response when `DEBUG=True`:

```json
{
  "detail": "Registration OTP generated successfully.",
  "expires_in_seconds": 300,
  "debug_otp": "123456"
}
```

Response when `DEBUG=False`:

```json
{
  "detail": "Registration OTP generated successfully.",
  "expires_in_seconds": 300
}
```

### Pharmacist Registration OTP

```text
POST /api/auth/pharmacist/register/request-otp/
```

Same request and response shape as patient registration OTP.

### Generic Registration OTP

```text
POST /api/auth/register/request-otp/
```

Patient request:

```json
{
  "role": "patient",
  "phone_number": "0999000001"
}
```

Pharmacist request:

```json
{
  "role": "pharmacist",
  "phone_number": "0999000002"
}
```

## Patient Registration

```text
POST /api/auth/patient/register/
```

Request:

```json
{
  "full_name": "Test Patient",
  "phone_number": "0999000001",
  "password": "StrongPass123!",
  "otp": "123456"
}
```

Optional fields:

- `email`
- `confirm_password`
- `birth_date`
- `gender`
- `address`
- `hearing_disability_level`
- `record_access_pin`

Accepted aliases:

- `name` instead of `full_name`
- `phone` instead of `phone_number`

Success response:

```text
201 Created
```

```json
{
  "detail": "Registration request submitted successfully. Your account is pending organization approval.",
  "approval_status": "pending",
  "user": {
    "id": 13,
    "email": null,
    "phone_number": "0999000001",
    "role": "patient",
    "is_active": true,
    "is_verified": false,
    "approval_status": "pending"
  },
  "profile": {
    "id": 6,
    "full_name": "Test Patient"
  }
}
```

Important:

- No `access` token is returned.
- No `refresh` token is returned.
- Frontend should navigate to a pending approval screen.

## Pharmacist Registration

```text
POST /api/auth/pharmacist/register/
```

Request:

```json
{
  "full_name": "Test Pharmacist",
  "phone_number": "0999000002",
  "password": "StrongPass123!",
  "license_number": "LIC-TEST-0002",
  "pharmacy_name": "Test Pharmacy",
  "pharmacy_address": "Damascus",
  "otp": "123456"
}
```

Optional fields:

- `email`
- `confirm_password`
- `pharmacy_phone_number`
- `latitude`
- `longitude`

Accepted aliases:

- `name` instead of `full_name`
- `phone` instead of `phone_number`
- `license_id` instead of `license_number`

Success response:

```text
201 Created
```

```json
{
  "detail": "Registration request submitted successfully. Your account is pending organization approval.",
  "approval_status": "pending",
  "user": {
    "id": 14,
    "email": null,
    "phone_number": "0999000002",
    "role": "pharmacist",
    "is_active": true,
    "is_verified": false,
    "approval_status": "pending"
  },
  "profile": {
    "id": 3,
    "full_name": "Test Pharmacist",
    "license_number": "LIC-TEST-0002",
    "is_approved": false
  }
}
```

Important:

- No `access` token is returned.
- No `refresh` token is returned.
- Frontend should navigate to a pending approval screen.

## Login

```text
POST /api/auth/login/
```

Request:

```json
{
  "phone_number": "0999000001",
  "password": "StrongPass123!"
}
```

Accepted alias:

```json
{
  "phone": "0999000001",
  "password": "StrongPass123!"
}
```

Email login may still work for compatibility, but frontend should use `phone_number`.

Patient login success:

```text
200 OK
```

```json
{
  "user": {
    "id": 13,
    "email": null,
    "phone_number": "0999000001",
    "role": "patient",
    "is_active": true,
    "is_verified": true,
    "approval_status": "approved"
  },
  "profile": {
    "id": 6,
    "full_name": "Test Patient",
    "national_id": "",
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false
  },
  "access": "<access_token>",
  "refresh": "<refresh_token>"
}
```

Pending login:

```text
403 Forbidden
```

```json
{
  "detail": "حسابك قيد مراجعة المنظمة. سيتم تفعيله بعد الموافقة.",
  "approval_status": "pending"
}
```

Rejected login:

```text
403 Forbidden
```

```json
{
  "detail": "تم رفض طلب إنشاء الحساب. يرجى مراجعة المنظمة.",
  "approval_status": "rejected",
  "rejection_reason": "..."
}
```

Invalid credentials:

```text
400 Bad Request
```

```json
{
  "detail": ["Invalid credentials."]
}
```

Important:

- Login never uses OTP.
- Tokens are returned only after approval.
- Pharmacist can log in only if `user.approval_status = "approved"` and `PharmacistProfile.is_approved = true`.

## Refresh Token

```text
POST /api/auth/refresh/
```

Request:

```json
{
  "refresh": "<refresh_token>"
}
```

Success:

```json
{
  "access": "<new_access_token>"
}
```

If the user is pending, rejected, or inactive, refresh is blocked and does not return a new access token.

Pending refresh response:

```text
403 Forbidden
```

```json
{
  "detail": "حسابك قيد مراجعة المنظمة. سيتم تفعيله بعد الموافقة.",
  "approval_status": "pending"
}
```

Rejected refresh response:

```text
403 Forbidden
```

```json
{
  "detail": "تم رفض طلب إنشاء الحساب. يرجى مراجعة المنظمة.",
  "approval_status": "rejected",
  "rejection_reason": "..."
}
```

## Current User

```text
GET /api/auth/me/
```

Auth:

```text
Authorization: Bearer <access_token>
```

Success returns:

```json
{
  "user": {
    "id": 13,
    "email": null,
    "phone_number": "0999000001",
    "role": "patient",
    "is_active": true,
    "is_verified": true,
    "approval_status": "approved"
  },
  "profile": {
    "id": 6,
    "full_name": "Test Patient",
    "national_id": "",
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false
  }
}
```

If user becomes rejected after token was issued, old access token is blocked:

```text
403 Forbidden
```

```json
{
  "detail": "تم رفض طلب إنشاء الحساب. يرجى مراجعة المنظمة.",
  "approval_status": "rejected",
  "rejection_reason": "..."
}
```

## Logout And Change Password

### Logout

```text
POST /api/auth/logout/
```

Auth required.

Request:

```json
{
  "refresh": "<refresh_token>"
}
```

Success:

```json
{
  "detail": "Logged out successfully."
}
```

### Change Password

```text
POST /api/auth/change-password/
```

Auth required.

Request:

```json
{
  "current_password": "OldPass123!",
  "new_password": "NewStrongPass123!",
  "confirm_password": "NewStrongPass123!"
}
```

Success:

```json
{
  "detail": "Password changed successfully."
}
```

## Admin And Organization Approval Endpoints

Use:

```text
Authorization: Bearer <admin_access_token>
```

### List Registration Requests

```text
GET /api/admin/registration-requests/
```

Returns pending patient/pharmacist registration requests visible to the current admin/organization staff user.

### Approve User

```text
POST /api/admin/users/{user_id}/approve/
```

Response:

```json
{
  "detail": "User approved successfully.",
  "user": {
    "id": 13,
    "phone_number": "0999000001",
    "role": "patient",
    "approval_status": "approved"
  }
}
```

### Reject User

```text
POST /api/admin/users/{user_id}/reject/
```

Request:

```json
{
  "reason": "Invalid documents"
}
```

Response:

```json
{
  "detail": "User rejected successfully.",
  "user": {
    "id": 13,
    "phone_number": "0999000001",
    "role": "patient",
    "approval_status": "rejected"
  }
}
```

Approval permission rules:

- Superuser/staff without organization staff profile can approve/reject all patient and pharmacist registrations.
- Organization staff with `can_manage_patients` can approve/reject patient users only.
- Organization staff with `can_manage_pharmacists` can approve/reject pharmacist users only.
- If staff tries to approve/reject a role they do not manage, backend returns:

```json
{
  "detail": "You do not have permission to approve this user role."
}
```

Security behavior after rejection:

- Old access tokens are blocked by centralized approval enforcement.
- Refresh token cannot mint a new access token.
- Pharmacist rejection sets `PharmacistProfile.is_approved = false`.

## Patient Profile And Settings

Use:

```text
Authorization: Bearer <patient_access_token>
```

### Patient Profile

```text
GET /api/patients/me/
PATCH /api/patients/me/
```

Profile response:

```json
{
  "id": 6,
  "full_name": "Test Patient",
  "phone": "0999000001",
  "national_id": "",
  "blood_type": "",
  "allergies": "",
  "chronic_conditions": "",
  "regular_medications": "",
  "is_pregnant": false,
  "date_of_birth": null,
  "gender": ""
}
```

Editable fields include:

- `full_name`
- `phone`
- `allergies`
- `chronic_conditions`
- `regular_medications`
- `is_pregnant`
- `date_of_birth`
- `gender`

### Patient Settings

```text
GET /api/patients/me/settings/
PATCH /api/patients/me/settings/
```

Settings response:

```json
{
  "notifications_enabled": true,
  "prescription_reminders": true,
  "dark_mode": false,
  "use_biometrics": false,
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:00:00Z"
}
```

Settings persist in the database.

## Pharmacist Profile And Pharmacy

Use:

```text
Authorization: Bearer <pharmacist_access_token>
```

### Pharmacist Profile

```text
GET /api/pharmacist/me/
PATCH /api/pharmacist/me/
```

Backward-compatible alias:

```text
GET /api/pharmacists/me/
PATCH /api/pharmacists/me/
```

Profile response includes pharmacist profile and nested pharmacy data.

Editable fields include:

- `full_name`
- `license_number`
- `phone_number`
- `pharmacy_name`
- `pharmacy_address`
- `pharmacy_phone_number`
- `latitude`
- `longitude`

### Pharmacist Pharmacy

```text
GET /api/pharmacist/me/pharmacy/
PATCH /api/pharmacist/me/pharmacy/
```

Response:

```json
{
  "id": 1,
  "name": "Test Pharmacy",
  "address": "Damascus",
  "phone": "",
  "lat": null,
  "lng": null,
  "has_sign_service": true
}
```

## Patient Login QR

Patient Login QR is different from Patient Session QR.

Admin generates login QR:

```text
POST /api/admin/patients/{patient_id}/login-qr/
```

Auth:

```text
Authorization: Bearer <admin_access_token>
```

Response:

```json
{
  "patient_id": 6,
  "qr_token": "<qr_token>",
  "qr_payload": "<qr_token>",
  "is_active": true,
  "created_at": "2026-05-01T10:00:00Z",
  "revoked_at": null
}
```

Admin revokes login QR:

```text
POST /api/admin/patients/{patient_id}/login-qr/revoke/
```

Patient logs in with QR:

```text
POST /api/auth/patient/qr-login/
```

Request:

```json
{
  "qr_token": "<qr_token>"
}
```

Important:

- `qr_token` is sent in body only.
- `qr_token` is not sent in the `Authorization` header.
- Pending/rejected patient cannot log in with QR.
- Approved patient can log in with QR.
- QR login returns `access` and `refresh` only if the patient is approved.

## Patient Session QR

Patient Session QR is different from Patient Login QR.

Patient generates temporary session QR:

```text
POST /api/patients/me/session-qr/
```

Auth:

```text
Authorization: Bearer <patient_access_token>
```

Response:

```json
{
  "qr_token": "<temporary_session_qr>",
  "qr_payload": "<temporary_session_qr>",
  "expires_at": "2026-05-01T10:05:00Z",
  "expires_in_seconds": 300
}
```

Frontend should display `qr_payload` as the QR image content.

Pharmacist starts session:

```text
POST /api/pharmacist/sessions/start-by-qr/
```

Auth:

```text
Authorization: Bearer <pharmacist_access_token>
```

Request:

```json
{
  "qr_token": "<temporary_session_qr>"
}
```

Alternative field:

```json
{
  "qr_payload": "<temporary_session_qr>"
}
```

Success response:

```json
{
  "session": {
    "id": 12,
    "status": "active",
    "created_at": "2026-05-01T10:00:00Z",
    "expires_at": "2026-05-01T10:30:00Z"
  },
  "patient": {
    "id": 6,
    "full_name": "Test Patient",
    "phone_number": "0999000001",
    "gender": "",
    "birth_date": null
  },
  "medical_info": {
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false,
    "is_breastfeeding": false
  },
  "recent_prescriptions": [],
  "pharmacist": {
    "id": 3,
    "full_name": "Test Pharmacist"
  },
  "pharmacy": {
    "id": 1,
    "name": "Test Pharmacy"
  }
}
```

List sessions:

```text
GET /api/pharmacist/sessions/
GET /api/pharmacist/sessions/?status=active
```

End session:

```text
POST /api/pharmacist/sessions/{session_id}/end/
```

Important:

- Session QR is one-time use.
- Session QR expires.
- Only approved pharmacists can start, list, and end sessions.
- `qr_token` is sent in body only.

## Prescriptions

Frontend should use only the intended MVP prescription routes.

### Pharmacist Routes

Use:

```text
Authorization: Bearer <pharmacist_access_token>
```

```text
POST /api/pharmacist/prescriptions/
GET /api/pharmacist/prescriptions/
GET /api/pharmacist/prescriptions/{prescription_id}/
PATCH /api/pharmacist/prescriptions/{prescription_id}/
POST /api/pharmacist/prescriptions/{prescription_id}/items/
PATCH /api/pharmacist/prescriptions/{prescription_id}/items/{item_id}/
DELETE /api/pharmacist/prescriptions/{prescription_id}/items/{item_id}/
POST /api/pharmacist/prescriptions/{prescription_id}/items/{item_id}/transcribe-audio/
POST /api/pharmacist/prescriptions/{prescription_id}/submit/
```

Create prescription request:

```json
{
  "session_id": 12,
  "patient_id": 6,
  "doctor_name": "Dr. Ahmad",
  "diagnosis": "Flu",
  "notes": "Take medicines after food",
  "items": [
    {
      "medicine_name": "Paracetamol",
      "dosage": "500mg",
      "frequency": "3 times daily",
      "duration": "5 days",
      "instructions_text": "Take one tablet after food three times a day"
    }
  ]
}
```

Important:

- Creating a prescription requires a valid active `session_id`.
- The session must belong to the authenticated pharmacist.
- The `patient_id` must match the session patient.
- Submitted prescriptions are visible to the patient.

### Patient Routes

Use:

```text
Authorization: Bearer <patient_access_token>
```

```text
GET /api/patients/me/prescriptions/
GET /api/patients/me/prescriptions/{prescription_id}/
```

By default, patient prescription list returns submitted prescriptions.

### Legacy Prescription Route Warning

Frontend must not use:

```text
POST /api/prescriptions/
```

Legacy create is blocked and returns:

```json
{
  "detail": "Use /api/pharmacist/prescriptions/ with a valid active patient session to create prescriptions."
}
```

## Frontend Routing Guidance

After registration success:

- Do not store tokens.
- Navigate to `PendingApproval` screen.
- Show:

```text
حسابك قيد مراجعة المنظمة. سيتم تفعيله بعد الموافقة.
```

After login pending response:

- Navigate to or show `PendingApproval` screen.

After login rejected response:

- Show rejected message.
- Show `rejection_reason` if present.
- Do not store tokens.

After successful login:

- Store `access` and `refresh`.
- Route by `user.role`:
  - `patient` -> patient app
  - `pharmacist` -> pharmacist app

When access token expires:

- Call `POST /api/auth/refresh/`.
- If refresh returns pending/rejected/inactive, clear tokens and show the appropriate screen.

When user logs out:

- Call `POST /api/auth/logout/` with refresh token if available.
- Clear local tokens regardless of logout response.

## Endpoint Inventory

| Method | Path | Auth | Role | Frontend use | Notes |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/auth/patient/register/request-otp/` | No | Public | Patient registration OTP | Returns `debug_otp` only in DEBUG |
| POST | `/api/auth/pharmacist/register/request-otp/` | No | Public | Pharmacist registration OTP | Same shape as patient OTP |
| POST | `/api/auth/register/request-otp/` | No | Public | Generic registration OTP | Requires `role` |
| POST | `/api/auth/patient/register/` | No | Public | Patient registration | Returns pending response, no tokens |
| POST | `/api/auth/pharmacist/register/` | No | Public | Pharmacist registration | Returns pending response, no tokens |
| POST | `/api/auth/login/` | No | Public | Login after approval | Uses phone/password, no OTP |
| POST | `/api/auth/refresh/` | No | Public with refresh token | Refresh access token | Blocks pending/rejected/inactive users |
| GET | `/api/auth/me/` | Bearer | Any approved user | Load current user | Old tokens blocked after rejection |
| POST | `/api/auth/logout/` | Bearer | Any approved user | Logout | Body contains refresh token |
| POST | `/api/auth/change-password/` | Bearer | Any approved user | Change password | Requires current password |
| GET | `/api/admin/registration-requests/` | Bearer | Admin/staff | Admin approval UI | Role-scoped for organization staff |
| POST | `/api/admin/users/{user_id}/approve/` | Bearer | Admin/staff | Approve account | Pharmacist approval sets `is_approved=true` |
| POST | `/api/admin/users/{user_id}/reject/` | Bearer | Admin/staff | Reject account | Rejection blocks old tokens |
| GET/PATCH | `/api/patients/me/` | Bearer | Patient | Patient profile | Use patient token |
| GET/PATCH | `/api/patients/me/settings/` | Bearer | Patient | Patient settings | Persists in DB |
| POST | `/api/admin/patients/{patient_id}/login-qr/` | Bearer | Admin/staff | Generate patient login QR | Body result has `qr_token` |
| POST | `/api/admin/patients/{patient_id}/login-qr/revoke/` | Bearer | Admin/staff | Revoke login QR | Revokes active login QR |
| POST | `/api/auth/patient/qr-login/` | No | Public | Patient login by QR | Body contains `qr_token` |
| POST | `/api/patients/me/session-qr/` | Bearer | Patient | Generate temporary session QR | One-time, expires in 300s |
| POST | `/api/pharmacist/sessions/start-by-qr/` | Bearer | Approved pharmacist | Start patient session | Body contains session QR |
| GET | `/api/pharmacist/sessions/` | Bearer | Approved pharmacist | List sessions | Optional `status` query |
| POST | `/api/pharmacist/sessions/{session_id}/end/` | Bearer | Approved pharmacist | End session | Own sessions only |
| GET/PATCH | `/api/pharmacist/me/` | Bearer | Pharmacist | Pharmacist profile | Use pharmacist token |
| GET/PATCH | `/api/pharmacist/me/pharmacy/` | Bearer | Pharmacist | Pharmacist pharmacy | Use pharmacist token |
| POST | `/api/pharmacist/prescriptions/` | Bearer | Approved pharmacist | Create prescription | Requires valid active session |
| GET | `/api/pharmacist/prescriptions/` | Bearer | Pharmacist | List pharmacist prescriptions | Own prescriptions |
| GET/PATCH | `/api/pharmacist/prescriptions/{prescription_id}/` | Bearer | Pharmacist | Retrieve/update draft | Update requires approved pharmacist |
| POST | `/api/pharmacist/prescriptions/{prescription_id}/items/` | Bearer | Approved pharmacist | Add item | Draft only |
| PATCH/DELETE | `/api/pharmacist/prescriptions/{prescription_id}/items/{item_id}/` | Bearer | Approved pharmacist | Update/delete item | Draft only |
| POST | `/api/pharmacist/prescriptions/{prescription_id}/items/{item_id}/transcribe-audio/` | Bearer | Approved pharmacist | Audio transcription | Draft only |
| POST | `/api/pharmacist/prescriptions/{prescription_id}/submit/` | Bearer | Approved pharmacist | Submit prescription | Requires at least one item |
| GET | `/api/patients/me/prescriptions/` | Bearer | Patient | Patient prescription list | Submitted by default |
| GET | `/api/patients/me/prescriptions/{prescription_id}/` | Bearer | Patient | Patient prescription detail | Own prescriptions only |
| POST | `/api/prescriptions/` | Bearer | Deprecated | Do not use | Blocked |

## Error Reference

| Situation | Response | Frontend action |
| --- | --- | --- |
| Pending account | `{"detail": "حسابك قيد مراجعة المنظمة. سيتم تفعيله بعد الموافقة.", "approval_status": "pending"}` | Show pending approval screen |
| Rejected account | `{"detail": "تم رفض طلب إنشاء الحساب. يرجى مراجعة المنظمة.", "approval_status": "rejected", "rejection_reason": "..."}` | Show rejected screen/reason |
| Inactive account | `{"detail": "User account is inactive."}` | Clear tokens and show login/support state |
| Missing/invalid auth | `{"detail": "Authentication credentials were not provided."}` | Try refresh or send to login |
| Wrong role | `{"detail": "You do not have permission to perform this action."}` | Route to correct role area |
| Invalid credentials | `{"detail": ["Invalid credentials."]}` | Show login error |
| Invalid OTP | `{"detail": ["Invalid OTP."]}` | Ask user to retry or request new OTP |
| Expired OTP | `{"detail": ["OTP has expired."]}` | Ask user to request new OTP |
| Invalid QR | `{"detail": ["Invalid QR token."]}` | Ask user to scan/generate again |
| Expired session QR | `{"detail": ["QR token has expired."]}` | Ask patient to generate a new session QR |
| Used session QR | `{"detail": ["This QR token has already been used."]}` | Ask patient to generate a new session QR |
| Revoked QR | `{"detail": ["This QR token has been revoked."]}` | Ask patient/admin to generate a valid QR |

## Important Frontend Warnings

- Registration does not return tokens.
- Patient cannot log in immediately after registration.
- Pharmacist cannot log in immediately after registration.
- Login never uses OTP.
- Store tokens only after successful approved login or approved QR login.
- `qr_token` never goes in the `Authorization` header.
- Patient Login QR and Patient Session QR are different.
- Patient Session QR is one-time use and expires after 300 seconds.
- Only approved pharmacists can start, list, and end sessions.
- Frontend must not use legacy `POST /api/prescriptions/`.
- Use `/api/pharmacist/prescriptions/` with a valid active `session_id` to create prescriptions.
- If refresh returns pending/rejected/inactive, clear local tokens immediately.
