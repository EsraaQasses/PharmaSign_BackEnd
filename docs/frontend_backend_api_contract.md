# PharmaSign Frontend Backend API Contract

## 1. Base URL

- Local development base URL:

```text
http://127.0.0.1:8000
```

- All API paths start with `/api`.

## 2. Authentication Rules

- Authorization header format:

```text
Authorization: Bearer <access_token>
```

- `patient_access_token` is used only for patient endpoints.
- `pharmacist_access_token` is used only for pharmacist endpoints.
- `qr_token` is not an auth token.
- `qr_token` must never be sent in the `Authorization` header.
- `qr_token` is sent only in the request body for QR-related endpoints.
- Authenticated endpoints return `401 Unauthorized` when the access token is missing or invalid.
- Role-restricted endpoints return `403 Forbidden` when the authenticated user has the wrong role.

## 3. Token Usage Table

| Token/value | Where it comes from | Where it is used | Notes |
| --- | --- | --- | --- |
| Patient access token | `POST /api/auth/login/`, `POST /api/auth/patient/register/`, or `POST /api/auth/patient/qr-login/` for a patient user | Patient endpoints such as `/api/patients/me/`, `/api/patients/me/settings/`, `/api/patients/me/session-qr/`, `/api/patients/me/prescriptions/` | Send as `Authorization: Bearer <access_token>`. |
| Pharmacist access token | `POST /api/auth/login/` or `POST /api/auth/pharmacist/register/` for a pharmacist user | Pharmacist endpoints such as `/api/pharmacist/me/`, `/api/pharmacist/me/pharmacy/`, `/api/pharmacist/sessions/` | Send as `Authorization: Bearer <access_token>`. Some endpoints require `profile.is_approved = true`. |
| Refresh token | Any auth endpoint that returns tokens | `POST /api/auth/refresh/`, `POST /api/auth/logout/` | Store securely. Use to obtain a new access token or blacklist on logout. |
| Patient Login QR token | Admin/organization endpoint `POST /api/admin/patients/{patient_id}/login-qr/` | `POST /api/auth/patient/qr-login/` | Used by patient to log into their account. Not used for pharmacist sessions. |
| Patient Session QR token | Patient endpoint `POST /api/patients/me/session-qr/` | `POST /api/pharmacist/sessions/start-by-qr/` | Temporary token displayed as QR in patient app, scanned by pharmacist, expires after 5 minutes, one-time use. |

## 4. Public/Auth APIs

### POST `/api/auth/login/`

Purpose: Login with phone number or email and password.

Required auth: None.

Headers:

```text
Content-Type: application/json
```

Request body examples:

```json
{
  "phone_number": "0999999999",
  "password": "StrongPass123!"
}
```

Aliases:

```json
{
  "phone": "0999999999",
  "password": "StrongPass123!"
}
```

Email login remains supported:

```json
{
  "email": "patient@example.com",
  "password": "StrongPass123!"
}
```

Success response example:

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999999999",
    "role": "patient",
    "is_active": true,
    "is_verified": false
  },
  "profile": {
    "id": 1,
    "full_name": "Patient One",
    "national_id": "",
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false
  },
  "access": "access.jwt.token",
  "refresh": "refresh.jwt.token"
}
```

Common error response examples:

```json
{
  "detail": ["Email or phone number is required."]
}
```

```json
{
  "detail": ["Invalid credentials."]
}
```

What frontend should store from response:

- Store `access` as the current role-specific access token.
- Store `refresh` securely for token refresh/logout.
- Store `user.role` to route the user to the correct app area.
- Store or cache `profile` only as needed for UI.

### POST `/api/auth/refresh/`

Purpose: Exchange refresh token for a new access token.

Required auth: None.

Headers:

```text
Content-Type: application/json
```

Request body example:

```json
{
  "refresh": "refresh.jwt.token"
}
```

Success response example:

```json
{
  "access": "new.access.jwt.token"
}
```

Common error response example:

```json
{
  "detail": "Token is invalid or expired",
  "code": "token_not_valid"
}
```

What frontend should store from response:

- Replace the old access token with `access`.

### GET `/api/auth/me/`

Purpose: Get the current authenticated user and role profile.

Required auth: Access token required.

Headers:

```text
Authorization: Bearer <access_token>
```

Request body: None.

Success response example for patient:

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999999999",
    "role": "patient",
    "is_active": true,
    "is_verified": false
  },
  "profile": {
    "id": 1,
    "full_name": "Patient One",
    "national_id": "",
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false
  }
}
```

Success response example for pharmacist:

```json
{
  "user": {
    "id": 2,
    "email": "pharmacist@example.com",
    "phone_number": "0988888888",
    "role": "pharmacist",
    "is_active": true,
    "is_verified": false
  },
  "profile": {
    "id": 1,
    "full_name": "Pharmacist One",
    "license_number": "LIC-123",
    "is_approved": true,
    "pharmacy": {
      "id": 1,
      "name": "PharmaSign Pharmacy",
      "address": "Damascus",
      "phone": "011111111",
      "lat": null,
      "lng": null,
      "has_sign_service": true
    }
  }
}
```

Common error response example:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

What frontend should store from response:

- Store or refresh local `user` and `profile` state.

### POST `/api/auth/logout/`

Purpose: Blacklist a refresh token.

Required auth: Access token required.

Headers:

```text
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request body example:

```json
{
  "refresh": "refresh.jwt.token"
}
```

Success response example:

```json
{
  "detail": "Logged out successfully."
}
```

Common error response example:

```json
{
  "refresh": ["Token is invalid or expired"]
}
```

What frontend should store from response:

- Store nothing. Clear local access/refresh tokens after successful logout.

### POST `/api/auth/change-password/`

Purpose: Change password for the authenticated user.

Required auth: Access token required.

Headers:

```text
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request body example:

```json
{
  "current_password": "OldPass123!",
  "new_password": "NewPass123!",
  "confirm_password": "NewPass123!"
}
```

Success response example:

```json
{
  "detail": "Password changed successfully."
}
```

Common error response examples:

```json
{
  "current_password": ["Current password is incorrect."]
}
```

```json
{
  "confirm_password": ["New password and confirmation do not match."]
}
```

What frontend should store from response:

- Store nothing. The user may be prompted to log in again depending on app policy.

### POST `/api/auth/patient/register/request-otp/`

Purpose: Request a development-only OTP for patient registration phone verification.

Required auth: None.

Headers:

```text
Content-Type: application/json
```

Request body example:

```json
{
  "phone_number": "0999999999"
}
```

Alias:

```json
{
  "phone": "0999999999"
}
```

Success response example when `DEBUG=True`:

```json
{
  "detail": "Registration OTP generated successfully.",
  "expires_in_seconds": 300,
  "debug_otp": "123456"
}
```

Success response example when `DEBUG=False`:

```json
{
  "detail": "Registration OTP generated successfully.",
  "expires_in_seconds": 300
}
```

Common error response examples:

```json
{
  "detail": ["Phone number is required."]
}
```

```json
{
  "detail": ["Phone number is already registered."]
}
```

What frontend should store from response:

- Store nothing long-term.
- In development only, `debug_otp` can be shown or used for testing.

### POST `/api/auth/patient/register/`

Purpose: Self-register a patient account using phone number, password, and OTP.

Required auth: None.

Headers:

```text
Content-Type: application/json
```

Request body example:

```json
{
  "full_name": "Patient One",
  "phone_number": "0999999999",
  "password": "StrongPass123!",
  "otp": "123456"
}
```

Aliases:

```json
{
  "name": "Patient One",
  "phone": "0999999999",
  "password": "StrongPass123!",
  "otp": "123456"
}
```

Optional email:

```json
{
  "full_name": "Patient One",
  "phone_number": "0999999999",
  "email": "patient@example.com",
  "password": "StrongPass123!",
  "confirm_password": "StrongPass123!",
  "otp": "123456"
}
```

Additional accepted patient fields:

- `birth_date`
- `gender`
- `address`
- `hearing_disability_level`
- `record_access_pin`
- `national_id` is accepted but not persisted in the current profile response.

