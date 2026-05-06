# Server Smoke Tests

Use this checklist in Postman against a deployed PharmaSign backend after Phase 1-5 backend integration.

## Postman Environment

Create an environment with these variables:

| Variable | Example | Notes |
|---|---|---|
| `base_url` | `https://api.example.com/api` | Do not include trailing slash. |
| `pharmacist_phone` | `0999000001` | Approved pharmacist test account. |
| `pharmacist_password` | `StrongPass123!` | Approved pharmacist password. |
| `patient_phone` | `0999000002` | Approved patient test account. |
| `patient_password` | `StrongPass123!` | Approved patient password. |
| `other_patient_access` | | Optional token for negative tests. |
| `other_pharmacist_access` | | Optional token for negative tests. |
| `access` | | Saved from pharmacist login. |
| `refresh` | | Saved from pharmacist login. |
| `patient_access` | | Saved from patient login. |
| `patient_refresh` | | Saved from patient login. |
| `qr_token` | | Saved from patient session QR. |
| `session_id` | | Saved from pharmacist start-by-QR. |
| `patient_id` | | Saved from pharmacist start-by-QR. |
| `prescription_id` | | Saved from prescription create. |
| `empty_prescription_id` | | Saved from negative no-item prescription create. |
| `item_id` | | Saved from item create. |
| `raw_transcript` | | Saved from transcription response. |

For protected pharmacist requests, use header:

```text
Authorization: Bearer {{access}}
```

For protected patient requests, use header:

```text
Authorization: Bearer {{patient_access}}
```

## Test Data Assumptions

- The pharmacist account is active, verified, approved, and has a `PharmacistProfile` with `is_approved=true`.
- The patient account is active, verified/approved enough for JWT auth, and has a `PatientProfile`.
- The pharmacist can access the patient through current backend organization/pharmacy rules.
- For transcription and gloss success tests, deployment has `GEMINI_API_KEY` configured.
- For media tests, have a small PNG/JPG image file and a small supported audio file such as MP3, WAV, M4A, or OGG.

## Scenario 1 - Pharmacist Login And Auth Check

1. Login pharmacist
   - Method/path: `POST {{base_url}}/auth/login/`
   - Body JSON:
     ```json
     {
       "phone_number": "{{pharmacist_phone}}",
       "password": "{{pharmacist_password}}"
     }
     ```
   - Expected: `200 OK`
   - Expected fields: `user`, `profile`, `access`, `refresh`
   - Save: `access -> {{access}}`, `refresh -> {{refresh}}`

2. Check pharmacist auth
   - Method/path: `GET {{base_url}}/auth/me/`
   - Auth: `Bearer {{access}}`
   - Expected: `200 OK`
   - Expected fields: `user.id`, `user.role`, `profile`
   - Verify: `user.role` is `pharmacist`

## Scenario 2 - Patient Login And Auth Check

1. Login patient
   - Method/path: `POST {{base_url}}/auth/login/`
   - Body JSON:
     ```json
     {
       "phone_number": "{{patient_phone}}",
       "password": "{{patient_password}}"
     }
     ```
   - Expected: `200 OK`
   - Expected fields: `user`, `profile`, `access`, `refresh`
   - Save: `access -> {{patient_access}}`, `refresh -> {{patient_refresh}}`

2. Check patient auth
   - Method/path: `GET {{base_url}}/auth/me/`
   - Auth: `Bearer {{patient_access}}`
   - Expected: `200 OK`
   - Expected fields: `user.id`, `user.role`, `profile`
   - Verify: `user.role` is `patient`

## Scenario 3 - Patient Session QR

1. Patient creates session QR
   - Method/path: `POST {{base_url}}/patients/me/session-qr/`
   - Auth: `Bearer {{patient_access}}`
   - Body: none
   - Expected: `201 Created`
   - Expected fields: `qr_token`, `qr_payload`, `expires_at`, `expires_in_seconds`
   - Save: `qr_token -> {{qr_token}}`

