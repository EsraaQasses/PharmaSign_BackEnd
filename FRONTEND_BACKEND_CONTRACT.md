# Frontend Backend Contract - Phase 1 Prescriptions

Base URL prefix: `/api/`

Authentication: all endpoints in this document require a Bearer JWT access token.

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
  "detail": "Prescription submitted successfully.",
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
  "detail": "Prescription must contain at least one medication item before submission."
}
```

Frontend notes: successful response wraps the prescription in a `prescription` key.
The nested `prescription` object is the full shared prescription shape.

## GET `/api/patients/me/prescriptions/`

Auth/role: patient.

Request body: none.

Query params:

- `include_drafts=true`: optional. Without this, only submitted prescriptions are returned.

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
  "approved_instruction_text": [
    "This field is required."
  ]
}
```

Frontend notes: the backend stores approved text in the item instruction field and returns `transcription_status: "approved"` in this response.

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