Success response example:

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999999999",
    "role": "patient",
    "is_active": true,
    "is_verified": false
  },
  "profile": {
    "id": 1,
    "full_name": "Patient One",
    "national_id": "",
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false
  },
  "access": "access.jwt.token",
  "refresh": "refresh.jwt.token"
}
```

Common error response examples:

```json
{
  "otp": ["This field is required."]
}
```

```json
{
  "detail": ["Invalid OTP."]
}
```

```json
{
  "detail": ["OTP has expired."]
}
```

```json
{
  "phone_number": ["A user with this phone number already exists."]
}
```

What frontend should store from response:

- Store `access` as `patient_access_token`.
- Store `refresh` securely.
- Store `user` and `profile` for UI state.

### POST `/api/auth/pharmacist/register/`

Purpose: Register a pharmacist account and associated pharmacy.

Required auth: None.

Headers:

```text
Content-Type: application/json
```

Request body example:

```json
{
  "full_name": "Pharmacist One",
  "phone_number": "0988888888",
  "email": "pharmacist@example.com",
  "password": "StrongPass123!",
  "license_number": "LIC-123",
  "pharmacy_name": "PharmaSign Pharmacy",
  "pharmacy_address": "Damascus"
}
```

Aliases:

- `name` for `full_name`
- `phone` for `phone_number`
- `license_id` for `license_number`

Optional fields:

- `confirm_password`
- `pharmacy_phone_number`
- `latitude`
- `longitude`

Success response example:

```json
{
  "user": {
    "id": 2,
    "email": "pharmacist@example.com",
    "phone_number": "0988888888",
    "role": "pharmacist",
    "is_active": true,
    "is_verified": false
  },
  "profile": {
    "id": 1,
    "full_name": "Pharmacist One",
    "license_number": "LIC-123",
    "is_approved": false,
    "pharmacy": {
      "id": 1,
      "name": "PharmaSign Pharmacy",
      "address": "Damascus",
      "phone": "",
      "lat": null,
      "lng": null,
      "has_sign_service": true
    }
  },
  "access": "access.jwt.token",
  "refresh": "refresh.jwt.token"
}
```

Common error response examples:

```json
{
  "email": ["A user with this email already exists."]
}
```

```json
{
  "license_number": ["This field is required."]
}
```

What frontend should store from response:

- Store `access` as `pharmacist_access_token`.
- Store `refresh` securely.
- Store `profile.is_approved` to control pharmacist workflow access.

### POST `/api/auth/patient/qr-login/`

Purpose: Patient login using Patient Login QR.

Required auth: None.

Headers:

```text
Content-Type: application/json
```

Request body example:

```json
{
  "qr_token": "opaque-patient-login-qr-token"
}
```

Legacy fallback also exists:

```json
{
  "qr_code_value": "legacy-static-qr-value",
  "pin": "1234"
}
```

Success response example:

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999999999",
    "role": "patient",
    "is_active": true,
    "is_verified": false
  },
  "profile": {
    "id": 1,
    "full_name": "Patient One",
    "national_id": "",
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false
  },
  "access": "access.jwt.token",
  "refresh": "refresh.jwt.token"
}
```

Common error response examples:

```json
{
  "detail": ["QR token is required."]
}
```

```json
{
  "detail": ["Invalid QR token."]
}
```

```json
{
  "detail": ["QR token has been revoked."]
}
```

What frontend should store from response:

- Store `access` as `patient_access_token`.
- Store `refresh` securely.
- Do not store the QR token as an access token.

## 5. Patient APIs

### GET `/api/patients/me/`

Purpose: Get current patient's editable profile view.

Required role: `patient`.

Required token: `patient_access_token`.

Headers:

```text
Authorization: Bearer <patient_access_token>
```

Success response example:

```json
{
  "id": 1,
  "full_name": "Patient One",
  "phone": "0999999999",
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

Error response examples:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

```json
{
  "detail": "You do not have permission to perform this action."
}
```

Frontend notes:

- Use only patient access token.
- `national_id` and `blood_type` currently return empty strings in this endpoint.

### PATCH `/api/patients/me/`

Purpose: Update current patient's safe editable profile fields.

Required role: `patient`.

Required token: `patient_access_token`.

Headers:

```text
Authorization: Bearer <patient_access_token>
Content-Type: application/json
```

Body example:

```json
{
  "full_name": "Patient One Updated",
  "phone": "0999999999",
  "allergies": "Penicillin",
  "chronic_conditions": "Asthma",
  "regular_medications": "Vitamin D",
  "is_pregnant": false,
  "date_of_birth": "1999-01-01",
  "gender": "F"
}
```

Success response example:

```json
{
  "id": 1,
  "full_name": "Patient One Updated",
  "phone": "0999999999",
  "national_id": "",
  "blood_type": "",
  "allergies": "Penicillin",
  "chronic_conditions": "Asthma",
  "regular_medications": "Vitamin D",
  "is_pregnant": false,
  "date_of_birth": "1999-01-01",
  "gender": "F"
}
```

Error response examples:

```json
{
  "gender": ["\"X\" is not a valid choice."]
}
```

Frontend notes:

- Do not send `id`, `user`, `role`, `password`, `qr_code_value`, or PIN/hash fields.

### GET `/api/patients/me/settings/`

Purpose: Get persisted patient settings.

Required role: `patient`.

Required token: `patient_access_token`.

Headers:

```text
Authorization: Bearer <patient_access_token>
```

Success response example:

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

Error response examples:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Frontend notes:

- Settings are persisted in the database.

### PATCH `/api/patients/me/settings/`

Purpose: Update persisted patient settings.

Required role: `patient`.

Required token: `patient_access_token`.

Headers:

```text
Authorization: Bearer <patient_access_token>
Content-Type: application/json
```

Body example:

```json
{
  "notifications_enabled": false,
  "prescription_reminders": true,
  "dark_mode": true,
  "use_biometrics": false
}
```

Success response example:

```json
{
  "notifications_enabled": false,
  "prescription_reminders": true,
  "dark_mode": true,
  "use_biometrics": false,
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:05:00Z"
}
```

Error response examples:

```json
{
  "dark_mode": ["Must be a valid boolean."]
}
```

Frontend notes:

- Send only settings fields that need to change.

### POST `/api/patients/me/session-qr/`

Purpose: Generate a temporary Patient Session QR for pharmacist scanning.

Required role: `patient`.

Required token: `patient_access_token`.

Headers:

```text
Authorization: Bearer <patient_access_token>
Content-Type: application/json
```

Body example:

```json
{}
```

Success response example:

```json
{
  "qr_token": "opaque-temporary-session-token",
  "qr_payload": "opaque-temporary-session-token",
  "expires_at": "2026-05-01T10:05:00Z",
  "expires_in_seconds": 300
}
```

Error response examples:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

```json
{
  "detail": "You do not have permission to perform this action."
}
```

Frontend notes:

- Display `qr_payload` as QR image content.
- Do not send this token in the `Authorization` header.
- Do not store it long-term.
- It expires after 5 minutes.
- It is one-time use.
- Generating a new session QR revokes previous active unused session QR tokens for the same patient.

### GET `/api/patients/me/prescriptions/`

Purpose: List prescriptions for the current patient.

Required role: `patient`.

Required token: `patient_access_token`.

Headers:

```text
Authorization: Bearer <patient_access_token>
```

Success response example:

```json
[
  {
    "id": 1,
    "patient": {
      "id": 1,
      "full_name": "Patient One"
    },
    "pharmacist": {
      "id": 1,
      "full_name": "Pharmacist One"
    },
    "pharmacy": {
      "id": 1,
      "name": "PharmaSign Pharmacy"
    },
    "doctor_name": "Doctor One",
    "doctor_specialty": "",
    "status": "draft",
    "prescribed_at": "2026-05-01T10:00:00Z",
    "delivered_at": null,
    "notes": "",
    "reused_from": null,
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:00:00Z",
    "items": []
  }
]
```

Error response examples:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Frontend notes:

- This endpoint is implemented.
- Response uses the prescription serializer, including nested patient/pharmacist/pharmacy/items.

### GET `/api/patients/me/prescriptions/{id}/`

Purpose: Retrieve one prescription for the current patient.

Required role: `patient`.

Required token: `patient_access_token`.

Headers:

```text
Authorization: Bearer <patient_access_token>
```

Success response example:

```json
{
  "id": 1,
  "patient": {
    "id": 1,
    "full_name": "Patient One"
  },
  "pharmacist": {
    "id": 1,
    "full_name": "Pharmacist One"
  },
  "pharmacy": {
    "id": 1,
    "name": "PharmaSign Pharmacy"
  },
  "doctor_name": "Doctor One",
  "doctor_specialty": "",
  "status": "draft",
  "prescribed_at": "2026-05-01T10:00:00Z",
  "delivered_at": null,
  "notes": "",
  "reused_from": null,
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:00:00Z",
  "items": []
}
```

Error response examples:

```json
{
  "detail": "Not found."
}
```

Frontend notes:

- A patient can only retrieve prescriptions belonging to their own patient profile.

## 6. Pharmacist APIs

### GET `/api/pharmacist/me/`

Purpose: Get current pharmacist profile.

Required role: `pharmacist`.

Required token: `pharmacist_access_token`.

Headers:

```text
Authorization: Bearer <pharmacist_access_token>
```

Success response example:

```json
{
  "id": 1,
  "email": "pharmacist@example.com",
  "phone_number": "0988888888",
  "pharmacy": {
    "id": 1,
    "name": "PharmaSign Pharmacy",
    "owner_user": 2,
    "address": "Damascus",
    "latitude": null,
    "longitude": null,
    "is_contracted_with_organization": false,
    "organization": null,
    "phone_number": "",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:00:00Z"
  },
  "full_name": "Pharmacist One",
  "license_number": "LIC-123",
  "is_approved": true,
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:00:00Z"
}
```

Error response examples:

```json
{
  "detail": "You do not have permission to perform this action."
}
```

Frontend notes:

- Use `is_approved` to decide whether pharmacist can start patient sessions.
- Backward-compatible alias also exists: `GET /api/pharmacists/me/`.

### PATCH `/api/pharmacist/me/`

Purpose: Update current pharmacist profile and selected pharmacy fields.

Required role: `pharmacist`.

Required token: `pharmacist_access_token`.

Headers:

```text
Authorization: Bearer <pharmacist_access_token>
Content-Type: application/json
```

Body example:

```json
{
  "full_name": "Pharmacist One Updated",
  "phone_number": "0988888888",
  "license_number": "LIC-123",
  "pharmacy_name": "Updated Pharmacy",
  "pharmacy_address": "Damascus",
  "pharmacy_phone_number": "011111111",
  "latitude": "33.513800",
  "longitude": "36.276500"
}
```

Success response example:

```json
{
  "id": 1,
  "email": "pharmacist@example.com",
  "phone_number": "0988888888",
  "pharmacy": {
    "id": 1,
    "name": "Updated Pharmacy",
    "owner_user": 2,
    "address": "Damascus",
    "latitude": "33.513800",
    "longitude": "36.276500",
    "is_contracted_with_organization": false,
    "organization": null,
    "phone_number": "011111111",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:05:00Z"
  },
  "full_name": "Pharmacist One Updated",
  "license_number": "LIC-123",
  "is_approved": true,
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:05:00Z"
}
```

Error response examples:

```json
{
  "latitude": ["A valid number is required."]
}
```

Frontend notes:

- Do not send approval fields such as `is_approved`.
- Backward-compatible alias also exists: `PATCH /api/pharmacists/me/`.

### GET `/api/pharmacist/me/pharmacy/`

Purpose: Get current pharmacist pharmacy in frontend-compatible shape.

Required role: `pharmacist`.

Required token: `pharmacist_access_token`.

Headers:

```text
Authorization: Bearer <pharmacist_access_token>
```

Success response example:

```json
{
  "id": 1,
  "name": "PharmaSign Pharmacy",
  "address": "Damascus",
  "phone": "011111111",
  "lat": null,
  "lng": null,
  "has_sign_service": true
}
```

Error response examples:

```json
{
  "detail": "You do not have permission to perform this action."
}
```

Frontend notes:

- This endpoint returns `phone`, `lat`, and `lng` aliases.

### PATCH `/api/pharmacist/me/pharmacy/`

Purpose: Update safe editable fields for current pharmacist pharmacy.

Required role: `pharmacist`.

Required token: `pharmacist_access_token`.

Headers:

```text
Authorization: Bearer <pharmacist_access_token>
Content-Type: application/json
```

Body example:

```json
{
  "name": "Updated Pharmacy",
  "address": "Damascus",
  "phone": "011111111",
  "lat": "33.513800",
  "lng": "36.276500",
  "has_sign_service": true
}
```

Success response example:

```json
{
  "id": 1,
  "name": "Updated Pharmacy",
  "address": "Damascus",
  "phone": "011111111",
  "lat": "33.513800",
  "lng": "36.276500",
  "has_sign_service": true
}
```

Error response examples:

```json
{
  "lat": ["A valid number is required."]
}
```

Frontend notes:

- `has_sign_service` is accepted by the serializer but currently always represents as `true`.

### POST `/api/pharmacist/sessions/start-by-qr/`

Purpose: Start a temporary pharmacist-patient session by scanning Patient Session QR.

Required role: approved `pharmacist`.

Required token: `pharmacist_access_token`.

Headers:

```text
Authorization: Bearer <pharmacist_access_token>
Content-Type: application/json
```

Body example:

```json
{
  "qr_token": "opaque-temporary-session-token"
}
```

Alias:

```json
{
  "qr_payload": "opaque-temporary-session-token"
}
```

Success response example:

```json
{
  "session": {
    "id": 12,
    "status": "active",
    "created_at": "2026-05-01T10:00:00Z",
    "expires_at": "2026-05-01T10:30:00Z"
  },
  "patient": {
    "id": 5,
    "full_name": "Patient One",
    "phone_number": "0999999999",
    "blood_type": "",
    "allergies": "Penicillin",
    "chronic_conditions": "Asthma",
    "regular_medications": "Vitamin D"
  },
  "pharmacist": {
    "id": 2,
    "full_name": "Pharmacist One"
  },
  "pharmacy": {
    "id": 1,
    "name": "PharmaSign Pharmacy"
  }
}
```

Error response examples:

```json
{
  "qr_token": ["This field is required."]
}
```

```json
{
  "detail": ["Invalid QR token."]
}
```

```json
{
  "detail": ["QR token has expired."]
}
```

```json
{
  "detail": ["This QR token has already been used."]
}
```

```json
{
  "detail": ["This QR token has been revoked."]
}
```

```json
{
  "detail": "Pharmacist account is not approved."
}
```

Frontend notes:

- Pharmacist scans Patient Session QR displayed by patient.
- Send scanned QR string as `qr_token` or `qr_payload`.
- Do not send scanned QR string as an auth token.
- If an active unexpired session already exists for the same patient/pharmacist, backend returns the existing active session.

### GET `/api/pharmacist/sessions/`

Purpose: List sessions belonging to the authenticated pharmacist.

Required role: `pharmacist`.

Required token: `pharmacist_access_token`.

Headers:

```text
Authorization: Bearer <pharmacist_access_token>
```

Success response example:

```json
[
  {
    "id": 12,
    "status": "active",
    "started_at": "2026-05-01T10:00:00Z",
    "ended_at": null,
    "expires_at": "2026-05-01T10:30:00Z",
    "created_at": "2026-05-01T10:00:00Z",
    "patient": {
      "id": 5,
      "full_name": "Patient One",
      "phone_number": "0999999999",
      "blood_type": "",
      "allergies": "Penicillin",
      "chronic_conditions": "Asthma",
      "regular_medications": "Vitamin D"
    },
    "pharmacist": {
      "id": 2,
      "full_name": "Pharmacist One"
    },
    "pharmacy": {
      "id": 1,
      "name": "PharmaSign Pharmacy"
    }
  }
]
```

Error response examples:

```json
{
  "detail": "You do not have permission to perform this action."
}
```

Frontend notes:

- Returns only sessions owned by the authenticated pharmacist.

### GET `/api/pharmacist/sessions/?status=active`

Purpose: List authenticated pharmacist sessions filtered by status.

Required role: `pharmacist`.

Required token: `pharmacist_access_token`.

Headers:

```text
Authorization: Bearer <pharmacist_access_token>
```

Success response example:

```json
[
  {
    "id": 12,
    "status": "active",
    "started_at": "2026-05-01T10:00:00Z",
    "ended_at": null,
    "expires_at": "2026-05-01T10:30:00Z",
    "created_at": "2026-05-01T10:00:00Z",
    "patient": {
      "id": 5,
      "full_name": "Patient One",
      "phone_number": "0999999999",
      "blood_type": "",
      "allergies": "Penicillin",
      "chronic_conditions": "Asthma",
      "regular_medications": "Vitamin D"
    },
    "pharmacist": {
      "id": 2,
      "full_name": "Pharmacist One"
    },
    "pharmacy": {
      "id": 1,
      "name": "PharmaSign Pharmacy"
    }
  }
]
```

Error response examples:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Frontend notes:

- Supported statuses are `active`, `completed`, `cancelled`, and `expired`.

### POST `/api/pharmacist/sessions/{session_id}/end/`

Purpose: End a pharmacist-owned patient session.

Required role: `pharmacist`.

Required token: `pharmacist_access_token`.

Headers:

```text
Authorization: Bearer <pharmacist_access_token>
Content-Type: application/json
```

Body example:

```json
{}
```

Success response example:

```json
{
  "detail": "Session ended successfully."
}
```

Error response examples:

```json
{
  "detail": "Not found."
}
```

Frontend notes:

- A pharmacist cannot end another pharmacist's session.
- Backend sets session status to `completed`.

## 7. Admin / Organization APIs

### POST `/api/admin/patients/create-account/`

Purpose: Admin/organization creates a patient account without OTP.

Required role: admin or organization staff with patient-management permission.

Required token: admin/organization access token.

Headers:

```text
Authorization: Bearer <access_token>
Content-Type: application/json
```

Body example:

```json
{
  "full_name": "Patient Created By Organization",
  "phone_number": "0999111222",
  "password": "OptionalStrongPass123!",
  "national_id": "optional",
  "date_of_birth": "1999-01-01",
  "gender": "F",
  "blood_type": "A+",
  "allergies": "Penicillin",
  "chronic_conditions": "Asthma",
  "regular_medications": "Vitamin D",
  "notes": "optional"
}
```

Success response example:

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999111222",
    "role": "patient",
    "is_active": true,
    "is_verified": true
  },
  "profile": {
    "id": 1,
    "full_name": "Patient Created By Organization",
    "national_id": "optional",
    "blood_type": "A+",
    "allergies": "Penicillin",
    "chronic_conditions": "Asthma",
    "regular_medications": "Vitamin D",
    "is_pregnant": false
  },
  "temporary_password_generated": false
}
```

