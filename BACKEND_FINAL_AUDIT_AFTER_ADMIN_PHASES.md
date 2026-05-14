# Backend Final Audit After Admin Phases

Audit date: 2026-05-14  
Scope: backend only, current repository files under `c:\Users\alaan\Desktop\PharmaSign_BackEnd`.

## 1. Executive Summary

The backend is a Django 5.1 / Django REST Framework API for PharmaSign. It now supports patient/pharmacist registration with approval-aware JWT login, patient QR workflows, pharmacist prescription workflows, admin dashboard APIs for auth, stats, patients, QR, pharmacies, pharmacists, approval requests, prescription logs, and a partial sign-quality monitoring API.

Admin dashboard backend work completed from the original `ADMIN_BACKEND_DISCOVERY.md`:

- Phase A: admin auth, admin me, admin logout, dashboard stats.
- Phase B: admin patients and QR APIs.
- Phase C: admin pharmacies and pharmacists APIs.
- Phase D: admin approval requests APIs.
- Phase E: admin prescription logs APIs.

Prescription pricing/billing has also been added:

- `PrescriptionItem.unit_price`, `PrescriptionItem.quantity`, `PrescriptionItem.line_total`.
- `Prescription.total_price`, `Prescription.currency`.
- Backend calculates `line_total` and `total_price`.
- Pharmacist item create requires `unit_price` or legacy `price`.
- `quantity` is optional and defaults to `1.00`.
- Totals are read-only in serializers.

Still missing or partial:

- Password reset / account recovery.
- Reports summary endpoint.
- Admin settings / organization profile endpoint.
- Admin sign-quality frontend contract endpoint `/api/admin/sign-quality-records/`.
- Full frontend integration is not implemented in backend files and cannot be confirmed from current backend files.

Risk / product decisions:

- Password reset is missing and is a production account-recovery blocker.
- Sign quality lacks reviewer notes and per-medicine quality status fields.
- Reports should decide whether to include revenue metrics such as `total_sales`.
- City/region fields do not exist as structured fields for patients or pharmacies.

| Area | Status | Notes |
|---|---|---|
| Auth/Login | Complete | `/api/auth/login/`, `/api/auth/refresh/`, `/api/auth/logout/`, `/api/auth/me/`, approval-aware JWT. |
| Admin Auth | Complete | `/api/admin/auth/login/`, `/me/`, `/logout/` in `accounts/urls.py` and `AuthViewSet`. |
| Admin Dashboard Stats | Complete | `/api/admin/dashboard/stats/`; no sales metrics yet. |
| Patients Admin | Partial | List/detail/update/delete/generate QR exist; POST `/api/admin/patients/` does not exist, but `/api/admin/patients/create-account/` exists. |
| Patient QR | Complete | Admin QR list/detail/regenerate/disable/reactivate uses `PatientProfile.qr_code_value`. Login QR endpoints also exist separately. |
| Pharmacies Admin | Complete | CRUD-style list/create/detail/patch/delete exists; delete is blocked when risky relations exist. |
| Pharmacists Admin | Complete | CRUD-style list/create/detail/patch/delete exists; delete deactivates user and unapproves profile. |
| Approval Requests | Complete | User-backed approval request list/detail/approve/reject exists. |
| Prescription Logs | Complete | Admin list/detail exists with items and safe access logs. |
| Prescription Pricing | Complete | Required price, optional quantity default `1`, backend totals. |
| Sign Quality Monitoring | Partial | `/api/admin/sign-quality-reports/` exists; frontend-proposed `/sign-quality-records/` and reviewer notes do not. |
| Reports | Missing | No `/api/admin/reports/summary/` found. |
| Settings/Organization | Missing | Organization model/serializer exists; no admin settings endpoint found. |
| Password Reset / Account Recovery | Missing | No forgot/reset-password endpoints found. |
| Frontend Admin Integration | Partial | Backend endpoints exist; frontend integration cannot be confirmed from current backend files. |

## 2. Current Project Architecture

### Django apps

Configured in `pharmasign/settings.py`:

- Django apps: `admin`, `auth`, `contenttypes`, `sessions`, `messages`, `staticfiles`.
- Third-party apps: `corsheaders`, `rest_framework`, `rest_framework_simplejwt`, `rest_framework_simplejwt.token_blacklist`.
- Local apps: `common`, `accounts`, `organizations`, `patients`, `pharmacies`, `prescriptions`, `transcriptions`.

### URL routing

- Root URLs: `pharmasign/urls.py`
  - `/admin/` -> Django admin.
  - `/api/` -> `pharmasign/api_urls.py`.
  - media served only when `settings.DEBUG` is true.
- API includes: `pharmasign/api_urls.py`
  - `accounts.urls`
  - `patients.urls`
  - `pharmacies.urls`
  - `prescriptions.urls`
  - `transcriptions.urls` under `/api/transcriptions/`

### Authentication configuration

`pharmasign/settings.py`:

- `AUTH_USER_MODEL = "accounts.User"`
- DRF auth class: `accounts.authentication.ApprovalAwareJWTAuthentication`
- Default permission: `IsAuthenticated`
- JWT refresh endpoint uses `accounts.jwt.ApprovalAwareTokenRefreshView`.

### Permission configuration

Important permissions in `common/permissions.py`:

- `IsAdminRole`
- `IsPharmacistRole`
- `IsPatientRole`
- `CanManagePatients`
- `CanManagePharmacists`
- `IsAdminOrPharmacistRole`
- `IsApprovedPharmacistRole`

Organization scoping is implemented inside several viewsets by inspecting `request.user.organization_staff_profile`.

### Pagination configuration

`pharmasign/settings.py`:

- Default pagination: `rest_framework.pagination.PageNumberPagination`
- Default page size: `20`

Admin list endpoints use local `AdminPageNumberPagination` classes with:

- `page_size_query_param = "page_size"`
- `max_page_size = 100`

Defined in:

- `accounts/views.py`
- `patients/views.py`
- `pharmacies/views.py`
- `prescriptions/views.py`

### Static/media configuration

`pharmasign/settings.py`:

- `STATIC_URL = "/static/"`
- `STATIC_ROOT = BASE_DIR / "staticfiles"`
- `MEDIA_URL = config("MEDIA_URL", "/media/")`
- `MEDIA_ROOT = BASE_DIR / config("MEDIA_ROOT", "media")`
- upload permission settings are configured.
- image/audio/video extension, content-type, and size allowlists are configured.

### Environment variables

Relevant settings in `pharmasign/settings.py`:

- `SECRET_KEY`
- `PHARMASIGN_ENV`
- `DEBUG`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `MEDIA_URL`, `MEDIA_ROOT`
- `PHARMASIGN_MAX_IMAGE_UPLOAD_BYTES`
- `PHARMASIGN_MAX_AUDIO_UPLOAD_BYTES`
- `PHARMASIGN_MAX_VIDEO_UPLOAD_BYTES`
- `PHARMASIGN_ALLOWED_*`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GEMINI_SIGN_MODEL`
- `MAX_AUDIO_UPLOAD_SIZE_MB`
- `OTP_DELIVERY_PROVIDER_CONFIGURED`
- `JWT_ACCESS_TOKEN_LIFETIME`
- `JWT_REFRESH_TOKEN_LIFETIME`

### Important files

| Category | Files |
|---|---|
| Settings/root routing | `pharmasign/settings.py`, `pharmasign/urls.py`, `pharmasign/api_urls.py` |
| Auth | `accounts/models.py`, `accounts/serializers.py`, `accounts/views.py`, `accounts/urls.py`, `accounts/authentication.py`, `accounts/jwt.py`, `accounts/services.py`, `accounts/tests.py` |
| Patients/QR | `patients/models.py`, `patients/serializers.py`, `patients/views.py`, `patients/urls.py`, `patients/services.py`, `patients/tests.py` |
| Pharmacies/pharmacists | `pharmacies/models.py`, `pharmacies/serializers.py`, `pharmacies/views.py`, `pharmacies/urls.py`, `pharmacies/tests.py` |
| Prescriptions/pricing/sign quality | `prescriptions/models.py`, `prescriptions/serializers.py`, `prescriptions/views.py`, `prescriptions/urls.py`, `prescriptions/services.py`, `prescriptions/transcription.py`, `prescriptions/tests.py` |
| Transcription provider | `transcriptions/views.py`, `transcriptions/services.py`, `transcriptions/validators.py`, `transcriptions/urls.py`, `transcriptions/tests.py` |
| Organizations | `organizations/models.py`, `organizations/serializers.py`, `organizations/admin.py` |
| Shared | `common/choices.py`, `common/permissions.py`, `common/uploads.py`, `common/api_errors.py`, `common/utils.py` |

## 3. Models and Database State

### accounts

| Model | File path | Important fields | Relationships | Feature uses | Recent fields | Missing frontend/admin fields |
|---|---|---|---|---|---|---|
| `User` | `accounts/models.py` | `email`, `phone_number`, `role`, `is_staff`, `is_active`, `is_verified`, `approval_status`, `approved_at`, `approved_by`, `rejection_reason` | `approved_by` self FK; reverse one-to-one from patient/pharmacist/staff profiles | Login, admin auth, approvals, role checks | Approval fields from `accounts/migrations/0005...` | Password reset token fields missing. |
| `PhoneOTP` | `accounts/models.py` | `phone_number`, `purpose`, `code_hash`, `expires_at`, `used_at`, `attempts`, `max_attempts`, `user` | FK to `User` nullable | Registration OTP | Added in `accounts/migrations/0004_phoneotp.py` | Purpose choices only registration, no password reset purpose. |

### patients

| Model | File path | Important fields | Relationships | Feature uses | Recent fields | Missing frontend/admin fields |
|---|---|---|---|---|---|---|
| `PatientProfile` | `patients/models.py` | `user`, `organization`, `full_name`, `phone_number`, `birth_date`, `gender`, `address`, `hearing_disability_level`, `is_self_registered`, `qr_code_value`, `qr_is_active`, `record_access_pin_hash` | one-to-one `User`, FK `Organization` | Patient admin, profile, QR, sessions, prescriptions | QR and PIN fields exist | No structured `city`, `region`, `diagnosis`, `current_medications`. |
| `PatientMedicalInfo` | `patients/models.py` | `patient`, `blood_type`, `chronic_conditions`, `allergies`, `is_pregnant`, `is_breastfeeding`, `notes` | one-to-one `PatientProfile` | Patient medical info, admin patient detail | `blood_type` in `patients/migrations/0006...` | No separate diagnosis/current medications; `notes` reused for regular medications in some serializers. |
| `PatientLoginQR` | `patients/models.py` | `patient`, `token_hash`, `is_active`, `revoked_at`, `created_by` | FK `PatientProfile`, FK `User` | Patient QR login token | `patients/migrations/0004_patientloginqr.py` | Raw token not stored by design. |
| `PatientSessionQR` | `patients/models.py` | `patient`, `token_hash`, `expires_at`, `used_at`, `revoked_at` | FK `PatientProfile` | One-time patient session QR | `patients/migrations/0005...` | Raw token not stored by design. |
| `PatientSession` | `patients/models.py` | `patient`, `pharmacist`, `pharmacy`, `access_type`, `qr_code_value_snapshot`, `status`, `started_at`, `ended_at`, `expires_at` | FK patient/pharmacist/pharmacy | Pharmacist patient session, prescription creation validation | `expires_at` added in `patients/migrations/0005...` | None for current workflow. |
| `PatientEnrollment` | `patients/models.py` | enrollment identity fields, org, linked patient profile, notes, created_by | FK organization/user, one-to-one patient profile | Legacy/admin enrollment account creation | Initial | Separate from Phase B admin patients. |
| `PatientSettings` | `patients/models.py` | `notifications_enabled`, `prescription_reminders`, `dark_mode`, `use_biometrics` | one-to-one patient | Patient self settings | `patients/migrations/0003_patientsettings.py` | Admin organization settings missing. |

### pharmacies

| Model | File path | Important fields | Relationships | Feature uses | Recent fields | Missing frontend/admin fields |
|---|---|---|---|---|---|---|
| `Pharmacy` | `pharmacies/models.py` | `name`, `owner_user`, `address`, `latitude`, `longitude`, `is_contracted_with_organization`, `organization`, `phone_number` | FK owner user, FK organization | Admin pharmacies, pharmacist registration, patient/pharmacist pharmacy lists | Initial | No structured `city`, `region`, `license_number`, `status`, `notes`. |
| `PharmacistProfile` | `pharmacies/models.py` | `user`, `pharmacy`, `full_name`, `license_number`, `is_approved` | one-to-one user, FK pharmacy | Pharmacist auth/profile/admin, prescription ownership | Initial | No `notes` field. |

### prescriptions

| Model | File path | Important fields | Relationships | Feature uses | Recent fields | Missing frontend/admin fields |
|---|---|---|---|---|---|---|
| `Prescription` | `prescriptions/models.py` | `patient`, `pharmacist`, `pharmacy`, `session`, `doctor_name`, `doctor_specialty`, `diagnosis`, `status`, `prescribed_at`, `submitted_at`, `delivered_at`, `notes`, `total_price`, `currency`, `reused_from` | FK patient/pharmacist/pharmacy/session/self | Prescription workflow, admin logs, patient history | `total_price`, `currency` in `prescriptions/migrations/0005...` | No payment status/invoice fields. |
| `PrescriptionItem` | `prescriptions/models.py` | `prescription`, medicine fields, `price`, `unit_price`, `quantity`, `line_total`, media/transcription/sign fields, `is_confirmed` | FK prescription | Medicine items, transcription, sign/gloss, pricing | `unit_price`, decimal `quantity`, `line_total` in `0005` | `price` retained as legacy alias; no explicit item payment status. |
| `SignQualityReport` | `prescriptions/models.py` | `patient`, `prescription`, `prescription_item`, `medicine_name`, `approved_instruction_text`, `report_type`, `status` | FK patient/prescription/item | Patient reports unclear sign, admin sign quality reports | `prescriptions/migrations/0004_signqualityreport.py` | No `reviewer_notes`, no per-medicine quality status field beyond report status. |
| `PrescriptionAccessLog` | `prescriptions/models.py` | `prescription`, `accessed_by`, `access_type`, `timestamp` | FK prescription/user | Audit log exposure in admin prescription detail | Initial | No IP/user agent. |

### organizations

| Model | File path | Important fields | Relationships | Feature uses | Recent fields | Missing frontend/admin fields |
|---|---|---|---|---|---|---|
| `Organization` | `organizations/models.py` | `name`, `description`, `phone`, `address` | reverse staff/patients/pharmacies | Admin scoping, org profile candidate | Initial | No logo, email, website, settings flags. |
| `OrganizationStaffProfile` | `organizations/models.py` | `user`, `organization`, `job_title`, `can_manage_patients`, `can_manage_pharmacists` | one-to-one user, FK organization | Admin profile and scoped permissions | Initial | No granular permissions beyond two booleans. |

### Migration summary

| Migration file | App | Purpose | Applied/required notes |
|---|---|---|---|
| `accounts/migrations/0001_initial.py` | accounts | Initial custom user | Must be applied. |
| `accounts/migrations/0002_user_is_staff_alter_user_role.py` | accounts | Staff/role adjustments | Must be applied. |
| `accounts/migrations/0003_alter_user_email_alter_user_phone_number.py` | accounts | Email/phone adjustments | Must be applied. |
| `accounts/migrations/0004_phoneotp.py` | accounts | Registration OTP model | Must be applied. |
| `accounts/migrations/0005_user_approval_status_user_approved_at_and_more.py` | accounts | Approval workflow fields | Must be applied for approval-aware auth. |
| `organizations/migrations/0001_initial.py` | organizations | Organization/staff profile | Must be applied for org scoping. |
| `patients/migrations/0001_initial.py` | patients | Patient profile/enrollment/medical info | Must be applied. |
| `patients/migrations/0002_patientsession.py` | patients | Patient session | Must be applied for pharmacist sessions. |
| `patients/migrations/0003_patientsettings.py` | patients | Patient settings | Must be applied for `/patients/me/settings/`. |
| `patients/migrations/0004_patientloginqr.py` | patients | Patient login QR | Must be applied for QR login token support. |
| `patients/migrations/0005_patientsessionqr_patientsession_expires_at_and_more.py` | patients | Session QR and session expiry | Must be applied for one-time session QR. |
| `patients/migrations/0006_patientmedicalinfo_blood_type.py` | patients | Blood type | Must be applied for medical info field. |
| `pharmacies/migrations/0001_initial.py` | pharmacies | Pharmacy/pharmacist models | Must be applied. |
| `prescriptions/migrations/0001_initial.py` | prescriptions | Prescription/item/access log | Must be applied. |
| `prescriptions/migrations/0002_prescriptionitem_transcription_completed_at_and_more.py` | prescriptions | Transcription/sign fields | Must be applied. |
| `prescriptions/migrations/0003_prescription_diagnosis_prescription_session_and_more.py` | prescriptions | Diagnosis/session/status fields | Must be applied. |
| `prescriptions/migrations/0004_signqualityreport.py` | prescriptions | Sign quality reports | Must be applied for Phase F base. |
| `prescriptions/migrations/0005_prescription_currency_prescription_total_price_and_more.py` | prescriptions | Pricing/billing fields and backfill | Must be applied before pricing endpoints are used. |

Pricing migration specifically adds:

- `PrescriptionItem.unit_price`
- `PrescriptionItem.quantity` altered to `DecimalField(max_digits=12, decimal_places=2, default=1)`
- `PrescriptionItem.line_total`
- `Prescription.total_price`
- `Prescription.currency`

Whether these migrations are applied on production cannot be confirmed from current backend files.

## 4. Authentication and Authorization

### Existing auth flows

- Normal login: `AuthViewSet.login`, `/api/auth/login/`.
- Admin login: `AuthViewSet.admin_login`, `/api/admin/auth/login/`.
- Token refresh: `ApprovalAwareTokenRefreshView`, `/api/auth/refresh/`.
- Logout: `AuthViewSet.logout`, `/api/auth/logout/`; admin wrapper `/api/admin/auth/logout/`.
- Current user: `/api/auth/me/`; admin `/api/admin/auth/me/`.
- Change password: `/api/auth/change-password/`.
- Registration OTP: `/api/auth/register/request-otp/`, `/api/auth/patient/register/request-otp/`, `/api/auth/pharmacist/register/request-otp/`.
- Patient self-register: `/api/auth/patient/self-register/` and alias `/api/auth/patient/register/`.
- Pharmacist register: `/api/auth/pharmacist/register/`.
- Patient QR login: `/api/auth/patient/qr-login/`.
- Approval-aware JWT: `accounts/authentication.py` and `accounts/jwt.py` block pending/rejected non-staff users.

| Endpoint | Method | Purpose | Auth required | Who can access | Request body | Response |
|---|---:|---|---|---|---|---|
| `/api/auth/login/` | POST | Normal JWT login | No | Active users; pending/rejected blocked | `email` or `phone_number`/`phone`, `password` | `{user, profile, access, refresh}` |
| `/api/admin/auth/login/` | POST | Admin JWT login | No | `is_superuser` or `role=admin`; pending/rejected blocked | Same as normal login | `{user, profile, access, refresh}` |
| `/api/auth/refresh/` | POST | JWT refresh | No, refresh token supplied | Approved active users | `refresh` | `access`, rotated `refresh` if enabled |
| `/api/auth/logout/` | POST | Blacklist refresh token | Yes | Authenticated users | `refresh` | `{detail}` |
| `/api/admin/auth/logout/` | POST | Admin logout wrapper | Yes | Authenticated users; route itself does not re-check admin beyond JWT | `refresh` | Same as logout |
| `/api/auth/me/` | GET | Current user/profile | Yes | Authenticated approved users | None | `{user, profile}` |
| `/api/admin/auth/me/` | GET | Current admin/profile | Yes | Admin/superuser | None | `{user, profile}` |
| `/api/auth/change-password/` | POST | Change password | Yes | Authenticated users | `current_password`, `new_password`, `confirm_password` | `{detail}` |
| `/api/auth/register/request-otp/` | POST | Generic registration OTP | No | Public | `role`, `phone_number`/`phone` | `{detail, expires_in_seconds, debug_otp?}` |
| `/api/auth/patient/register/request-otp/` | POST | Patient OTP | No | Public | `phone_number`/`phone` | same |
| `/api/auth/pharmacist/register/request-otp/` | POST | Pharmacist OTP | No | Public | `phone_number`/`phone` | same |
| `/api/auth/patient/self-register/` | POST | Patient register | No | Public with valid OTP | phone/name/password/otp/profile fields | pending user/profile |
| `/api/auth/patient/register/` | POST | Alias for patient register | No | Public with valid OTP | same | same |
| `/api/auth/pharmacist/register/` | POST | Pharmacist register | No | Public with valid OTP | phone/name/password/pharmacy/license/otp | pending pharmacist/profile |
| `/api/auth/patient/qr-login/` | POST | QR login | No | Patient QR token or legacy QR+PIN | `qr_token` or `qr_code_value`+`pin` | JWT login response |

Clear answers:

- Password reset / forgot password is not implemented.
- Missing likely endpoints: `POST /api/auth/password-reset/request/`, `POST /api/auth/password-reset/confirm/`, optionally admin reset endpoints.
- OTP is registration-related only: `PhoneOTP.PURPOSE_CHOICES` includes patient/pharmacist registration only.
- Admin cannot reset patient/pharmacist password through a dedicated endpoint. Admin create endpoints may generate temporary passwords for new accounts only.
- Patient/pharmacist account recovery after forgotten password is missing.

## 5. Admin Backend APIs Implemented

All endpoints below are under `/api/`; admin namespace is `/api/admin/...`.

### Phase A - Admin Auth and Dashboard

| Endpoint | Method | View/Class | Serializer | Permission | Query params | Request body | Response shape | Status |
|---|---:|---|---|---|---|---|---|---|
| `/api/admin/auth/login/` | POST | `accounts.views.AuthViewSet.admin_login` | `LoginSerializer`, `AdminAuthMeSerializer` | `AllowAny`, then admin role check | None | login credentials | user/profile/access/refresh | Complete |
| `/api/admin/auth/me/` | GET | `AuthViewSet.admin_me` | `AdminAuthMeSerializer` | `IsAuthenticated`, admin role check | None | None | user/profile | Complete |
| `/api/admin/auth/logout/` | POST | `AuthViewSet.admin_logout` | `LogoutSerializer` | `IsAuthenticated` | None | `refresh` | `{detail}` | Complete |
| `/api/admin/dashboard/stats/` | GET | `AuthViewSet.admin_dashboard_stats` | manual payload | `IsAuthenticated`, admin role check | None | None | counts/distributions/recent lists | Complete |

Dashboard org scoping uses `OrganizationStaffProfile` when present. `patients_by_city` is always `[]` because city/region are not structured fields.

### Phase B - Patients + QR

| Endpoint | Method | View/Class | Serializer | Permission | Query params | Request body | Response shape | Status |
|---|---:|---|---|---|---|---|---|---|
| `/api/admin/patients/` | GET | `patients.views.AdminPatientViewSet.list` | `AdminPatientSerializer` | `IsAuthenticated + CanManagePatients` | `search`, `gender`, `hearing_disability_level`, `approval_status`, `qr_is_active`, `page`, `page_size` | None | paginated patient rows | Complete |
| `/api/admin/patients/<id>/` | GET | `AdminPatientViewSet.retrieve` | `AdminPatientSerializer` | same | None | None | patient detail | Complete |
| `/api/admin/patients/<id>/` | PATCH | `AdminPatientViewSet.partial_update` | `AdminPatientUpdateSerializer` -> `AdminPatientSerializer` | same | None | safe profile/user/medical fields | updated patient detail | Complete |
| `/api/admin/patients/<id>/` | DELETE | `AdminPatientViewSet.destroy` | N/A | same | None | None | 204 | Complete |
| `/api/admin/patients/<id>/generate-qr/` | POST | `AdminPatientViewSet.generate_qr` | `GeneratePatientQRSerializer` | same | None | optional `regenerate` | patient QR payload | Complete |
| `/api/admin/qr-codes/` | GET | `AdminQRCodeViewSet.list` | `AdminPatientQRSerializer` | same | `page`, `page_size` | None | paginated QR rows | Complete |
| `/api/admin/qr-codes/<id>/` | GET | `AdminQRCodeViewSet.retrieve` | `AdminPatientQRSerializer` | same | None | None | QR detail | Complete |
| `/api/admin/qr-codes/<id>/regenerate/` | POST | `AdminQRCodeViewSet.regenerate` | `AdminPatientQRSerializer` | same | None | None | regenerated QR detail | Complete |
| `/api/admin/qr-codes/<id>/disable/` | POST | `AdminQRCodeViewSet.disable` | `AdminPatientQRSerializer` | same | None | None | disabled QR detail | Complete |
| `/api/admin/qr-codes/<id>/reactivate/` | POST | `AdminQRCodeViewSet.reactivate` | `AdminPatientQRSerializer` | same | None | None | active QR detail | Complete |
| `/api/admin/patients/create-account/` | POST | `AdminPatientAccountViewSet.create_account` | `AdminPatientCreateAccountSerializer` | same | None | patient account data | user/profile/temp password | Extra/Partial |
| `/api/admin/patients/<id>/login-qr/` | POST | `AdminPatientLoginQRViewSet.generate` | `GeneratePatientLoginQRSerializer` | same | None | none | raw one-time login token | Extra |
| `/api/admin/patients/<id>/login-qr/revoke/` | POST | `AdminPatientLoginQRViewSet.revoke` | `RevokePatientLoginQRSerializer` | same | None | none | revoke result | Extra |

Delete behavior: patient delete deactivates linked `User.is_active`, sets `PatientProfile.qr_is_active=False`, revokes active `PatientLoginQR`, and returns 204. It does not hard-delete records.

QR model decision: admin QR list uses `PatientProfile.qr_code_value`; QR id equals patient profile id. `PatientLoginQR.token_hash` is not exposed.

### Phase C - Pharmacies + Pharmacists

| Endpoint | Method | View/Class | Serializer | Permission | Query params | Request body | Response shape | Status |
|---|---:|---|---|---|---|---|---|---|
| `/api/admin/pharmacies/` | GET | `AdminPharmacyViewSet.list` | `AdminPharmacySerializer` | `IsAuthenticated + CanManagePharmacists` | `search`, `is_contracted_with_organization`, `page`, `page_size` | None | paginated pharmacies | Complete |
| `/api/admin/pharmacies/` | POST | `AdminPharmacyViewSet.create` | `AdminPharmacyWriteSerializer` -> `AdminPharmacySerializer` | same | None | existing pharmacy fields | pharmacy detail | Complete |
| `/api/admin/pharmacies/<id>/` | GET | `AdminPharmacyViewSet.retrieve` | `AdminPharmacySerializer` | same | None | None | pharmacy detail | Complete |
| `/api/admin/pharmacies/<id>/` | PATCH | `AdminPharmacyViewSet.partial_update` | `AdminPharmacyWriteSerializer` | same | None | existing pharmacy fields | pharmacy detail | Complete |
| `/api/admin/pharmacies/<id>/` | DELETE | `AdminPharmacyViewSet.destroy` | N/A | same | None | None | 204 or 400 | Complete |
| `/api/admin/pharmacists/` | GET | `AdminPharmacistViewSet.list` | `AdminPharmacistSerializer` | same | `search`, `pharmacy_id`, `approval_status`, `is_active`, `is_approved`, `page`, `page_size` | None | paginated pharmacists | Complete |
| `/api/admin/pharmacists/` | POST | `AdminPharmacistViewSet.create` | `AdminPharmacistWriteSerializer` -> `AdminPharmacistSerializer` | same | None | user/profile/pharmacy fields | pharmacist detail/temp password | Complete |
| `/api/admin/pharmacists/<id>/` | GET | `AdminPharmacistViewSet.retrieve` | `AdminPharmacistSerializer` | same | None | None | pharmacist detail | Complete |
| `/api/admin/pharmacists/<id>/` | PATCH | `AdminPharmacistViewSet.partial_update` | `AdminPharmacistWriteSerializer` | same | None | safe user/profile fields | pharmacist detail | Complete |
| `/api/admin/pharmacists/<id>/` | DELETE | `AdminPharmacistViewSet.destroy` | N/A | same | None | None | 204 | Complete |

Pharmacy delete behavior: hard-delete only when no related pharmacists, prescriptions, or patient sessions exist; otherwise returns 400 `pharmacy_delete_blocked`.

Pharmacist delete behavior: deactivates linked user and sets `PharmacistProfile.is_approved=False`; no hard delete.

### Phase D - Approval Requests

| Endpoint | Method | View/Class | Serializer | Permission | Query params | Request body | Response shape | Status |
|---|---:|---|---|---|---|---|---|---|
| `/api/admin/approval-requests/` | GET | `AuthViewSet.approval_requests` | `AdminApprovalRequestSerializer` | `IsAuthenticated` plus registration management check | `search`, `type`, `status`, `page`, `page_size` | None | paginated user-backed approval rows | Complete |
| `/api/admin/approval-requests/<id>/` | GET | `AuthViewSet.approval_request_detail` | `AdminApprovalRequestSerializer` | same | None | None | approval detail | Complete |
| `/api/admin/approval-requests/<id>/approve/` | POST | `AuthViewSet.approve_approval_request` | `AdminApprovalRequestSerializer` | same | None | None | detail + updated request | Complete |
| `/api/admin/approval-requests/<id>/reject/` | POST | `AuthViewSet.reject_approval_request` | `AdminApprovalRequestSerializer` | same | None | `reason` | detail + updated request | Complete |
| `/api/admin/registration-requests/` | GET | `AuthViewSet.registration_requests` | manual payload | same | None | None | pending users | Legacy preserved |
| `/api/admin/users/<id>/approve/` | POST | `AuthViewSet.approve_user` | manual payload | same | None | None | updated user summary | Legacy preserved |
| `/api/admin/users/<id>/reject/` | POST | `AuthViewSet.reject_user` | manual payload | same | None | `reason` | updated user summary | Legacy preserved |

Approval model decision: no `ApprovalRequest` model exists. `id` is `User.id`. Approve/reject updates `User.approval_status`; pharmacist profiles synchronize `is_approved`.

### Phase E - Prescription Logs

| Endpoint | Method | View/Class | Serializer | Permission | Query params | Request body | Response shape | Status |
|---|---:|---|---|---|---|---|---|---|
| `/api/admin/prescription-logs/` | GET | `AdminPrescriptionLogViewSet.list` | `AdminPrescriptionLogListSerializer` | `IsAuthenticated + CanManagePatients` | `search`, `status`, `pharmacy_id`, `pharmacist_id`, `patient_id`, `date_from`, `date_to`, `page`, `page_size` | None | paginated prescription logs | Complete |
| `/api/admin/prescription-logs/<id>/` | GET | `AdminPrescriptionLogViewSet.retrieve` | `AdminPrescriptionLogDetailSerializer` | same | None | None | prescription detail/items/access logs | Complete |

Prescription log date decision: annotated `log_date = Coalesce(submitted_at, prescribed_at, created_at)`. Serializer `date` returns same priority in Python.

Access logs exposure decision: detail includes safe `PrescriptionAccessLog` fields: `id`, `accessed_by` summary, `access_type`, `timestamp`.

### Existing partial sign-quality admin API

| Endpoint | Method | View/Class | Serializer | Permission | Query params | Request body | Response shape | Status |
|---|---:|---|---|---|---|---|---|---|
| `/api/admin/sign-quality-reports/` | GET | `AdminSignQualityReportViewSet.list` | `AdminSignQualityReportSerializer` | `IsAuthenticated + CanManagePatients` | `status`, `report_type`, `patient_id`, `prescription_id` | None | sign quality reports | Partial |
| `/api/admin/sign-quality-reports/<id>/` | GET | `AdminSignQualityReportViewSet.retrieve` | `AdminSignQualityReportSerializer` | same | None | None | report detail | Partial |
| `/api/admin/sign-quality-reports/<id>/` | PATCH | `AdminSignQualityReportViewSet.partial_update` | `AdminSignQualityReportUpdateSerializer` | same | None | `status` | updated report | Partial |

Frontend-proposed `/api/admin/sign-quality-records/` does not exist.

## 6. Prescription Workflow and Pricing

### Current prescription flow

1. Pharmacist starts or uses an active patient session.
2. Pharmacist creates prescription with `POST /api/pharmacist/prescriptions/`.
3. Pharmacist adds items with `POST /api/pharmacist/prescriptions/<id>/items/`.
4. Pharmacist may update/delete draft items.
5. Pharmacist uploads/transcribes audio with `POST /api/pharmacist/prescriptions/<id>/items/<item_id>/transcribe-audio/`.
6. Pharmacist approves transcript with `POST /api/pharmacist/prescriptions/<id>/items/<item_id>/approve-transcript/`.
7. Pharmacist generates sign/gloss with `POST /api/pharmacist/prescriptions/<id>/items/<item_id>/generate-sign/`.
8. Pharmacist submits/confirm/deliver/cancel/archive via status endpoints.
9. Patient views prescriptions under `/api/patients/me/prescriptions/`.
10. Admin views logs under `/api/admin/prescription-logs/`.

### Pricing behavior

Fields:

- `PrescriptionItem.price`: legacy decimal price retained.
- `PrescriptionItem.unit_price`: current billing unit price.
- `PrescriptionItem.quantity`: decimal billing quantity, default `1.00`.
- `PrescriptionItem.line_total`: backend-calculated.
- `Prescription.total_price`: backend-calculated aggregate.
- `Prescription.currency`: default `"SYP"`.

Validation:

- Create requires `unit_price` or legacy `price`.
- `quantity` is optional; if omitted it defaults to `1.00`.
- `unit_price >= 0`.
- provided `quantity > 0`.
- PATCH does not require `unit_price` or `quantity`; provided values are validated.
- Old requests without `unit_price` or `price` fail.

Calculation:

- `line_total = unit_price * quantity`, quantized to 2 decimals.
- `total_price = Sum(PrescriptionItem.line_total)`.
- totals recalculate in `PrescriptionItem.save()` and `PrescriptionItem.delete()`.
- frontend totals are not trusted.

Serializers accepting pricing:

- `PrescriptionItemCreateSerializer`
- `PrescriptionItemUpdateSerializer`
- `PharmacistPrescriptionItemInputSerializer`

Serializers returning pricing:

- `PrescriptionItemContractSerializer`
- `PrescriptionItemSerializer`
- `PharmacistPrescriptionItemSerializer`
- `PrescriptionSerializer`
- `PharmacistPrescriptionSerializer`
- `AdminPrescriptionLogListSerializer`
- `AdminPrescriptionLogItemSerializer`
- `AdminPrescriptionLogDetailSerializer`

Example valid item create without quantity:

```json
{
  "medicine_name": "Paracetamol",
  "dosage": "500mg",
  "frequency": "twice daily",
  "duration": "5 days",
  "instructions": "after food",
  "unit_price": "2500.00"
}
```

Expected pricing response:

```json
{
  "unit_price": "2500.00",
  "quantity": "1.00",
  "line_total": "2500.00"
}
```

Invalid item create without price:

```json
{
  "unit_price": ["This field is required."]
}
```

Endpoints returning `total_price`/`currency`:

- `/api/prescriptions/<id>/`
- `/api/patients/me/prescriptions/`
- `/api/patients/me/prescriptions/<id>/`
- `/api/pharmacist/prescriptions/`
- `/api/pharmacist/prescriptions/<id>/`
- `/api/admin/prescription-logs/`
- `/api/admin/prescription-logs/<id>/`

Frontend/mobile must be updated to send `unit_price` or `price` for every created medicine item. `quantity` can be omitted.

## 7. Patient / QR System

| QR concept | Purpose | Who generates it | Who uses it | Raw stored? | Hash stored? | Expiry | One-time? | Endpoints |
|---|---|---|---|---|---|---|---|---|
| `PatientProfile.qr_code_value` | Stable patient record QR / legacy login QR with PIN | `assign_patient_qr_code` via admin/create/register | Pharmacist session start; patient QR login with PIN | Yes | No | No | No | admin QR endpoints, `/api/patient-sessions/start-by-qr/`, `/api/auth/patient/qr-login/` |
| `PatientProfile.qr_is_active` | Enable/disable stable QR | Admin/patient creation | QR validation | N/A | N/A | No | No | admin QR disable/reactivate |
| `PatientLoginQR` | Secure login token QR | Admin `GeneratePatientLoginQRSerializer` | Patient QR login | No, returned only at generation | Yes, `token_hash` | No explicit expiry | Active until revoked/replaced | `/api/admin/patients/<id>/login-qr/`, `/api/auth/patient/qr-login/` |
| `PatientSessionQR` | One-time short-lived session QR | Patient self endpoint | Pharmacist starts session | No, returned only at generation | Yes, `token_hash` | Yes, default 300 seconds in service | Yes, marks `used_at` | `/api/patients/me/session-qr/`, `/api/pharmacist/sessions/start-by-qr/` |
| `PatientSession` | Active pharmacist-patient workflow session | Pharmacist session start | Prescription creation | Stores snapshot only | N/A | `expires_at` optional | N/A | pharmacist sessions and prescription create |

Admin QR decision:

- Admin `/api/admin/qr-codes/` uses `PatientProfile` rows with `qr_code_value`.
- QR id equals `PatientProfile.id`.
- `PatientLoginQR.token_hash` is not exposed.
- Regenerate calls `assign_patient_qr_code(patient, regenerate=True)`.
- Disable sets `qr_is_active=False`.
- Reactivate sets `qr_is_active=True` if value exists, otherwise generates one.

## 8. Transcription and Sign Generation

Current support:

- Audio upload validators in `common/uploads.py` and `transcriptions/validators.py`.
- Prescription item audio stored on `PrescriptionItem.instructions_audio`.
- Raw transcript: `PrescriptionItem.instructions_transcript_raw`.
- Edited/approved transcript: `PrescriptionItem.instructions_transcript_edited`.
- Transcription status fields: `transcription_status`, `transcription_provider`, timestamps, error message.
- Sign/gloss output: `PrescriptionItem.supporting_text`.
- Sign status: `PrescriptionItem.sign_status`.
- Sign video field exists: `PrescriptionItem.sign_language_video`.

Provider configuration:

- `TRANSCRIPTION_PROVIDER = "gemini"` in settings.
- `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_SIGN_MODEL`.
- `prescriptions/transcription.py` also supports `PRESCRIPTION_TRANSCRIPTION_BACKEND`, default `"placeholder"` for lower-level item transcription service.

Endpoints:

| Endpoint | Method | Purpose | View |
|---|---:|---|---|
| `/api/pharmacist/prescriptions/<id>/items/<item_id>/transcribe-audio/` | POST | Upload/transcribe audio | `PharmacistPrescriptionViewSet.transcribe_audio` |
| `/api/prescriptions/items/<id>/transcribe/` | POST | Legacy item transcribe action | `PrescriptionItemViewSet.transcribe` |
| `/api/pharmacist/prescriptions/<id>/items/<item_id>/approve-transcript/` | POST | Approve transcript | `PharmacistPrescriptionViewSet.approve_transcript` |
| `/api/pharmacist/prescriptions/<id>/items/<item_id>/generate-sign/` | POST | Generate sign/gloss | `PharmacistPrescriptionViewSet.generate_sign` |
| `/api/transcriptions/test/` | POST | Standalone transcription test | `TestTranscriptionView` |

Known limitations:

- `generate_sign` returns `"video_url": null`, `"output_type": "gloss_only"`, `"video_generation_supported": false`.
- Real sign video generation is not implemented.
- `sign_language_video` exists but is not produced by current gloss generation.
- Gemini API key is required for real transcription/sign generation.
- In DEBUG, provider exceptions are logged; responses use sanitized errors in provider-facing flows.

## 9. Sign Quality Monitoring

Current backend:

- Model: `prescriptions.models.SignQualityReport`.
- Patient report endpoint: `/api/patients/me/prescriptions/items/<item_id>/report-sign-issue/`.
- Admin endpoints:
  - `/api/admin/sign-quality-reports/`
  - `/api/admin/sign-quality-reports/<id>/`
- Serializers:
  - `SignQualityReportSerializer`
  - `PatientSignQualityReportCreateSerializer`
  - `AdminSignQualityReportSerializer`
  - `AdminSignQualityReportUpdateSerializer`
- Statuses:
  - `open`
  - `reviewed`
  - `resolved`
  - `dismissed`
- Report type:
  - `sign_unclear`

Missing:

- `reviewer_notes` field.
- per-medicine `medicineQualityStatus` separate from report status.
- frontend expected `/api/admin/sign-quality-records/`.
- grouped record shape with prescription, pharmacy, pharmacist, and medicine list.
- sign quality detail currently does not include pharmacy/pharmacist summary.

Recommendation:

- Reuse `SignQualityReport` as the base record.
- Add alias endpoints `/api/admin/sign-quality-records/` and `/api/admin/sign-quality-records/<id>/` only if the frontend contract requires those names.
- Do not add `reviewer_notes` until product confirms it is needed; if needed, migration required.
- Keep one row per reported item unless product wants grouped-by-prescription review; grouping can be serializer-only initially.
- Phase F can be implemented without migration if it only reshapes existing fields and status.

## 10. Reports / Analytics / Dashboard

Existing:

- `/api/admin/dashboard/stats/` returns:
  - patients count
  - pharmacists count
  - pharmacies count
  - prescriptions count
  - active QR count
  - pending approvals count
  - sign quality follow-up count
  - gender/hearing/age distributions
  - recent patients
  - recent approval requests
- No `/api/admin/reports/summary/` endpoint found.
- No PDF/Excel export endpoint found.
- Dashboard stats do not include `total_sales`.
- Prescription pricing totals are not included in stats.

Recommended minimal `/api/admin/reports/summary/`:

- `total_sales = Sum(Prescription.total_price)` with date/status filters.
- `prescriptions_by_status`.
- `prescriptions_by_date`.
- top pharmacies by prescription count and sales.
- sign quality counts.
- pending approvals count.
- active QR count.

## 11. Settings / Organization Profile

Existing:

- `Organization` model: `name`, `description`, `phone`, `address`.
- `OrganizationStaffProfile` model: `organization`, `job_title`, `can_manage_patients`, `can_manage_pharmacists`.
- Serializers exist in `organizations/serializers.py`.
- No `organizations/urls.py` or admin settings endpoint found.
- Patient self settings exist at `/api/patients/me/settings/`, but this is not admin organization settings.

Recommendation:

- Implement `/api/admin/settings/` if frontend settings page is in scope.
- Without migration, support:
  - organization `name`
  - `description`
  - `phone`
  - `address`
  - current staff profile `job_title`
  - permissions read-only or carefully admin-only writable.
- Migration needed for logo, website, email, theme, branding, billing config, feature flags.

## 12. Missing Features / Remaining Work

| Priority | Task | Why needed | Suggested endpoints/files | Migration needed? | Risk |
|---|---|---|---|---|---|
| P0 | Password reset / account recovery | Users can get locked out; no recovery path found | `accounts/models.py`, `accounts/serializers.py`, `accounts/views.py`, `/api/auth/password-reset/request/`, `/api/auth/password-reset/confirm/` | Likely yes if token model, or reuse OTP with new purpose | High |
| P1 | Sign Quality Phase F | Admin dashboard frontend expects richer sign-quality records | `prescriptions/serializers.py`, `prescriptions/views.py`, `prescriptions/urls.py` | No for alias/basic shape; yes for reviewer notes | Medium |
| P1 | Reports summary including total sales | Pricing exists but analytics do not expose it | `accounts/views.py` or new reports app/view, `/api/admin/reports/summary/` | No initially | Medium |
| P2 | Admin settings endpoint | Frontend settings page cannot connect | `organizations/serializers.py`, new views/urls or account admin view | No for current org fields | Low/Medium |
| P2 | Final frontend-backend contract | Prevent field naming and shape drift | `FRONTEND_BACKEND_CONTRACT.md` | No | Medium |
| P2 | Postman collection for all admin endpoints | QA and integration speed | docs/postman collection | No | Low |
| P2 | Frontend integration replacing mock contexts | Required for real dashboard | Frontend repo, not backend | No backend migration | Medium |
| P2 | Production deployment check | Ensure migrations and URLs live | server ops | No | Medium |
| P1 | Security hardening/rate limits for OTP/password reset | OTP abuse protection | throttling settings, auth views/services | Maybe | High |
| P3 | Documentation update | Maintainability | `README`, docs files | No | Low |

## 13. Security Audit

Positive findings:

- JWT auth is centralized through `ApprovalAwareJWTAuthentication`.
- Token refresh enforces account approval via `ApprovalAwareTokenRefreshSerializer`.
- Pending/rejected users are blocked from login and token use.
- Admin APIs use `CanManagePatients`, `CanManagePharmacists`, or explicit admin checks.
- Patient/pharmacist prescription querysets are role-scoped.
- Patient login/session QR token hashes are stored; raw tokens are returned only at generation.
- File uploads validate extension, size, and content type.
- Admin QR list does not expose `PatientLoginQR.token_hash`.

Risks / concerns:

- Password reset is missing.
- OTP lacks password reset purpose.
- Need throttling/rate limiting for OTP and future password reset; no DRF throttling config found.
- In DEBUG, OTP responses include `debug_otp`; production must set `DEBUG=False`.
- Default `SECRET_KEY` fallback is insecure if not overridden.
- `ALLOWED_HOSTS` defaults to local hosts only; production must configure.
- `CORS_ALLOWED_ORIGINS` defaults to local Expo/dev origins; production must configure.
- `admin_logout` requires auth but does not explicitly call `_ensure_admin_response`; however JWT auth will still authenticate approved users. Product may want admin-only logout namespace behavior.
- Admin-created temporary passwords are returned once in API response; frontend and operators must handle securely.
- `PrescriptionAccessLog` lacks IP/user-agent.
- Real provider errors are sanitized in some places, but DEBUG logging may include provider exceptions.
- If `DEBUG=True` in production, Django debug pages and debug OTP become critical exposure.

Endpoints that must not expose sensitive data:

- `/api/admin/patients/<id>/login-qr/` returns raw login QR token; secure transport and operator handling required.
- Admin user/pharmacist/patient create endpoints may return temporary passwords.
- QR token hashes must remain hidden.

Recommended hardening:

- Add DRF throttling for OTP, login, password reset, QR login.
- Add password reset with hashed, expiring, attempt-limited tokens.
- Enforce production `DEBUG=False`, secure `SECRET_KEY`, strict `ALLOWED_HOSTS`, strict CORS.
- Consider audit fields for admin actions.
- Add IP/user-agent to sensitive access logs if product needs compliance audit.

## 14. Backend-Frontend Contract Notes

Base URL in local development:

- `http://127.0.0.1:8000`

