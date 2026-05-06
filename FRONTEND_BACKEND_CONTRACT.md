# Frontend Backend Contract - Phase 1 Prescriptions

Base URL prefix: `/api/`

Authentication: protected endpoints in this document require a Bearer JWT access token. Auth login, registration, OTP request, token refresh, and patient QR login endpoints are public unless noted otherwise.

## Shared Prescription Shape

```json
{
  "id": 10,
  "patient": {
    "id": 3,
    "full_name": "Patient Name",
    "phone_number": "+963900000000"
  },
  "pharmacist": {
    "id": 2,
    "full_name": "Pharmacist Name"
  },
  "pharmacy": {
    "id": 1,
    "name": "Main Pharmacy",
    "address": "Street address",
    "phone_number": "+963900000001"
  },
  "session": 7,
  "session_id": 7,
  "doctor_name": "Doctor Name",
  "doctor_specialty": "Internal Medicine",
  "diagnosis": "Diagnosis text",
  "status": "draft",
  "prescribed_at": "2026-05-05T12:00:00Z",
  "submitted_at": null,
  "delivered_at": null,
  "notes": "",
  "items": [],
  "created_at": "2026-05-05T12:00:00Z",
  "updated_at": "2026-05-05T12:00:00Z"
}
```

## Shared Item Shape

```json
{
  "id": 25,
  "medication_name": "Amoxicillin",
  "dosage": "500mg",
  "frequency": "Twice daily",
  "duration": "7 days",
  "instructions": "Take after food",
  "quantity": null,
  "price": "0.00",
  "image_url": null,
  "audio_url": null,
  "video_url": null,
  "transcription_status": "not_requested",
  "raw_transcript": null,
  "approved_instruction_text": null,
  "gloss_text": "",
  "supporting_text": "",
  "sign_status": "pending",
  "is_confirmed": false,
  "created_at": "2026-05-05T12:00:00Z",
  "updated_at": "2026-05-05T12:00:00Z"
}
```

Frontend notes:

- Response fields use frontend names: `medication_name`, `instructions`, `raw_transcript`, `approved_instruction_text`, `gloss_text`.
- Existing backend request names remain accepted where possible: `medicine_name` and `instructions_text`.
- `video_url` is `null` in Phase 1. Video generation is not supported in this phase.
- `gloss_text` and `supporting_text` currently contain the same generated gloss text.
- `doctor_specialty` is optional and blank string is allowed.
- Frontend should load doctor specialty dropdown options from `GET /api/pharmacist/prescriptions/doctor-specialties/`.
- Frontend displays each specialty `label` and sends the selected `value` as `doctor_specialty`.
- If the user selects `أخرى`, frontend may send the custom typed specialty string as `doctor_specialty`.
- Backend does not reject custom free-text `doctor_specialty` values in Phase 1.

## GET `/api/pharmacist/prescriptions/doctor-specialties/`

Auth/role: pharmacist.

Request body: none.

Success response:

```json
{
  "results": [
    {
      "value": "طبيب عام",
      "label": "طبيب عام"
    },
    {
      "value": "قلبية",
      "label": "قلبية"
    },
    {
      "value": "عصبية",
      "label": "عصبية"
    },
    {
      "value": "أطفال",
      "label": "أطفال"
    },
    {
      "value": "نسائية",
      "label": "نسائية"
    },
    {
      "value": "عظمية",
      "label": "عظمية"
    },
    {
      "value": "باطنية",
      "label": "باطنية"
    },
    {
      "value": "أسنان",
      "label": "أسنان"
    },
    {
      "value": "أخرى",
      "label": "أخرى"
    }
  ]
}
```

Error response example:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Frontend notes: use this endpoint as the stable Phase 1 dropdown source. Values are suggestions only; `doctor_specialty` remains flexible free text.

## POST `/api/pharmacist/prescriptions/`

Auth/role: approved pharmacist.

Request body:

```json
{
  "session_id": 7,
  "patient_id": 3,
  "doctor_name": "Doctor Name",
  "doctor_specialty": "Internal Medicine",
  "diagnosis": "Diagnosis text",
  "notes": "",
  "items": [
    {
      "medication_name": "Amoxicillin",
      "dosage": "500mg",
      "frequency": "Twice daily",
      "duration": "7 days",
      "instructions": "Take after food"
    }
  ]
}
```