If `password` is omitted, response includes one-time `temporary_password`:

```json
{
  "temporary_password_generated": true,
  "temporary_password": "generated-password"
}
```

Notes:

- Normal patients and pharmacists cannot call this endpoint.
- OTP is not required for admin/organization-created patient accounts.
- If a temporary password is returned, it should be delivered securely.

### POST `/api/admin/patients/{patient_id}/login-qr/`

Purpose: Generate or rotate Patient Login QR for a patient account.

Required role: admin or organization staff with patient-management permission.

Required token: admin/organization access token.

Headers:

```text
Authorization: Bearer <access_token>
Content-Type: application/json
```

Body example:

```json
{}
```

Success response example:

```json
{
  "patient_id": 1,
  "qr_token": "opaque-patient-login-token",
  "qr_payload": "opaque-patient-login-token",
  "is_active": true,
  "created_at": "2026-05-01T10:00:00Z",
  "revoked_at": null
}
```

Notes:

- This token is for Patient Login QR only.
- This token is not used to open pharmacist sessions.
- Backend stores only a token hash.

### POST `/api/admin/patients/{patient_id}/login-qr/revoke/`

Purpose: Revoke active Patient Login QR tokens for a patient account.

Required role: admin or organization staff with patient-management permission.

Required token: admin/organization access token.

