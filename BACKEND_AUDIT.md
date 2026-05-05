# PharmaSign Backend Audit

## 1. Executive Summary

The backend is a Django 5.1 / Django REST Framework API with custom `accounts.User`, JWT auth, registration OTP records, patient/pharmacist roles, organization-scoped administration, pharmacist approval, patient profiles, pharmacy profiles, patient sessions, prescriptions, audio transcription, and Gemini-based gloss generation.

Implemented areas include:

| Area | Status | Notes |
|---|---|---|
| Django app structure | Working | Apps are registered in `pharmasign/settings.py`. |
| JWT login/refresh/logout | Working | Uses SimpleJWT plus approval-aware token authentication. |
| OTP storage/validation | Partial | OTP records exist; production WhatsApp/SMS delivery is not configured. |
| Patient registration | Partial | Creates pending patient account, profile, medical info, and QR value after OTP. |
| Pharmacist registration | Partial | Creates pending pharmacist account, pharmacy, and profile after OTP. |
| Approval workflow | Partial | Admin/staff approval endpoints exist, but no organization API endpoint exists to create/manage organization staff through REST. |
| Patient profile/settings | Working | Patient self-profile and settings endpoints exist. |
| Pharmacy/pharmacist profile | Working | Pharmacist self-profile and pharmacy endpoints exist. |
| Sessions and QR tokens | Partial | Login QR and session QR exist; session expiry/ending is only partially enforced. |
| Prescriptions | Partial | Pharmacist workflow exists, but status lifecycle is limited and general create endpoint intentionally rejects writes. |
| Audio transcription | Partial | Gemini transcription exists; Whisper/Groq are not implemented. |
| Gloss/sign-language processing | Partial | Gemini text gloss generation exists; no video generation or persisted provider metadata beyond item status/supporting text. |
| Production readiness | Partial | CORS/env/media settings exist, but example JWT env values conflict with integer casts and DEBUG defaults to true. |

Missing or incomplete areas are mostly integration-hardening work: production OTP delivery, consistent approval behavior, complete prescription status transitions, endpoint-level API contracts, session expiry cleanup, organization REST management, consistent error response format, and a decision on Gemini vs Whisper/Groq.

## 2. Backend Apps and Structure

| App / module | Important files | Purpose |
|---|---|---|
| `pharmasign` | `settings.py`, `urls.py`, `api_urls.py`, `wsgi.py`, `asgi.py` | Project settings and root API routing. |
| `common` | `models.py`, `choices.py`, `permissions.py`, `uploads.py`, `utils.py` | Shared timestamp model, role/status choices, permissions, upload validation, QR/PIN helpers. |
| `accounts` | `models.py`, `serializers.py`, `views.py`, `urls.py`, `services.py`, `authentication.py`, `jwt.py`, migrations `0001`-`0005` | Custom user, OTP, auth endpoints, JWT refresh, approval-aware auth. |
| `organizations` | `models.py`, `serializers.py`, `admin.py`, migration `0001` | Organization and organization staff models/admin. No REST URLs found. |
| `patients` | `models.py`, `serializers.py`, `views.py`, `urls.py`, `services.py`, migrations `0001`-`0006` | Patient profiles, medical info, settings, enrollments, QR tokens, patient sessions. |
| `pharmacies` | `models.py`, `serializers.py`, `views.py`, `urls.py`, migration `0001` | Pharmacy and pharmacist profile models/endpoints. |
| `prescriptions` | `models.py`, `serializers.py`, `views.py`, `urls.py`, `services.py`, `transcription.py`, migrations `0001`-`0003` | Prescription CRUD workflow, items, transcription state, access logs, gloss generation. |
| `transcriptions` | `views.py`, `urls.py`, `services.py`, `validators.py`, `exceptions.py` | Standalone pharmacist audio transcription test endpoint using Gemini. |

## 3. Models