Success response: `201 Created`, shared prescription shape.

Error response example:

```json
{
  "detail": "A valid active patient session is required to create a prescription."
}
```

Frontend notes: prescription starts as `draft`. A valid active pharmacist-patient session is required.
`doctor_specialty` may be a predefined value from the doctor specialties endpoint, blank, omitted, or custom free text.

## GET `/api/pharmacist/prescriptions/`

Auth/role: pharmacist.

Request body: none.

Query params:

- `status`: optional prescription status filter.
- `patient_id`: optional patient filter.

Success response:

```json
[
  {
    "id": 10,
    "patient": {
      "id": 3,
      "full_name": "Patient Name",
      "phone_number": "+963900000000"
    },
    "pharmacist": {
      "id": 2,
      "full_name": "Pharmacist Name"
    },
    "pharmacy": {
      "id": 1,
      "name": "Main Pharmacy",
      "address": "Street address",
      "phone_number": "+963900000001"
    },
    "session": 7,
    "session_id": 7,
    "doctor_name": "Doctor Name",
    "doctor_specialty": "Internal Medicine",
    "diagnosis": "Diagnosis text",
    "status": "draft",
    "prescribed_at": "2026-05-05T12:00:00Z",
    "submitted_at": null,
    "delivered_at": null,
    "notes": "",
    "items": [],
    "created_at": "2026-05-05T12:00:00Z",
    "updated_at": "2026-05-05T12:00:00Z"
  }
]
```

Error response example:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Frontend notes: list is currently returned as an array, not a paginated DRF envelope.
Each list item also includes `item_count` for backward compatibility with existing backend consumers.
Prescription responses include both `session` and `session_id`; frontend should prefer `session_id`.

## GET `/api/pharmacist/prescriptions/<id>/`

Auth/role: pharmacist who owns the prescription.

Request body: none.

Success response: shared prescription shape.

Error response example:

```json
{
  "detail": "Not found."
}
```

Frontend notes: this endpoint logs prescription view access.

## PATCH `/api/pharmacist/prescriptions/<id>/`

Auth/role: approved pharmacist who owns the prescription.

Request body:

```json
{
  "doctor_name": "Updated Doctor",
  "doctor_specialty": "Cardiology",
  "diagnosis": "Updated diagnosis",
  "notes": "Updated notes"
}
```

Success response: shared prescription shape.

Error response example:

```json
{
  "detail": "Only draft prescriptions can be modified."
}
```

Frontend notes: only draft prescriptions are editable.
`doctor_specialty` may be a predefined value from the doctor specialties endpoint, blank, omitted, or custom free text.

## POST `/api/pharmacist/prescriptions/<id>/items/`

Auth/role: approved pharmacist who owns the prescription.

Request body:

```json
{
  "medication_name": "Amoxicillin",
  "dosage": "500mg",
  "frequency": "Twice daily",
  "duration": "7 days",
  "instructions": "Take after food"
}
```

Success response: `201 Created`, shared item shape.

Error response example:

```json
{
  "detail": "Only draft prescriptions can be modified."
}
```

Frontend notes: `medicine_name` and `instructions_text` are still accepted for backward compatibility.

## PATCH `/api/pharmacist/prescriptions/<id>/items/<item_id>/`

Auth/role: approved pharmacist who owns the prescription.

Request body:

```json
{
  "medication_name": "Updated medication",
  "dosage": "250mg",
  "frequency": "Once daily",
  "duration": "5 days",
  "instructions": "Take before food"
}
```

Success response: shared item shape.

Error response example:

```json
{
  "detail": "Not found."
}
```

Frontend notes: only draft prescriptions are editable.

## DELETE `/api/pharmacist/prescriptions/<id>/items/<item_id>/`

Auth/role: approved pharmacist who owns the prescription.

Request body: none.

Success response: `204 No Content`.

Error response example:

```json
{
  "detail": "Only draft prescriptions can be modified."
}
```