Headers:

```text
Authorization: Bearer <access_token>
Content-Type: application/json
```

Body example:

```json
{}
```

Success response example:

```json
{
  "patient_id": 1,
  "is_active": false
}
```

Notes:

- After revocation, QR login with that token should fail.

## 8. QR Flow Explanation

### Patient Login QR

- Endpoint: `POST /api/auth/patient/qr-login/`
- Used by patient to log into their account.
- Token source: admin/organization generated Patient Login QR.
- Admin/organization generates it with `POST /api/admin/patients/{patient_id}/login-qr/`.
- This is NOT used to open pharmacist sessions.
- This QR token is sent in the request body as `qr_token`.
- This QR token is not sent in the `Authorization` header.

### Patient Session QR

- Endpoint to generate QR: `POST /api/patients/me/session-qr/`
- Generated by logged-in patient using patient access token.
- Displayed on patient app screen as QR image using `qr_payload`.
- Pharmacist scans this QR.
- Pharmacist sends scanned value to:
  `POST /api/pharmacist/sessions/start-by-qr/`
- Pharmacist uses pharmacist access token.
- Pharmacist does not have a QR code in Phase 2.
- This QR expires after 5 minutes and is one-time use.
- This QR token is sent in the request body as `qr_token` or `qr_payload`.
- This QR token is not sent in the `Authorization` header.