| Model | File path | Fields | Relationships | Purpose | Completeness |
|---|---|---|---|---|---|
| `TimeStampedModel` | `common/models.py` | `created_at`, `updated_at` | Abstract base | Shared timestamps | Working |
| `User` | `accounts/models.py` | `email`, `phone_number`, `role`, `is_staff`, `is_active`, `is_verified`, `approval_status`, `approved_at`, `rejection_reason` | `approved_by` self-FK | Custom auth user for admin/patient/pharmacist | Partial: email nullable while `USERNAME_FIELD=email`; role approval is present |
| `PhoneOTP` | `accounts/models.py` | `phone_number`, `purpose`, `code_hash`, `expires_at`, `used_at`, `attempts`, `max_attempts` | FK `user` nullable | Registration OTP challenge | Partial: storage/validation works; delivery provider missing |
| `Organization` | `organizations/models.py` | `name`, `description`, `phone`, `address` | Has patients, pharmacies, staff | Organization owner/scope | Partial: model/admin only, no REST URL |
| `OrganizationStaffProfile` | `organizations/models.py` | `job_title`, `can_manage_patients`, `can_manage_pharmacists` | O2O `user`, FK `organization` | Scoped organization admin permissions | Partial: model/admin only |
| `PatientProfile` | `patients/models.py` | `full_name`, `phone_number`, `birth_date`, `gender`, `address`, `hearing_disability_level`, `is_self_registered`, `qr_code_value`, `qr_is_active`, `record_access_pin_hash` | O2O `user`, FK `organization` | Patient identity/profile and static QR access | Partial: no national ID field despite serializers returning blank compatibility value |
| `PatientEnrollment` | `patients/models.py` | names, parents, birth date, gender, address, phone, hearing level, notes, `is_account_created` | FK `organization`, O2O nullable `patient_profile`, FK `created_by` | Admin-created enrollment before account creation | Working/partial: admin workflow exists |
| `PatientMedicalInfo` | `patients/models.py` | `blood_type`, `chronic_conditions`, `allergies`, `is_pregnant`, `is_breastfeeding`, `notes` | O2O `patient` | Patient medical details | Working |
| `PatientSettings` | `patients/models.py` | `notifications_enabled`, `prescription_reminders`, `dark_mode`, `use_biometrics` | O2O `patient` | Patient app settings | Working |
| `PatientLoginQR` | `patients/models.py` | `token_hash`, `is_active`, `revoked_at` | FK `patient`, FK `created_by` | Long-lived admin-generated patient login QR | Partial: no expiry field |
| `PatientSessionQR` | `patients/models.py` | `token_hash`, `expires_at`, `used_at`, `revoked_at` | FK `patient` | Short-lived patient-generated session QR | Working/partial: one-time and expiry checks exist |
| `PatientSession` | `patients/models.py` | `access_type`, `qr_code_value_snapshot`, `status`, `started_at`, `ended_at`, `expires_at` | FK `patient`, FK `pharmacist`, FK `pharmacy` | Pharmacist-patient access session | Partial: lifecycle mostly start/end; no automatic expiry job |
| `Pharmacy` | `pharmacies/models.py` | `name`, `address`, `latitude`, `longitude`, `is_contracted_with_organization`, `phone_number` | FK `owner_user`, FK `organization` | Pharmacy profile | Working |
| `PharmacistProfile` | `pharmacies/models.py` | `full_name`, `license_number`, `is_approved` | O2O `user`, FK `pharmacy` | Pharmacist details and approval mirror | Partial: approval duplicated with `User.approval_status` |
| `Prescription` | `prescriptions/models.py` | `doctor_name`, `doctor_specialty`, `diagnosis`, `status`, `prescribed_at`, `submitted_at`, `delivered_at`, `notes` | FK `patient`, FK `pharmacist`, FK `pharmacy`, FK nullable `session`, FK nullable `reused_from` | Prescription header | Partial: lifecycle fields exist, limited transition endpoints |
| `PrescriptionItem` | `prescriptions/models.py` | medication fields, image/audio/video files, price, quantity, transcription fields, transcript fields, `supporting_text`, `sign_status`, `is_confirmed` | FK `prescription` | Medication item and transcription/sign state | Partial: audio/gloss works through specific routes; sign video not generated |
| `PrescriptionAccessLog` | `prescriptions/models.py` | `access_type`, `timestamp` | FK `prescription`, FK nullable `accessed_by` | Audit access log | Working/partial: only some operations log |

## 4. API Endpoints

Base prefix is `/api/`.