Frontend notes: no response body is returned on success.

## POST `/api/pharmacist/prescriptions/<id>/submit/`

Auth/role: approved pharmacist who owns the prescription.

Request body: none.

Success response:

```json
{
  "detail": "Prescription submitted successfully",
  "prescription": {
    "id": 10,
    "patient": {
      "id": 3,
      "full_name": "Patient Name",
      "phone_number": "+963900000000"
    },
    "pharmacist": {
      "id": 2,
      "full_name": "Pharmacist Name"
    },
    "pharmacy": {
      "id": 1,
      "name": "Main Pharmacy",
      "address": "Street address",
      "phone_number": "+963900000001"
    },
    "session": 7,
    "session_id": 7,
    "doctor_name": "Doctor Name",
    "doctor_specialty": "Internal Medicine",
    "diagnosis": "Diagnosis text",
    "status": "submitted",
    "prescribed_at": "2026-05-05T12:00:00Z",
    "submitted_at": "2026-05-05T12:05:00Z",
    "delivered_at": null,
    "notes": "",
    "items": [],
    "created_at": "2026-05-05T12:00:00Z",
    "updated_at": "2026-05-05T12:05:00Z"
  }
}
```

Error response example:

```json
{
  "detail": "Prescription must include at least one item before submission",
  "code": "prescription_has_no_items"
}
```

Frontend notes: successful response wraps the prescription in a `prescription` key.
The nested `prescription` object is the full shared prescription shape.

## GET `/api/patients/me/prescriptions/`

Auth/role: patient.

Request body: none.

Query params:

- `include_drafts=true`: optional. Without this, draft prescriptions are hidden.