## 9. Correct Frontend Flows

### Patient registration flow

1. Patient enters phone number.
2. Frontend calls `POST /api/auth/patient/register/request-otp/`.
3. During development, frontend may read `debug_otp` when `DEBUG=True`.
4. Patient submits name, phone number, password, and OTP.
5. Frontend calls `POST /api/auth/patient/register/`.
6. Backend returns `user`, `profile`, `access`, and `refresh`.
7. Frontend stores `access` as patient access token and stores `refresh` securely.

### Patient login flow

1. Patient enters phone number or email and password.
2. Frontend calls `POST /api/auth/login/`.
3. Backend returns normalized auth response.
4. Frontend checks `user.role === "patient"`.
5. Frontend stores access/refresh tokens securely.

### Patient show QR for pharmacist flow

1. Patient logs in.
2. Patient calls `POST /api/patients/me/session-qr/` with patient access token.
3. Frontend converts `qr_payload` to QR image.
4. Patient shows QR screen.
5. QR expires after 5 minutes.

### Pharmacist scan patient QR flow

1. Pharmacist logs in.
2. Ensure user role is `pharmacist`.
3. Ensure `is_approved` is `true` if available in profile.
4. Pharmacist scans patient QR.
5. Frontend sends scanned value to `POST /api/pharmacist/sessions/start-by-qr/`.
6. Store/use `session.id` for prescription workflow.
7. Navigate with returned patient summary.

### Pharmacist session management flow

1. Pharmacist logs in.
2. Frontend calls `GET /api/pharmacist/sessions/` to list sessions.
3. Frontend may call `GET /api/pharmacist/sessions/?status=active` to show only active sessions.
4. Pharmacist opens a session detail in the UI using returned session and patient summary.
5. Pharmacist ends a session with `POST /api/pharmacist/sessions/{session_id}/end/`.
6. Backend returns `{"detail": "Session ended successfully."}`.

## 10. Error Reference