| Method | Path | View/viewset | App/file | Auth | Role | Request body | Response body | Status |
|---|---|---|---|---|---|---|---|---|
| POST | `/api/auth/pharmacist/register/` | `AuthViewSet.pharmacist_register` | `accounts/views.py` | Public | None | pharmacist, pharmacy, password, OTP fields | detail, approval status, user, profile | Partial |
| POST | `/api/auth/register/request-otp/` | `AuthViewSet.register_request_otp` | `accounts/views.py` | Public | None | `role`, `phone_number`/`phone` | detail, expires, debug OTP in DEBUG | Partial |
| POST | `/api/auth/pharmacist/register/request-otp/` | `AuthViewSet.pharmacist_register_request_otp` | `accounts/views.py` | Public | None | phone | detail, expires, debug OTP in DEBUG | Partial |
| POST | `/api/auth/login/` | `AuthViewSet.login` | `accounts/views.py` | Public | None | email or phone, password | user/profile, access, refresh | Working |
| POST | `/api/auth/patient/self-register/` | `AuthViewSet.patient_self_register` | `accounts/views.py` | Public | None | patient fields, password, OTP | detail, approval status, user, profile | Partial |
| POST | `/api/auth/patient/register/` | `AuthViewSet.patient_register` | `accounts/views.py` | Public | None | same as self-register | same as self-register | Partial |
| POST | `/api/auth/patient/register/request-otp/` | `AuthViewSet.patient_register_request_otp` | `accounts/views.py` | Public | None | phone | detail, expires, debug OTP in DEBUG | Partial |
| POST | `/api/auth/patient/qr-login/` | `AuthViewSet.patient_qr_login` | `accounts/views.py` | Public | Patient QR | `qr_token` or `qr_code_value` + `pin` | user/profile, access, refresh | Partial |
| GET | `/api/admin/registration-requests/` | `AuthViewSet.registration_requests` | `accounts/views.py` | JWT | superuser/staff/org staff | None | pending user list | Working |
| POST | `/api/admin/users/<pk>/approve/` | `AuthViewSet.approve_user` | `accounts/views.py` | JWT | superuser/staff/org staff | none | detail, user | Working |
| POST | `/api/admin/users/<pk>/reject/` | `AuthViewSet.reject_user` | `accounts/views.py` | JWT | superuser/staff/org staff | optional `reason` | detail, user | Working |
| POST | `/api/auth/logout/` | `AuthViewSet.logout` | `accounts/views.py` | JWT | Any approved user | `refresh` | detail | Working |
| POST | `/api/auth/change-password/` | `AuthViewSet.change_password` | `accounts/views.py` | JWT | Any approved user | current/new/confirm password | detail | Working |
| POST | `/api/auth/refresh/` | `ApprovalAwareTokenRefreshView` | `accounts/jwt.py` | Public token | Approved account | `refresh` | access, maybe refresh | Working |
| GET | `/api/auth/me/` | `AuthViewSet.me` | `accounts/views.py` | JWT | Any approved user | None | user, profile | Working |
| GET | `/api/patients/enrollments/` | `PatientEnrollmentViewSet.list` | `patients/views.py` | JWT | Can manage patients | None | paginated enrollments | Working |
| POST | `/api/patients/enrollments/` | `PatientEnrollmentViewSet.create` | `patients/views.py` | JWT | Can manage patients | enrollment fields | enrollment | Working |
| GET | `/api/patients/enrollments/<id>/` | `PatientEnrollmentViewSet.retrieve` | `patients/views.py` | JWT | Can manage patients | None | enrollment | Working |
| PATCH | `/api/patients/enrollments/<id>/` | `PatientEnrollmentViewSet.partial_update` | `patients/views.py` | JWT | Can manage patients | enrollment fields | enrollment | Working |
| POST | `/api/patients/enrollments/<id>/create-account/` | `PatientEnrollmentViewSet.create_account` | `patients/views.py` | JWT | Can manage patients | email, password, phone, PIN | patient_id, user_id, QR | Working |
| POST | `/api/admin/patients/create-account/` | `AdminPatientAccountViewSet.create_account` | `patients/views.py` | JWT | Can manage patients | patient account/profile fields | user, profile, temporary password flag | Working |
| POST | `/api/admin/patients/<patient_id>/login-qr/` | `AdminPatientLoginQRViewSet.generate` | `patients/views.py` | JWT | Can manage patients | none | QR token payload | Working |
| POST | `/api/admin/patients/<patient_id>/login-qr/revoke/` | `AdminPatientLoginQRViewSet.revoke` | `patients/views.py` | JWT | Can manage patients | none | patient_id, inactive flag | Working |
| GET | `/api/patients/me/` | `PatientSelfProfileViewSet.retrieve` | `patients/views.py` | JWT | Patient | None | compatibility patient profile | Working |
| PATCH | `/api/patients/me/` | `PatientSelfProfileViewSet.partial_update` | `patients/views.py` | JWT | Patient | profile/medical fields | compatibility patient profile | Working |
| GET | `/api/patients/me/settings/` | `PatientSettingsViewSet.retrieve` | `patients/views.py` | JWT | Patient | None | settings | Working |
| PATCH | `/api/patients/me/settings/` | `PatientSettingsViewSet.partial_update` | `patients/views.py` | JWT | Patient | settings fields | settings | Working |
| POST | `/api/patients/me/session-qr/` | `PatientSessionQRViewSet.create` | `patients/views.py` | JWT | Patient | none | QR token, expiry | Working |
| GET | `/api/pharmacist/sessions/` | `PharmacistPatientSessionViewSet.list` | `patients/views.py` | JWT | Approved pharmacist | optional `status` query | sessions | Working |
| POST | `/api/pharmacist/sessions/start-by-qr/` | `PharmacistPatientSessionViewSet.start_by_qr` | `patients/views.py` | JWT | Approved pharmacist | `qr_token`/`qr_payload` | session, patient, medical info, recent prescriptions | Working |
| POST | `/api/pharmacist/sessions/<session_id>/end/` | `PharmacistPatientSessionViewSet.end` | `patients/views.py` | JWT | Approved pharmacist | none | detail | Working |
| POST | `/api/patients/<pk>/generate-qr/` | `PatientManagementViewSet.generate_qr` | `patients/views.py` | JWT | Can manage patients | `regenerate` | QR value/status | Working |
| POST | `/api/patient-sessions/start-by-qr/` | `PatientSessionViewSet.start_by_qr` | `patients/views.py` | JWT | Approved pharmacist | `qr_code_value` | session, patient_summary | Partial |
| GET | `/api/pharmacies/` | `PharmacyViewSet.list` | `pharmacies/views.py` | JWT | Pharmacist or admin manager | None | paginated pharmacies | Working |
| POST | `/api/pharmacies/` | `PharmacyViewSet.create` | `pharmacies/views.py` | JWT | Can manage pharmacists | pharmacy fields | pharmacy | Working |
| GET | `/api/pharmacies/<id>/` | `PharmacyViewSet.retrieve` | `pharmacies/views.py` | JWT | Pharmacist or admin manager | None | pharmacy | Working |
| GET | `/api/pharmacies/contracted/` | `PharmacyViewSet.contracted` | `pharmacies/views.py` | JWT | Pharmacist/admin manager | None | contracted pharmacies | Working |
| GET | `/api/pharmacists/me/` | `PharmacistProfileViewSet.retrieve` | `pharmacies/views.py` | JWT | Pharmacist | None | pharmacist profile | Working |
| PATCH | `/api/pharmacists/me/` | `PharmacistProfileViewSet.partial_update` | `pharmacies/views.py` | JWT | Pharmacist | pharmacist/pharmacy fields | pharmacist profile | Working |
| GET | `/api/pharmacist/me/` | same as above | `pharmacies/views.py` | JWT | Pharmacist | None | pharmacist profile | Working |
| PATCH | `/api/pharmacist/me/` | same as above | `pharmacies/views.py` | JWT | Pharmacist | pharmacist/pharmacy fields | pharmacist profile | Working |
| GET | `/api/pharmacist/me/pharmacy/` | `PharmacistPharmacyViewSet.retrieve` | `pharmacies/views.py` | JWT | Pharmacist | None | compatibility pharmacy | Working |
| PATCH | `/api/pharmacist/me/pharmacy/` | `PharmacistPharmacyViewSet.partial_update` | `pharmacies/views.py` | JWT | Pharmacist | pharmacy fields | compatibility pharmacy | Working |
| GET | `/api/prescriptions/<id>/` | `PrescriptionViewSet.retrieve` | `prescriptions/views.py` | JWT | Patient/pharmacist/admin scoped | None | prescription | Working |
| POST | `/api/prescriptions/` | `PrescriptionViewSet.create` | `prescriptions/views.py` | JWT | Approved pharmacist | body ignored | error directing to pharmacist endpoint | Partial |
| POST | `/api/prescriptions/<id>/items/` | `PrescriptionViewSet.add_item` | `prescriptions/views.py` | JWT | Prescription pharmacist | item fields | item | Partial |
| POST | `/api/prescriptions/<id>/confirm/` | `PrescriptionViewSet.confirm` | `prescriptions/views.py` | JWT | Prescription pharmacist | status confirm | prescription | Partial |
| PATCH | `/api/prescriptions/items/<id>/` | `PrescriptionItemViewSet.partial_update` | `prescriptions/views.py` | JWT | Approved pharmacist | item update fields | item update response | Working |
| POST | `/api/prescriptions/items/<id>/transcribe/` | `PrescriptionItemViewSet.transcribe` | `prescriptions/views.py` | JWT | Approved pharmacist | `force` | item | Partial: placeholder backend unless configured |
| GET | `/api/patients/me/prescriptions/` | `PatientPrescriptionViewSet.list` | `prescriptions/views.py` | JWT | Patient | optional `include_drafts=true` | paginated prescriptions | Working |
| GET | `/api/patients/me/prescriptions/<id>/` | `PatientPrescriptionViewSet.retrieve` | `prescriptions/views.py` | JWT | Patient | None | prescription | Working |
| GET | `/api/pharmacist/prescriptions/` | `PharmacistPrescriptionViewSet.list` | `prescriptions/views.py` | JWT | Pharmacist | optional `status`, `patient_id` | prescriptions | Working |
| POST | `/api/pharmacist/prescriptions/` | `PharmacistPrescriptionViewSet.create` | `prescriptions/views.py` | JWT | Approved pharmacist | `session_id`, `patient_id`, doctor fields, items | prescription | Working |
| GET | `/api/pharmacist/prescriptions/<prescription_id>/` | `PharmacistPrescriptionViewSet.retrieve` | `prescriptions/views.py` | JWT | Pharmacist | None | prescription | Working |
| PATCH | `/api/pharmacist/prescriptions/<prescription_id>/` | `PharmacistPrescriptionViewSet.partial_update` | `prescriptions/views.py` | JWT | Approved pharmacist | doctor/diagnosis/notes | prescription | Working |
| POST | `/api/pharmacist/prescriptions/<prescription_id>/items/` | `PharmacistPrescriptionViewSet.add_item` | `prescriptions/views.py` | JWT | Approved pharmacist | item text fields | item | Working |
| PATCH | `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/` | `PharmacistPrescriptionViewSet.update_item` | `prescriptions/views.py` | JWT | Approved pharmacist | item text fields | item | Working |
| DELETE | `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/` | `PharmacistPrescriptionViewSet.delete_item` | `prescriptions/views.py` | JWT | Approved pharmacist | none | empty 204 | Working |
| POST | `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/transcribe-audio/` | `PharmacistPrescriptionViewSet.transcribe_audio` | `prescriptions/views.py` | JWT | Approved pharmacist | multipart `audio` | transcript status/text | Partial |
| POST | `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/approve-transcript/` | `PharmacistPrescriptionViewSet.approve_transcript` | `prescriptions/views.py` | JWT | Approved pharmacist | `approved_instruction_text` | transcript fields | Working |
| POST | `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/generate-sign/` | `PharmacistPrescriptionViewSet.generate_sign` | `prescriptions/views.py` | JWT | Approved pharmacist | none | gloss text/status | Partial |
| POST | `/api/pharmacist/prescriptions/<prescription_id>/submit/` | `PharmacistPrescriptionViewSet.submit` | `prescriptions/views.py` | JWT | Approved pharmacist | none | detail, prescription | Working |
| POST | `/api/transcriptions/test/` | `TestTranscriptionView.post` | `transcriptions/views.py` | JWT | Approved pharmacist | multipart `audio` | provider/model/transcript or failure | Partial |