Success response: DRF paginated list using the shared prescription shape.

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 10,
      "status": "submitted",
      "items": []
    }
  ]
}
```

Error response example:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Frontend notes: unlike pharmacist list, this view uses DRF pagination because it is a generic viewset.

## GET `/api/patients/me/prescriptions/<id>/`

Auth/role: patient who owns the prescription.

Request body: none.

Success response: shared prescription shape.

Error response example:

```json
{
  "detail": "Not found."
}
```

Frontend notes: this endpoint logs prescription view access.

## POST `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/transcribe-audio/`

Auth/role: approved pharmacist who owns the prescription.

Request body: `multipart/form-data`

| Field | Type | Required |
|---|---|---|
| `audio` | file | yes |

Success response:

```json
{
  "item_id": 1,
  "transcription_status": "completed",
  "raw_transcript": "Take one pill after food",
  "approved_instruction_text": null,
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "audio_url": "http://localhost:8000/media/prescriptions/1/audio/file.mp3",
  "detail": "Audio transcribed successfully"
}
```

Error response example:

```json
{
  "detail": "Audio transcription failed",
  "code": "transcription_failed",
  "item_id": 1,
  "transcription_status": "failed"
}
```

Frontend notes: provider remains `gemini` in Phase 1. The transcript must be approved before it is considered final instruction text.

## POST `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/approve-transcript/`

Auth/role: approved pharmacist who owns the prescription.

Request body:

```json
{
  "approved_instruction_text": "Take one pill after food"
}
```

Success response:

```json
{
  "item_id": 1,
  "raw_transcript": "Take one pill after food",
  "approved_instruction_text": "Take one pill after food",
  "transcription_status": "approved",
  "detail": "Transcript approved successfully"
}
```

Error response example:

```json
{
  "detail": "Approved instruction text is required.",
  "code": "missing_approved_instruction_text"
}
```

Frontend notes: the backend stores approved transcript text separately from manual item instructions and returns `transcription_status: "approved"` in this response.

## POST `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/generate-sign/`

Auth/role: approved pharmacist who owns the prescription.

Request body: none.

Text selection behavior:

1. Use `approved_instruction_text` if available.
2. Else use `raw_transcript` if available.
3. Else use `instructions` if available.
4. If no usable text exists, return `400`.

Success response:

```json
{
  "item_id": 1,
  "sign_status": "completed",
  "gloss_text": "Generated gloss text",
  "supporting_text": "Generated gloss text",
  "video_url": null,
  "output_type": "gloss_only",
  "video_generation_supported": false,
  "detail": "Gloss generated successfully"
}
```

Error response example:

```json
{
  "detail": "Gloss generation failed",
  "code": "gloss_generation_failed",
  "item_id": 1,
  "sign_status": "failed"
}
```

No usable text error example:

```json
{
  "detail": "No instruction text is available for gloss generation.",
  "code": "missing_instruction_text",
  "item_id": 1,
  "sign_status": "pending"
}
```

Frontend notes: video generation is explicitly unsupported in Phase 1; render this as gloss-only output.

## Phase 4 - Media Upload, Audio Transcription, Transcript Approval, Gloss

Phase 4 stabilizes the prescription item processing flow for the frontend. All endpoints below require an authenticated approved pharmacist who owns the prescription. Archived prescriptions cannot be modified or processed.

### Shared Media URL Behavior

Prescription item responses always include:

```json
{
  "image_url": null,
  "audio_url": null,
  "video_url": null
}
```

When media exists and the serializer has request context, `image_url` and `audio_url` are absolute URLs. Without request context, relative `/media/...` URLs may be returned. `video_url` remains `null` in Phase 4 because sign video generation is not implemented.

Gloss responses always include:

```json
{
  "video_url": null,
  "output_type": "gloss_only",
  "video_generation_supported": false
}
```

### Item Image Upload

Endpoints:

- `POST /api/pharmacist/prescriptions/<prescription_id>/items/`
- `PATCH /api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/`

Request body may be JSON or `multipart/form-data`. JSON item create/update remains supported.

Accepted image file fields:

- `image` preferred
- `image_file`
- `medication_image`
- `medicine_image` backward-compatible backend name

Multipart example:

```text
medication_name=Amoxicillin
dosage=500mg
frequency=Twice daily
duration=7 days
instructions=Take after food
image=<file>
```

Success response: shared item shape with `image_url` populated when an image was saved.

Image validation codes:

- `invalid_image_file`
- `image_too_large`
- `unsupported_image_type`

### Audio Upload and Transcription

Endpoint:

`POST /api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/transcribe-audio/`

Request body: `multipart/form-data`.

Accepted audio file fields:

- `audio` preferred
- `audio_file` backward-compatible alias
- `voice` backward-compatible alias

Success response:

```json
{
  "item_id": 1,
  "transcription_status": "completed",
  "raw_transcript": "Take one pill after food",
  "approved_instruction_text": null,
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "audio_url": "http://localhost:8000/media/prescriptions/1/audio/file.mp3",
  "detail": "Audio transcribed successfully"
}
```

Failure response:

```json
{
  "detail": "Audio transcription failed",
  "code": "transcription_failed",
  "item_id": 1,
  "transcription_status": "failed"
}
```

Provider-not-configured response:

```json
{
  "detail": "Audio transcription provider is not configured",
  "code": "transcription_provider_not_configured",
  "item_id": 1,
  "transcription_status": "failed"
}
```

Audio validation codes:

- `missing_audio_file`
- `invalid_audio_file`
- `audio_too_large`
- `unsupported_audio_type`
- `transcription_failed`
- `transcription_provider_not_configured`

Provider notes: Phase 4 uses Gemini only. The backend does not switch to Whisper, Groq, or another provider.

### Transcript Approval

Endpoint:

`POST /api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/approve-transcript/`

Request body:

```json
{
  "approved_instruction_text": "Take one pill after food"
}
```

Success response:

```json
{
  "item_id": 1,
  "raw_transcript": "Take one pill after food",
  "approved_instruction_text": "Take one pill after food",
  "transcription_status": "approved",
  "detail": "Transcript approved successfully"
}
```

Validation code:

- `missing_approved_instruction_text`

### Gloss Generation

Endpoint:

`POST /api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/generate-sign/`

Text source priority:

1. `approved_instruction_text`
2. `raw_transcript`
3. `instructions`

No usable text response:

```json
{
  "detail": "No instruction text is available for gloss generation.",
  "code": "missing_instruction_text",
  "item_id": 1,
  "sign_status": "pending"
}
```

Success response:

```json
{
  "item_id": 1,
  "sign_status": "completed",
  "gloss_text": "Generated gloss text",
  "supporting_text": "Generated gloss text",
  "video_url": null,
  "output_type": "gloss_only",
  "video_generation_supported": false,
  "detail": "Gloss generated successfully"
}
```

Failure response:

```json
{
  "detail": "Gloss generation failed",
  "code": "gloss_generation_failed",
  "item_id": 1,
  "sign_status": "failed"
}
```

Provider-not-configured response:

```json
{
  "detail": "Gloss generation provider is not configured",
  "code": "gloss_provider_not_configured",
  "item_id": 1,
  "sign_status": "failed"
}
```

Gloss validation/provider codes:

- `missing_instruction_text`
- `gloss_generation_failed`
- `gloss_provider_not_configured`

### Phase 4 Permission and Status Codes

- `prescription_not_found`
- `prescription_permission_denied`
- `prescription_archived`
- `item_not_found`

Other pharmacists' prescriptions/items are not exposed. Foreign prescription or item access is returned as not found.


## Phase 2 — Auth, Registration, Session QR, Environment

Phase 2 stabilizes backend contracts used by the mobile frontend for authentication,
registration, OTP, patient session QR, and runtime configuration. All endpoints below
use the base `/api/` prefix.

### Auth

#### POST `/api/auth/login/`

Request body:

```json
{
  "phone_number": "0999999999",
  "password": "StrongPass123!"
}
```

`email` is still accepted as a login identifier for backward compatibility. `phone`
is also accepted as an alias for `phone_number`.

Success response:

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999999999",
    "role": "patient",
    "is_active": true,
    "is_verified": false,
    "approval_status": "approved"
  },
  "profile": {},
  "access": "...",
  "refresh": "..."
}
```