2. Pharmacist starts session by QR
   - Method/path: `POST {{base_url}}/pharmacist/sessions/start-by-qr/`
   - Auth: `Bearer {{access}}`
   - Body JSON:
     ```json
     {
       "qr_token": "{{qr_token}}"
     }
     ```
   - Expected: `201 Created` or `200 OK` if an active session already exists
   - Expected fields: `session.id`, `session.status`, `patient.id`, `medical_info`, `recent_prescriptions`
   - Save: `session.id -> {{session_id}}`, `patient.id -> {{patient_id}}`

3. List pharmacist sessions
   - Method/path: `GET {{base_url}}/pharmacist/sessions/`
   - Auth: `Bearer {{access}}`
   - Expected: `200 OK`
   - Expected fields: array of sessions

Keep the session active until prescription tests are done.

## Scenario 4 - Prescription Full Happy Path

1. Create prescription from session
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/`
   - Auth: `Bearer {{access}}`
   - Body JSON:
     ```json
     {
       "session_id": "{{session_id}}",
       "patient_id": "{{patient_id}}",
       "doctor_name": "Smoke Test Doctor",
       "doctor_specialty": "General",
       "diagnosis": "Smoke test diagnosis",
       "notes": "Smoke test prescription"
     }
     ```
   - Expected: `201 Created`
   - Expected fields: `id`, `status`, `patient`, `pharmacist`, `pharmacy`, `items`
   - Save: `id -> {{prescription_id}}`

2. Add item
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/items/`
   - Auth: `Bearer {{access}}`
   - Body JSON:
     ```json
     {
       "medication_name": "Amoxicillin",
       "dosage": "500mg",
       "frequency": "Twice daily",
       "duration": "7 days",
       "instructions": "Take after food"
     }
     ```
   - Expected: `201 Created`
   - Expected fields: `id`, `medication_name`, `instructions`, `image_url`, `audio_url`, `video_url`, `sign_status`
   - Save: `id -> {{item_id}}`

3. Submit prescription
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/submit/`
   - Auth: `Bearer {{access}}`
   - Expected: `200 OK`
   - Expected fields: `detail`, `prescription.status`
   - Verify: `prescription.status` is `submitted`

4. Confirm prescription
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/confirm/`
   - Auth: `Bearer {{access}}`
   - Expected: `200 OK`
   - Verify: `prescription.status` is `confirmed`