## 5. Authentication and Permissions

| Item | Status | Files involved | Issues found |
|---|---|---|---|
| Register | Partial | `accounts/views.py`, `accounts/serializers.py`, `pharmacies/serializers.py`, `patients/services.py` | Patient and pharmacist registration exist and both create pending accounts. Production OTP delivery is missing. |
| Login | Working | `accounts/views.py`, `accounts/serializers.py` | Blocks pending/rejected accounts. Uses email or phone. |
| OTP | Partial | `accounts/models.py`, `accounts/services.py`, `accounts/serializers.py` | Stored securely as password hash, expiry/attempts enforced. Delivery only logs/prints in DEBUG; production provider is not configured. |
| JWT | Working | `accounts/views.py`, `accounts/authentication.py`, `accounts/jwt.py`, `pharmasign/settings.py` | Approval-aware auth enforces `approval_status` on authenticated requests. |
| Refresh token | Working | `accounts/jwt.py`, `accounts/urls.py` | Refresh checks user approval. `SIMPLE_JWT.BLACKLIST_AFTER_ROTATION` is not set, so rotated old refresh tokens are not blacklisted unless default changes. |
| Role checks | Working/partial | `common/permissions.py`, app views | Patient/pharmacist/admin role permissions exist. Some endpoints use `IsPharmacistRole` then manual approval checks instead of `IsApprovedPharmacistRole`, creating inconsistency. |
| Pharmacist approval checks | Partial | `accounts/views.py`, `common/permissions.py`, `accounts/authentication.py`, `pharmacies/models.py` | Both `User.approval_status` and `PharmacistProfile.is_approved` exist. Auth blocks by user approval; some views also check profile approval. Duplication can drift. |
| Protected routes | Working | `pharmasign/settings.py`, all app views | Default is authenticated. Public auth endpoints explicitly use `AllowAny`. |