Pending/rejected approval errors:

```json
{
  "detail": "Account is pending approval.",
  "code": "approval_pending",
  "approval_status": "pending"
}
```

```json
{
  "detail": "Account registration was rejected.",
  "code": "approval_rejected",
  "approval_status": "rejected",
  "rejection_reason": "Invalid documents"
}
```

Other common login errors use:

```json
{
  "detail": "Invalid credentials.",
  "code": "invalid_credentials",
  "fields": {}
}
```

#### POST `/api/auth/refresh/`

Request body:

```json
{
  "refresh": "..."
}
```

Success response:

```json
{
  "access": "...",
  "refresh": "..."
}
```

Backend currently has SimpleJWT refresh rotation enabled, so a new `refresh` token may
be returned. Frontend should store the returned refresh token when present.

#### POST `/api/auth/logout/`

Request body:

```json
{
  "refresh": "..."
}
```

Success response:

```json
{
  "detail": "Logged out successfully"
}
```

Invalid refresh token errors use `code: "invalid_refresh"`.

#### POST `/api/auth/change-password/`

Auth/role: authenticated user.

Request body:

```json
{
  "current_password": "...",
  "new_password": "...",
  "confirm_password": "..."
}
```

Success response:

```json
{
  "detail": "Password changed successfully"
}
```

Validation failures include `detail`, `code`, `fields`, and field-level keys where
possible for backward compatibility.

#### GET `/api/auth/me/`

Auth/role: authenticated user.

Success response:

```json
{
  "user": {
    "id": 1,
    "email": null,
    "phone_number": "0999999999",
    "role": "patient",
    "is_active": true,
    "is_verified": false,
    "approval_status": "approved"
  },
  "profile": {}
}
```

### Registration And OTP

#### POST `/api/auth/patient/register/request-otp/`
#### POST `/api/auth/pharmacist/register/request-otp/`

Request body:

```json
{
  "phone_number": "0999999999"
}
```

`phone` remains accepted as an alias for `phone_number`.

Success response when `DEBUG=True`:

```json
{
  "detail": "OTP sent successfully",
  "expires_in_seconds": 300,
  "debug_otp": "123456"
}
```

`debug_otp` is only returned when `DEBUG=True`. If `DEBUG=False` and no real OTP
provider is configured, response is:

```json
{
  "detail": "OTP delivery provider is not configured",
  "code": "otp_provider_not_configured",
  "fields": {}
}
```

#### POST `/api/auth/patient/register/`
#### POST `/api/auth/pharmacist/register/`

Success response:

```json
{
  "detail": "Registration submitted successfully",
  "approval_status": "pending",
  "user": {},
  "profile": {}
}
```

Common registration and OTP errors use:

```json
{
  "detail": "...",
  "code": "duplicate_phone",
  "fields": {
    "phone_number": "Phone number is already registered."
  }
}
```

Stable codes in Phase 2:

- `duplicate_phone`
- `invalid_otp`
- `expired_otp`
- `otp_max_attempts_exceeded`
- `missing_required_field`
- `otp_provider_not_configured`

### Session QR

#### POST `/api/patients/me/session-qr/`

Auth/role: patient.

Success response:

```json
{
  "qr_token": "...",
  "qr_payload": "...",
  "expires_at": "2026-05-06T12:00:00Z",
  "expires_in_seconds": 300
}
```

#### POST `/api/pharmacist/sessions/start-by-qr/`

Auth/role: approved pharmacist.

Preferred request body:

```json
{
  "qr_token": "..."
}
```

`qr_payload` is still accepted for backward compatibility.

Success response:

```json
{
  "session": {
    "id": 1,
    "status": "active",
    "started_at": "2026-05-06T12:00:00Z",
    "expires_at": "2026-05-06T12:30:00Z"
  },
  "patient": {
    "id": 2,
    "full_name": "Patient Name",
    "phone_number": "0999999999",
    "birth_date": "2000-01-01",
    "gender": "female",
    "hearing_disability_level": ""
  },
  "medical_info": {
    "blood_type": "",
    "allergies": "",
    "chronic_conditions": "",
    "notes": ""
  },
  "recent_prescriptions": []
}
```

The backend may include additional compatible keys such as pharmacist, pharmacy,
regular medication, pregnancy, or breastfeeding fields.

Stable QR error codes:

- `qr_expired`
- `qr_used`
- `qr_revoked`
- `qr_invalid`

Example:

```json
{
  "detail": "QR token has expired",
  "code": "qr_expired",
  "fields": {}
}
```

#### GET `/api/pharmacist/sessions/`

Auth/role: approved pharmacist.

Query params:

- `status`: optional session status filter.

Success response: list of sessions owned by the pharmacist.

#### POST `/api/pharmacist/sessions/<session_id>/end/`

Auth/role: approved pharmacist who owns the session.

Success response:

```json
{
  "detail": "Session ended successfully",
  "session": {
    "id": 1,
    "status": "ended",
    "ended_at": "2026-05-06T12:10:00Z"
  }
}
```

The database status remains the existing backend status enum value; the response maps
successful end action to frontend-friendly `status: "ended"`.

### Environment

JWT duration env vars accept either integers using their historical default units or
duration suffixes:

```env
JWT_ACCESS_TOKEN_LIFETIME=5h
JWT_REFRESH_TOKEN_LIFETIME=7d
```

Supported suffixes:

- `m`: minutes
- `h`: hours
- `d`: days

`PHARMASIGN_ENV=development` defaults omitted `DEBUG` to `True` for local development.
`PHARMASIGN_ENV=production` defaults omitted `DEBUG` to `False`. Production should set
`DEBUG=False` explicitly.

## Phase 3 — Prescription Lifecycle

Phase 3 stabilizes the prescription lifecycle endpoints used by the mobile frontend.
Frontend should prefer the pharmacist namespace for lifecycle actions:
`/api/pharmacist/prescriptions/<id>/...`.

### Lifecycle Response Shape

All pharmacist lifecycle endpoints return:

```json
{
  "detail": "Prescription submitted successfully",
  "prescription": {
    "id": 1,
    "status": "submitted",
    "submitted_at": "2026-05-06T12:00:00Z",
    "delivered_at": null,
    "patient": {},
    "pharmacist": {},
    "pharmacy": {},
    "session": 1,
    "session_id": 1,
    "items": []
  }
}
```