Auth flow:

1. Admin logs in via `POST /api/admin/auth/login/`.
2. Store `access` and `refresh` securely.
3. Send `Authorization: Bearer <access>` on admin requests.
4. Refresh via `POST /api/auth/refresh/`.
5. Logout via `POST /api/admin/auth/logout/` with refresh token.

Status codes:

- `200` success.
- `201` create success.
- `204` delete/deactivate success.
- `400` validation/business rule failure.
- `401` missing/invalid auth.
- `403` authenticated but role/approval/permission denied.
- `404` object outside scope or missing.
- `502/503` provider errors for transcription/sign generation.

Error shape:

- Varies between direct DRF field errors and custom `{detail, code, fields}` payloads.
- Frontend should handle both field-error objects and `detail/code`.

Naming:

- Backend currently uses snake_case.
- Frontend should either consume snake_case directly or centralize camelCase mapping in adapters.

Pagination:

DRF page-number shape:

```json
{
  "count": 0,
  "next": null,
  "previous": null,
  "results": []
}
```

Admin endpoints by feature:

- Auth: `/api/admin/auth/login/`, `/api/admin/auth/me/`, `/api/admin/auth/logout/`
- Dashboard: `/api/admin/dashboard/stats/`
- Patients: `/api/admin/patients/`, `/api/admin/patients/<id>/`, `/api/admin/patients/<id>/generate-qr/`
- QR: `/api/admin/qr-codes/`, `/api/admin/qr-codes/<id>/`, actions
- Pharmacies: `/api/admin/pharmacies/`, `/api/admin/pharmacies/<id>/`
- Pharmacists: `/api/admin/pharmacists/`, `/api/admin/pharmacists/<id>/`
- Approvals: `/api/admin/approval-requests/`, detail, approve, reject
- Prescription logs: `/api/admin/prescription-logs/`, detail
- Sign quality partial: `/api/admin/sign-quality-reports/`, detail/update