## 6. Core Backend Features

| Feature | Current status | Files involved | What works | What is missing | Priority |
|---|---|---|---|---|---|
| Patient account flow | Partial | `accounts/serializers.py`, `accounts/views.py`, `patients/services.py` | OTP request, self-register, pending user/profile/medical info/QR creation | Production OTP delivery; approval UX/API consistency; national ID persistence | High |
| Pharmacist account flow | Partial | `pharmacies/serializers.py`, `accounts/views.py` | OTP request, register with pharmacy/profile, pending approval | Production OTP delivery; license verification; organization assignment rules | High |
| Pharmacist approval | Partial | `accounts/views.py`, `common/permissions.py`, `pharmacies/models.py` | Approve/reject endpoints update user and pharmacist profile; reject blacklists outstanding tokens | Unified single approval source; admin/staff management API | High |
| Patient profile | Working | `patients/models.py`, `patients/serializers.py`, `patients/views.py` | Retrieve/update self profile and medical info | Real `national_id`; profile ownership edge-case handling if missing profile | Medium |
| Pharmacist profile | Working | `pharmacies/models.py`, `pharmacies/serializers.py`, `pharmacies/views.py` | Retrieve/update self profile | Approval state consistency | Medium |
| Pharmacy profile | Working | `pharmacies/models.py`, `pharmacies/serializers.py`, `pharmacies/views.py` | Retrieve/update pharmacist pharmacy; admin create/list | Contract/organization workflow incomplete | Medium |
| Prescription creation | Partial | `prescriptions/views.py`, `prescriptions/serializers.py` | Pharmacist can create draft from active session | General `/prescriptions/` create intentionally unusable; no patient-created prescriptions | High |
| Prescription listing | Working | `prescriptions/views.py` | Patient and pharmacist listing endpoints exist | Admin listing is only through generic router retrieve/create surface, no explicit list on `PrescriptionViewSet` | Medium |
| Prescription details | Working | `prescriptions/views.py`, `prescriptions/serializers.py` | Scoped retrieve and access logging | Safe serializer hides some item fields for patient/general views | Low |
| Prescription status updates | Partial | `prescriptions/views.py`, `common/choices.py` | Draft submit, confirm exist | No cancel/deliver/archive endpoints; `delivered_at` unused | High |
| QR token generation | Working/partial | `patients/services.py`, `patients/views.py` | Patient static QR, admin login QR, patient session QR | Static QR has no expiry; login QR has no expiry | High |
| QR token validation | Working/partial | `accounts/serializers.py`, `patients/serializers.py` | Hash-based login/session token lookup, revocation/use checks | Static QR endpoint accepts raw `qr_code_value`; PIN only used by QR-login compatibility path | High |
| QR token expiry | Partial | `patients/models.py`, `patients/services.py`, `patients/serializers.py` | Session QR expires after 300s | Login QR/static QR do not expire; no cleanup job | High |
| Session creation | Working | `patients/views.py`, `patients/serializers.py` | Approved pharmacist starts session from session QR or static QR route | Duplicate start routes with different request/response contracts | Medium |
| Session lifecycle | Partial | `patients/views.py`, `patients/models.py` | Active session reuse and explicit end endpoint | No automatic expiration transition; no cancel endpoint | Medium |
| Audio upload | Partial | `common/uploads.py`, `transcriptions/validators.py`, `prescriptions/views.py` | Size/extension/content-type validation; multipart endpoint saves audio | Two validators with overlapping allowed lists; max size differs by endpoint | Medium |
| Audio transcription using Whisper/Groq | Missing | `transcriptions/services.py`, `prescriptions/transcription.py` | Gemini transcription exists | Whisper/Groq are not implemented | High if frontend expects Whisper/Groq |
| Saving transcription text | Working | `prescriptions/views.py`, `prescriptions/models.py` | Raw and edited transcripts saved on `PrescriptionItem` | Standalone `/transcriptions/test/` does not save, by design | Medium |
| Gloss generation | Partial | `prescriptions/services.py`, `prescriptions/views.py` | Gemini generates gloss into `supporting_text`; updates `sign_status` | No sign video generation; prompt text appears mojibake in source | High |
| Error handling format | Partial | DRF defaults, app views | Mostly uses `{"detail": ...}` or field errors | No global standardized error envelope; some provider errors differ | Medium |
| Media upload handling | Partial | `settings.py`, `common/uploads.py`, `prescriptions/models.py` | Media root/url configured, validators, dev media serving | Production media serving/storage not configured | High |
| CORS / production settings / environment variables | Partial | `pharmasign/settings.py`, `.env.example` | CORS origins configurable; DB can switch PostgreSQL/SQLite | `DEBUG` defaults true; `.env.example` uses `JWT_ACCESS_TOKEN_LIFETIME=5h` and `JWT_REFRESH_TOKEN_LIFETIME=7d`, but settings cast these as integers | Critical |