5. Deliver prescription
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/deliver/`
   - Auth: `Bearer {{access}}`
   - Expected: `200 OK`
   - Verify: `prescription.status` is `delivered`, `prescription.delivered_at` exists

6. Patient lists prescriptions
   - Method/path: `GET {{base_url}}/patients/me/prescriptions/`
   - Auth: `Bearer {{patient_access}}`
   - Expected: `200 OK`
   - Expected fields: `count`, `results`
   - Verify: `{{prescription_id}}` appears in `results`

7. Patient opens prescription detail
   - Method/path: `GET {{base_url}}/patients/me/prescriptions/{{prescription_id}}/`
   - Auth: `Bearer {{patient_access}}`
   - Expected: `200 OK`
   - Expected fields: shared prescription shape with `items`

## Scenario 5 - Media And Transcription

Run this before submitting if you want to update the same draft item. If the prescription from Scenario 4 is already delivered, create a new draft prescription and item first.

1. Upload medication image
   - Method/path: `PATCH {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/items/{{item_id}}/`
   - Auth: `Bearer {{access}}`
   - Body: `multipart/form-data`
   - Fields:
     - `image`: file
   - Expected: `200 OK`
   - Expected fields: `image_url`
   - Verify: `image_url` is absolute or a valid `/media/...` URL

2. Transcribe audio
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/items/{{item_id}}/transcribe-audio/`
   - Auth: `Bearer {{access}}`
   - Body: `multipart/form-data`
   - Fields:
     - `audio`: file
   - Expected: `200 OK`
   - Expected fields: `item_id`, `transcription_status`, `raw_transcript`, `approved_instruction_text`, `provider`, `model`, `audio_url`, `detail`
   - Verify: `transcription_status` is `completed`, `provider` is `gemini`
   - Save: `raw_transcript -> {{raw_transcript}}`
   - If provider is not configured, expected status is `503` with `code=transcription_provider_not_configured`

3. Approve transcript
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/items/{{item_id}}/approve-transcript/`
   - Auth: `Bearer {{access}}`
   - Body JSON:
     ```json
     {
       "approved_instruction_text": "{{raw_transcript}}"
     }
     ```
   - Expected: `200 OK`
   - Expected fields: `item_id`, `raw_transcript`, `approved_instruction_text`, `transcription_status`, `detail`
   - Verify: `transcription_status` is `approved`

4. Generate gloss
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/items/{{item_id}}/generate-sign/`
   - Auth: `Bearer {{access}}`
   - Body: none
   - Expected: `200 OK`
   - Expected fields: `item_id`, `sign_status`, `gloss_text`, `supporting_text`, `video_url`, `output_type`, `video_generation_supported`, `detail`
   - Verify: `sign_status` is `completed`, `video_url` is `null`, `output_type` is `gloss_only`, `video_generation_supported` is `false`
   - If provider is not configured, expected status is `503` with `code=gloss_provider_not_configured`

## Scenario 6 - Negative Tests

1. Submit prescription with no items
   - Create a new prescription using Scenario 4 step 1 and save `id -> {{empty_prescription_id}}`
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{empty_prescription_id}}/submit/`
   - Auth: `Bearer {{access}}`
   - Expected: `400 Bad Request`
   - Verify: `code` is `prescription_has_no_items`

2. Deliver draft prescription
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{empty_prescription_id}}/deliver/`
   - Auth: `Bearer {{access}}`
   - Expected: `400 Bad Request`
   - Verify: `code` is `invalid_prescription_status_transition`

3. Patient cannot access another patient prescription
   - Method/path: `GET {{base_url}}/patients/me/prescriptions/{{prescription_id}}/`
   - Auth: `Bearer {{other_patient_access}}`
   - Expected: `404 Not Found`

4. Pharmacist cannot access another pharmacist prescription
   - Method/path: `GET {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/`
   - Auth: `Bearer {{other_pharmacist_access}}`
   - Expected: `404 Not Found`
   - Verify when response includes a code: `code` is `prescription_not_found`

5. Start-by-QR with invalid token
   - Method/path: `POST {{base_url}}/pharmacist/sessions/start-by-qr/`
   - Auth: `Bearer {{access}}`
   - Body JSON:
     ```json
     {
       "qr_token": "invalid-token"
     }
     ```
   - Expected: `400 Bad Request`
   - Verify: `code` is `qr_invalid`

6. Transcribe without audio
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{prescription_id}}/items/{{item_id}}/transcribe-audio/`
   - Auth: `Bearer {{access}}`
   - Body: empty `multipart/form-data`
   - Expected: `400 Bad Request`
   - Verify: `code` is `missing_audio_file`

7. Generate gloss with no text
   - Create a new draft prescription and add an item with no `instructions`, no transcript, and no approved text.
   - Method/path: `POST {{base_url}}/pharmacist/prescriptions/{{new_prescription_id}}/items/{{new_item_id}}/generate-sign/`
   - Auth: `Bearer {{access}}`
   - Expected: `400 Bad Request`
   - Verify: `code` is `missing_instruction_text`

## Cleanup

End the pharmacist-patient session:

- Method/path: `POST {{base_url}}/pharmacist/sessions/{{session_id}}/end/`
- Auth: `Bearer {{access}}`
- Expected: `200 OK`
- Verify: `detail`, `session.id`, `session.status=ended`, `session.ended_at`

Optional token cleanup:

- Method/path: `POST {{base_url}}/auth/logout/`
- Auth: `Bearer {{access}}`
- Body JSON:
  ```json
  {
    "refresh": "{{refresh}}"
  }
  ```
- Expected: `200 OK`