`cancel` and `archive` do not add timestamps in Phase 3 because the model does not
currently have `cancelled_at` or `archived_at` fields. Status is the source of truth.

### Valid Status Transitions

- `draft -> submitted`
- `submitted -> confirmed`
- `submitted -> cancelled`
- `confirmed -> delivered`
- `confirmed -> cancelled`
- `delivered -> archived`
- `cancelled -> archived`

Invalid examples:

- `draft -> delivered`
- `delivered -> cancelled`
- `archived -> anything`
- `cancelled -> delivered`

Invalid transition response:

```json
{
  "detail": "Cannot move prescription from draft to delivered",
  "code": "invalid_prescription_status_transition",
  "current_status": "draft",
  "target_status": "delivered"
}
```

### POST `/api/pharmacist/prescriptions/<id>/submit/`

Auth/role: approved pharmacist who owns the prescription.

Allowed transition: `draft -> submitted`.

Validation:

- Prescription must belong to the authenticated pharmacist.
- Prescription must include at least one item.

Success response:

```json
{
  "detail": "Prescription submitted successfully",
  "prescription": {
    "id": 1,
    "status": "submitted",
    "submitted_at": "2026-05-06T12:00:00Z"
  }
}
```

No-items error:

```json
{
  "detail": "Prescription must include at least one item before submission",
  "code": "prescription_has_no_items"
}
```

### POST `/api/pharmacist/prescriptions/<id>/confirm/`

Auth/role: approved pharmacist who owns the prescription.

Allowed transition: `submitted -> confirmed`.

Success response:

```json
{
  "detail": "Prescription confirmed successfully",
  "prescription": {
    "id": 1,
    "status": "confirmed"
  }
}
```

Backward compatibility: the legacy `POST /api/prescriptions/<id>/confirm/` endpoint
still exists and may confirm a draft prescription for existing backend consumers.
Frontend should use the pharmacist namespace above.

### POST `/api/pharmacist/prescriptions/<id>/deliver/`

Auth/role: approved pharmacist who owns the prescription.

Allowed transition: `confirmed -> delivered`.

Success response:

```json
{
  "detail": "Prescription delivered successfully",
  "prescription": {
    "id": 1,
    "status": "delivered",
    "delivered_at": "2026-05-06T12:05:00Z"
  }
}
```

### POST `/api/pharmacist/prescriptions/<id>/cancel/`

Auth/role: approved pharmacist who owns the prescription.

Allowed transitions:

- `submitted -> cancelled`
- `confirmed -> cancelled`

Success response:

```json
{
  "detail": "Prescription cancelled successfully",
  "prescription": {
    "id": 1,
    "status": "cancelled"
  }
}
```

### POST `/api/pharmacist/prescriptions/<id>/archive/`

Auth/role: approved pharmacist who owns the prescription.

Allowed transitions:

- `delivered -> archived`
- `cancelled -> archived`

Success response:

```json
{
  "detail": "Prescription archived successfully",
  "prescription": {
    "id": 1,
    "status": "archived"
  }
}
```

### Lifecycle Error Codes

- `prescription_not_found`
- `prescription_permission_denied`
- `prescription_has_no_items`
- `prescription_items_not_ready`
- `invalid_prescription_status_transition`

`prescription_items_not_ready` is reserved for item-readiness validation if stricter
item confirmation rules are enabled later. Phase 3 submit validation only requires at
least one item.

### Patient Visibility

Patient endpoints:

- `GET /api/patients/me/prescriptions/`
- `GET /api/patients/me/prescriptions/<id>/`

Patients can only access their own prescriptions. By default, drafts are hidden.
Non-draft prescriptions are visible, including `submitted`, `confirmed`, `delivered`,
`cancelled`, and `archived`. `include_drafts=true` includes drafts for compatibility.

### Pharmacist Visibility

Pharmacist endpoints:

- `GET /api/pharmacist/prescriptions/`
- `GET /api/pharmacist/prescriptions/<id>/`

Pharmacists only see prescriptions they own. A prescription owned by another
pharmacist returns:

```json
{
  "detail": "Prescription not found",
  "code": "prescription_not_found"
}
```