| Situation | Example response | Frontend action |
| --- | --- | --- |
| 400 missing field | `{"phone_number": ["This field is required."]}` | Highlight the missing field and ask user to complete it. |
| 401 missing/invalid token | `{"detail": "Authentication credentials were not provided."}` | Send user to login or refresh token if possible. |
| 403 wrong role | `{"detail": "You do not have permission to perform this action."}` | Stop the action and route user to correct role area. |
| 403 pharmacist not approved | `{"detail": "Pharmacist account is not approved."}` | Show approval-pending state; do not allow session/prescription workflow. |
| Invalid QR | `{"detail": ["Invalid QR token."]}` | Ask user to scan/generate a valid QR again. |
| Expired QR | `{"detail": ["QR token has expired."]}` | Ask patient to generate a new Patient Session QR. |
| Already used QR | `{"detail": ["This QR token has already been used."]}` | Ask patient to generate a new Patient Session QR. |
| Revoked QR | `{"detail": ["This QR token has been revoked."]}` | Ask patient/admin to generate a valid QR again. |
| Invalid credentials | `{"detail": ["Invalid credentials."]}` | Show login error without revealing which field is wrong. |
| Invalid OTP | `{"detail": ["Invalid OTP."]}` | Ask user to retry OTP or request a new OTP. |

## 11. Response Shape Reference

### Login response

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999999999",
    "role": "patient",
    "is_active": true,
    "is_verified": false
  },
  "profile": {
    "id": 1,
    "full_name": "Patient One",
    "national_id": "",
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false
  },
  "access": "access.jwt.token",
  "refresh": "refresh.jwt.token"
}
```

### Current user response

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999999999",
    "role": "patient",
    "is_active": true,
    "is_verified": false
  },
  "profile": {
    "id": 1,
    "full_name": "Patient One",
    "national_id": "",
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "regular_medications": "",
    "is_pregnant": false
  }
}
```

### Patient profile

```json
{
  "id": 1,
  "full_name": "Patient One",
  "phone": "0999999999",
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

### Pharmacist profile

```json
{
  "id": 1,
  "email": "pharmacist@example.com",
  "phone_number": "0988888888",
  "pharmacy": {
    "id": 1,
    "name": "PharmaSign Pharmacy",
    "owner_user": 2,
    "address": "Damascus",
    "latitude": null,
    "longitude": null,
    "is_contracted_with_organization": false,
    "organization": null,
    "phone_number": "",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:00:00Z"
  },
  "full_name": "Pharmacist One",
  "license_number": "LIC-123",
  "is_approved": true,
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:00:00Z"
}
```

### Session QR response

```json
{
  "qr_token": "opaque-temporary-session-token",
  "qr_payload": "opaque-temporary-session-token",
  "expires_at": "2026-05-01T10:05:00Z",
  "expires_in_seconds": 300
}
```

### Start session by QR response

```json
{
  "session": {
    "id": 12,
    "status": "active",
    "created_at": "2026-05-01T10:00:00Z",
    "expires_at": "2026-05-01T10:30:00Z"
  },
  "patient": {
    "id": 5,
    "full_name": "Patient One",
    "phone_number": "0999999999",
    "blood_type": "",
    "allergies": "Penicillin",
    "chronic_conditions": "Asthma",
    "regular_medications": "Vitamin D"
  },
  "pharmacist": {
    "id": 2,
    "full_name": "Pharmacist One"
  },
  "pharmacy": {
    "id": 1,
    "name": "PharmaSign Pharmacy"
  }
}
```

### Pharmacist session list item

```json
{
  "id": 12,
  "status": "active",
  "started_at": "2026-05-01T10:00:00Z",
  "ended_at": null,
  "expires_at": "2026-05-01T10:30:00Z",
  "created_at": "2026-05-01T10:00:00Z",
  "patient": {
    "id": 5,
    "full_name": "Patient One",
    "phone_number": "0999999999",
    "blood_type": "",
    "allergies": "Penicillin",
    "chronic_conditions": "Asthma",
    "regular_medications": "Vitamin D"
  },
  "pharmacist": {
    "id": 2,
    "full_name": "Pharmacist One"
  },
  "pharmacy": {
    "id": 1,
    "name": "PharmaSign Pharmacy"
  }
}
```

### End session response

```json
{
  "detail": "Session ended successfully."
}
```

### API error response

```json
{
  "detail": ["Invalid QR token."]
}
```

Field validation errors can use field keys:

```json
{
  "phone_number": ["This field is required."]
}
```

## 12. Important Warnings for Frontend

- Pharmacist has no QR code in Phase 2.
- Patient Session QR appears only on the patient app.
- Pharmacist scans patient QR and sends the scanned value to backend.
- Patient Login QR and Patient Session QR are different.
- `qr_token` is not an access token.
- Do not store Patient Session QR long-term.
- Same Patient Session QR cannot be reused.
- Patient Session QR expires after 5 minutes.
- Use patient access token only for patient endpoints.
- Use pharmacist access token only for pharmacist endpoints.