Pricing rule:

- `unit_price` required on create, or legacy `price`.
- `quantity` optional, defaults to `1.00`.
- `line_total` and `total_price` are backend-calculated.
- Do not send or trust frontend totals.

QR rule:

- Admin QR `id` equals patient profile id.
- Admin QR value is `PatientProfile.qr_code_value`.
- Secure login QR token is separate and raw token is only returned at generation.

Fields currently null/unsupported:

- patient `city`
- patient `region`
- patient `diagnosis` at patient level
- pharmacy `city`
- pharmacy `region`
- pharmacy `license_number`
- pharmacy `status`
- pharmacy `notes`
- pharmacist `notes`

Frontend must not assume these fields exist as editable backend fields yet.

## 15. Deployment Checklist

Linux server commands:

```bash
cd /path/to/PharmaSign_BackEnd
git status
git pull
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
python manage.py test accounts patients pharmacies prescriptions
sudo systemctl restart pharmasign
sudo systemctl restart nginx
sudo journalctl -u pharmasign -n 100 --no-pager
```

Smoke tests:

```bash
curl -i http://127.0.0.1:8000/api/admin/auth/login/
curl -i http://127.0.0.1:8000/api/auth/refresh/
```

Deployment notes:

- The pricing migration `prescriptions/migrations/0005_prescription_currency_prescription_total_price_and_more.py` must be applied.
- If `/api/admin/auth/login/` returns 404, deployed code is outdated or URL wiring is missing.
- Ensure `DEBUG=False`, real `SECRET_KEY`, production `ALLOWED_HOSTS`, production `CORS_ALLOWED_ORIGINS`.
- Ensure `GEMINI_API_KEY` is set if real transcription/sign gloss generation is expected.