## 7. Missing Backend Work

| Priority | Missing item | Why it is needed | Exact files likely needing changes | Suggested API contract | Notes |
|---|---|---|---|---|---|
| Critical | Fix JWT env contract | Current `.env.example` values like `5h`/`7d` will fail integer casting | `.env.example`, `pharmasign/settings.py` | Use integer env names like `JWT_ACCESS_TOKEN_LIFETIME_HOURS=5`, `JWT_REFRESH_TOKEN_LIFETIME_DAYS=7` or parse duration strings | Blocks clean setup from example env. |
| Critical | Configure production secrets/settings | Avoid insecure defaults in production | `pharmasign/settings.py`, deployment env | Require `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, CORS, DB, media storage | DEBUG currently defaults true. |
| High | Production OTP provider | Registration cannot work outside DEBUG without OTP delivery | `accounts/services.py`, settings/env | `POST /api/auth/*/request-otp/ -> {detail, expires_in_seconds}` unchanged | Add WhatsApp/SMS provider implementation and error handling. |
| High | Decide approval source of truth | Prevent `User.approval_status` and `PharmacistProfile.is_approved` drift | `accounts/views.py`, `accounts/authentication.py`, `common/permissions.py`, `pharmacies/models.py` | Keep same approval endpoints | Prefer deriving pharmacist approval from user approval or strict sync. |
| High | Add missing prescription lifecycle endpoints | Frontend may need cancel/deliver/archive/status updates | `prescriptions/views.py`, `prescriptions/serializers.py`, `prescriptions/urls.py` | `POST /api/pharmacist/prescriptions/<id>/cancel/`, `/deliver/`, `/archive/` | Use explicit transitions and timestamps. |
| High | Clarify transcription provider | User context mentions Whisper/Groq, code uses Gemini | `transcriptions/services.py`, settings, `requirements.txt` | Keep `POST .../transcribe-audio/`, expose provider/model in response | Add provider selection or update frontend contract to Gemini. |
| High | Complete sign-language output | Frontend likely expects sign-language asset, not only gloss text | `prescriptions/services.py`, `prescriptions/views.py`, `prescriptions/models.py` | `POST .../generate-sign/ -> {gloss_text, sign_status, video_url}` | Current `video_url` is always null. |
| High | Organization REST management | Organization staff permissions depend on profiles not creatable via REST | New `organizations/urls.py`, `organizations/views.py`, serializers | `/api/organizations/`, `/api/organizations/staff/` | Currently admin-only model management. |
| Medium | Standardize error format | Frontend integration is easier with one envelope | Project-level DRF exception handler | `{detail, code, fields}` | Current responses mix detail, field errors, and provider-specific payloads. |
| Medium | Session expiry handling | Prevent stale active sessions | `patients/models.py`, `patients/views.py`, scheduled task/management command | `POST /api/pharmacist/sessions/<id>/end/` plus background expiry | Code checks expiry on creation, but does not transition old sessions. |
| Medium | Consolidate duplicate session QR flows | Avoid frontend confusion | `patients/urls.py`, `patients/views.py` | Prefer `/api/pharmacist/sessions/start-by-qr/` with token only | Static QR flow has different security and response shape. |
| Medium | Persist national ID if needed | Serializers expose blank `national_id` but model has no field | `patients/models.py`, migrations, serializers | Include `national_id` in patient profile APIs | Current field is compatibility placeholder. |
| Medium | Media storage for production | Uploaded audio/image/video needs durable serving | `settings.py`, deployment config | Existing media URLs can stay | Consider S3-compatible storage or protected media views. |
| Low | Add API docs/schema | Frontend needs exact contracts | settings, urls | `/api/schema/`, `/api/docs/` | No OpenAPI generator found. |

## 8. Backend Blockers

| Blocker | Why it blocks frontend integration |
|---|---|
| `.env.example` JWT lifetimes conflict with settings casts | A developer using the example env may fail at startup because `5h`/`7d` are cast to `int`. |
| Production OTP delivery is not implemented | Patient/pharmacist registration requires OTP, but non-DEBUG delivery only logs that no provider is configured. |
| Whisper/Groq are not implemented | If frontend expects Whisper/Groq specifically, current backend only supports Gemini for real transcription. |
| Sign endpoint returns no video asset | `generate-sign` produces gloss text and always returns `video_url: None`; frontend sign-language playback cannot be integrated from backend output. |
| Organization/staff management has no REST endpoints | Approval and scoping depend on organization staff profiles, but they can only be managed via admin/code from current URLs. |
| Response strings contain mojibake Arabic in several files | Approval and gloss prompt text may display corrupted Arabic to clients and providers. |
| No standardized error response contract | Frontend must handle several response shapes. |

## 9. Recommended Backend Implementation Order

1. Fix environment/settings startup risks: JWT lifetime parsing, DEBUG default, required production secrets, CORS/hosts.
2. Fix mojibake Arabic strings in auth/transcription/gloss prompt files.
3. Add production OTP delivery or a clearly mocked provider contract for development/staging.
4. Normalize approval state so user approval and pharmacist profile approval cannot drift.
5. Add organization and staff REST endpoints or document that Django admin is required.
6. Consolidate QR/session flows around one secure short-lived token path.
7. Complete prescription lifecycle endpoints for cancel/confirm/submit/deliver/archive as required by product flow.
8. Choose and implement the transcription provider contract: Gemini-only, Whisper, Groq, or configurable provider.
9. Complete sign-language output contract: gloss-only vs video/media generation, with persisted provider/model/error metadata.
10. Add a project-level DRF exception handler and publish OpenAPI/API docs.
11. Add focused tests for auth approval, OTP, QR/session expiry, prescription creation, transcription failure, and gloss generation failure.

## 10. Unclear Items

| Item | Why unclear |
|---|---|
| Whether patients should require organization approval | Patient self-register sets `approval_status=pending`; code supports approval, but product rule is not documented in code. |
| Whether patients should have a real `national_id` | Serializers accept/return it as compatibility data, but no model field exists. |
| Whether static patient QR should remain supported | Code supports both static `qr_code_value` and short-lived session QR tokens. Security intent is unclear. |
| Whether Whisper/Groq are required | User context mentions Whisper/Groq, but code implements Gemini. |
| Whether sign-language means gloss text only or generated video | Models include `sign_language_video`, but generation currently writes gloss to `supporting_text` and returns no video. |
| Whether organization management is intentionally admin-only | Models/admin exist, but no REST URL exists. |
| Whether pharmacy contracts are manually managed | Model fields exist, but no dedicated contract workflow endpoint exists. |
| Whether access logs must cover every prescription operation | Access logs exist but are not used consistently for every endpoint. |
| Whether tests pass | Static code audit only; no tests were run for this report. |