## 16. Test Summary

Test files found:

- `accounts/tests.py`
- `patients/tests.py`
- `pharmacies/tests.py`
- `prescriptions/tests.py`
- `transcriptions/tests.py`

Visible test classes:

- `AuthAndPatientFlowTests`
- `AdminPhaseAApiTests`
- `AdminApprovalPhaseDApiTests`
- `PatientSessionFlowTests`
- `OrganizationStaffPermissionTests`
- `PatientSessionQRFlowTests`
- `AdminPatientPhaseBApiTests`
- `PharmacyPermissionTests`
- `AdminPharmacyPhaseCApiTests`
- `PrescriptionPermissionTests`
- `SignQualityReportTests`
- `AdminPrescriptionLogPhaseETests`
- `PharmacistPrescriptionMVPTests`
- `PrescriptionMediaUploadTests`
- `PrescriptionTranscriptionPipelineTests`
- `TranscriptionServiceTests`
- `TestTranscriptionEndpointTests`

Recent full test command from current work:

```bash
python manage.py test accounts patients pharmacies prescriptions
```

Recent visible result:

```text
Ran 245 tests in 710.360s
OK
```

Covered features include auth/registration/approval, admin phases A-E, patient sessions/QR, pharmacy/pharmacist admin, prescriptions, pricing, media upload, transcription, sign quality reports.

Tests still recommended:

- Password reset tests after implementation.
- Reports summary tests.
- Admin settings tests.
- Sign-quality records alias/detail shape tests.
- Security throttling tests for OTP/login/reset.
- Deployment smoke tests against a running production-like server.

## 17. Final Recommendation

Immediate next backend task: implement password reset / account recovery for patients and pharmacists, with throttling and expiring hashed tokens or OTP extension.

Backend readiness for frontend admin integration: mostly ready for core admin dashboard integration across auth, stats, patients, QR, pharmacies, pharmacists, approvals, and prescription logs.

Blocking or near-blocking gaps for frontend integration:

- If the frontend has a settings page, `/api/admin/settings/` is missing.
- If the frontend expects `/api/admin/sign-quality-records/`, that alias/shape is missing.
- If the frontend needs reports, `/api/admin/reports/summary/` is missing.
- If users need self-service account recovery, password reset is missing.

Can wait:

- PDF/Excel exports.
- Rich organization branding settings.
- IP/user-agent access logging.
- Real sign video generation if current product accepts gloss-only output.
