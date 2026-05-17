# Backend Discovery Report

## 1. Executive Summary

This backend is a Django 5.1 / Django REST Framework API project named `pharmasign`, with a custom `accounts.User` model and local apps for accounts, organizations, patients, pharmacies, prescriptions, and transcriptions.

The active API root is `/api/`, configured in `pharmasign/urls.py` and `pharmasign/api_urls.py`. The backend has substantial implemented functionality: OTP-based patient/pharmacist registration, JWT login/refresh/logout, approval-aware authentication, patient QR login, patient session QR access, pharmacist patient sessions, prescription creation and lifecycle, audio transcription, gloss generation, admin dashboards, admin patient/pharmacy/pharmacist management, prescription logs, and sign quality reports.

The most important risks are production secret leakage in `.env`, inconsistent/legacy API surfaces kept alongside newer workflow endpoints, missing organization API routes despite serializers/admin models existing, generated sign output being gloss-only with no actual video generation, several admin response fields intentionally returning placeholders (`city`, `region`, `status`, `notes`, `license_number`), and potentially destructive-looking router routes that advertise unsupported HTTP methods because ViewSets restrict `http_method_names` but routers still expose action mappings in URL resolution.

`python manage.py test` was attempted. It discovered 263 tests and passed Django system checks, but timed out after 120 seconds before completion.

## 2. Project Structure

- Main Django project: `pharmasign`
- Entry point: `manage.py`
- Main settings file: `pharmasign/settings.py`
- Root URL config: `pharmasign/urls.py`
- API include config: `pharmasign/api_urls.py`
- Backend apps:
  - `accounts/`
  - `common/`
  - `organizations/`
  - `patients/`
  - `pharmacies/`
  - `prescriptions/`
  - `transcriptions/`
- Existing docs/audits at repo root are present but were not treated as source of truth.
- Media folders exist: `media/`, `test-media-*`.
- Local SQLite database exists: `db.sqlite3`.

URL configuration:

- `pharmasign/urls.py` mounts Django admin at `/admin/` and API at `/api/`.
- `pharmasign/api_urls.py` includes:
  - `accounts.urls` at `/api/`
  - `patients.urls` at `/api/`
  - `pharmacies.urls` at `/api/`
  - `prescriptions.urls` at `/api/`
  - `transcriptions.urls` at `/api/transcriptions/`
- No `organizations.urls` exists or is included.

API prefixes and namespaces:

- Global API prefix: `/api/`
- Django admin prefix: `/admin/`
- App `app_name` exists in `accounts/urls.py` and `transcriptions/urls.py`.
- `patients/urls.py`, `pharmacies/urls.py`, and `prescriptions/urls.py` do not declare `app_name`.
- DRF routers create repeated `api-root` routes inside several included app URL files.

## 3. Installed Apps

From `pharmasign/settings.py`:

- Django apps: `django.contrib.admin`, `auth`, `contenttypes`, `sessions`, `messages`, `staticfiles`
- Third-party apps: `corsheaders`, `rest_framework`, `rest_framework_simplejwt`, `rest_framework_simplejwt.token_blacklist`
- Local apps: `common`, `accounts`, `organizations`, `patients`, `pharmacies`, `prescriptions`, `transcriptions`

App responsibilities:

| App | Path | Purpose | APIs | Important files |
|---|---|---:|---:|---|
| `common` | `common/` | Shared choices, permissions, upload validation, utility hashing/QR helpers, timestamp base model | No direct API | `choices.py`, `permissions.py`, `uploads.py`, `utils.py`, `api_errors.py`, `models.py` |
| `accounts` | `accounts/` | Custom user, OTP, JWT/auth endpoints, admin auth/dashboard/approval | Yes | `models.py`, `serializers.py`, `views.py`, `urls.py`, `authentication.py`, `jwt.py`, `services.py`, `otp_delivery.py`, `admin.py`, `tests.py` |
| `organizations` | `organizations/` | Organizations and organization staff scoping | No API route found | `models.py`, `serializers.py`, `admin.py` |
| `patients` | `patients/` | Patient profiles, enrollment, QR login/session tokens, settings, admin patient management, pharmacist sessions | Yes | `models.py`, `serializers.py`, `views.py`, `urls.py`, `services.py`, `admin.py`, `tests.py` |
| `pharmacies` | `pharmacies/` | Pharmacy and pharmacist profile management, public contracted pharmacies, pharmacist self profile/pharmacy | Yes | `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `tests.py` |
| `prescriptions` | `prescriptions/` | Prescriptions, items, pricing, media, lifecycle, access logs, sign reports, transcription/gloss integration | Yes | `models.py`, `serializers.py`, `views.py`, `urls.py`, `services.py`, `transcription.py`, `constants.py`, `admin.py`, `tests.py` |
| `transcriptions` | `transcriptions/` | Gemini-backed standalone audio transcription service and validators | Yes | `views.py`, `services.py`, `validators.py`, `exceptions.py`, `urls.py`, `tests.py` |

## 4. Settings and Environment

Settings file: `pharmasign/settings.py`.

Middleware:

- `django.middleware.security.SecurityMiddleware`
- `corsheaders.middleware.CorsMiddleware`
- `django.contrib.sessions.middleware.SessionMiddleware`
- `django.middleware.common.CommonMiddleware`
- `django.middleware.csrf.CsrfViewMiddleware`
- `django.contrib.auth.middleware.AuthenticationMiddleware`
- `django.contrib.messages.middleware.MessageMiddleware`
- `django.middleware.clickjacking.XFrameOptionsMiddleware`

Authentication:

- `AUTH_USER_MODEL = "accounts.User"`
- DRF default auth: `accounts.authentication.ApprovalAwareJWTAuthentication`
- JWT package: `rest_framework_simplejwt`
- Token blacklist app installed.

Permissions:

- DRF default permission: `IsAuthenticated`
- Role helpers and permission classes in `common/permissions.py`:
  - `IsAdminRole`
  - `IsPharmacistRole`
  - `IsPatientRole`
  - `CanManagePatients`
  - `CanManagePharmacists`
  - `IsAdminOrPharmacistRole`
  - `IsApprovedPharmacistRole`

Pagination:

- DRF default: `rest_framework.pagination.PageNumberPagination`
- Default page size: `20`
- Admin-specific paginator classes in `accounts/views.py`, `patients/views.py`, `pharmacies/views.py`, `prescriptions/views.py` allow `page_size` up to `100`.

CORS:

- `CORS_ALLOWED_ORIGINS` comes from env and defaults to localhost/127.0.0.1 Expo-style ports `8081`, `8082`, and `19006`.

Static/media:

- `STATIC_URL = "/static/"`
- `STATIC_ROOT = BASE_DIR / "staticfiles"`
- `MEDIA_URL` from env, default `/media/`
- `MEDIA_ROOT = BASE_DIR / MEDIA_ROOT env`, default `media`
- Media served by `pharmasign/urls.py` only when `DEBUG` is true.
- Upload permissions configured as `0o640` for files and `0o750` for directories.

Database:

- If `DB_NAME != "db.sqlite3"`, PostgreSQL is used with `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
- Otherwise SQLite is used at `BASE_DIR / "db.sqlite3"`.

JWT:

- Access lifetime env `JWT_ACCESS_TOKEN_LIFETIME`, default `5h`.
- Refresh lifetime env `JWT_REFRESH_TOKEN_LIFETIME`, default `7d`.
- `ROTATE_REFRESH_TOKENS = True`.
- `BLACKLIST_AFTER_ROTATION` is not explicitly set, so SimpleJWT default behavior applies.

Environment variables used:

- `SECRET_KEY`
- `PHARMASIGN_ENV`
- `DEBUG`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `TIME_ZONE`
- `MEDIA_URL`, `MEDIA_ROOT`
- `PHARMASIGN_MAX_IMAGE_UPLOAD_BYTES`
- `PHARMASIGN_MAX_AUDIO_UPLOAD_BYTES`
- `PHARMASIGN_MAX_VIDEO_UPLOAD_BYTES`
- `PHARMASIGN_ALLOWED_IMAGE_EXTENSIONS`
- `PHARMASIGN_ALLOWED_AUDIO_EXTENSIONS`
- `PHARMASIGN_ALLOWED_VIDEO_EXTENSIONS`
- `PHARMASIGN_ALLOWED_IMAGE_CONTENT_TYPES`
- `PHARMASIGN_ALLOWED_AUDIO_CONTENT_TYPES`
- `PHARMASIGN_ALLOWED_VIDEO_CONTENT_TYPES`
- `TRANSCRIPTION_PROVIDER`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GEMINI_SIGN_MODEL`
- `MAX_AUDIO_UPLOAD_SIZE_MB`
- `OTP_DELIVERY_CHANNEL`
- `OTP_DELIVERY_PROVIDER_CONFIGURED`
- `OTP_TELEGRAM_ENABLED`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_DEFAULT_CHAT_ID`
- `TELEGRAM_REQUEST_TIMEOUT_SECONDS`
- `PRESCRIPTION_TRANSCRIPTION_BACKEND` is read in `prescriptions/transcription.py` but is not listed in `.env.example`.

Environment risk:

- `.env` exists in the repository and contains live-looking provider credentials. Exact values are intentionally not repeated here. This should be treated as an urgent secret rotation and git hygiene issue.

## 5. Models

Shared:

- `common/models.py`
  - `TimeStampedModel`: abstract model with `created_at = auto_now_add`, `updated_at = auto_now`.

Accounts:

- `accounts/models.py`
  - `User(AbstractBaseUser, PermissionsMixin, TimeStampedModel)`
    - `email`: `EmailField`, unique, indexed, nullable/blank.
    - `phone_number`: `CharField(20)`, unique, nullable/blank.
    - `role`: choices from `RoleChoices`, default `patient`.
    - `is_staff`, `is_active`, `is_verified`: booleans.
    - `approval_status`: choices from `ApprovalStatusChoices`, default `approved`, indexed.
    - `approved_at`: nullable datetime.
    - `approved_by`: self FK nullable.
    - `rejection_reason`: text blank.
    - Indexes: `email`, `role/is_active`, `role/approval_status`.
    - Custom manager creates superusers as admin, approved, verified.
    - Admin registered in `accounts/admin.py`.
  - `PhoneOTP(TimeStampedModel)`
    - `phone_number`, `purpose`, `code_hash`, `expires_at`, `used_at`, `attempts`, `max_attempts`, `user`.
    - Purposes: `patient_register`, `pharmacist_register`.
    - Indexes: `phone_number/purpose`, `expires_at`, `used_at`.
    - Methods/properties: `set_code`, `check_code`, `is_expired`, `is_locked`, `mark_used`.
    - Admin registered in `accounts/admin.py`.

Organizations:

- `organizations/models.py`
  - `Organization(TimeStampedModel)`
    - `name` unique, `description`, `phone`, `address`.
    - Index: `name`.
    - Admin registered.
  - `OrganizationStaffProfile(TimeStampedModel)`
    - `user` one-to-one to auth user.
    - `organization` FK.
    - `job_title`, `can_manage_patients`, `can_manage_pharmacists`.
    - Validates `user.role == admin`.
    - Indexes: `organization`, `can_manage_patients/can_manage_pharmacists`.
    - Admin registered.

Patients:

- `patients/models.py`
  - `PatientProfile(TimeStampedModel)`
    - `user` one-to-one auth user.
    - `organization` nullable FK.
    - `full_name`, `phone_number`, `birth_date`, `gender`, `address`, `hearing_disability_level`.
    - `is_self_registered`, `qr_code_value` unique nullable, `qr_is_active`, `record_access_pin_hash`.
    - Validates user role is patient.
    - Indexes: `organization`, `full_name`, `qr_is_active`.
    - Property: `enrollment`.
    - Method: `set_record_access_pin`.
    - Admin registered.
  - `PatientEnrollment(TimeStampedModel)`
    - Organization enrollment record with names, parents, birth date, gender, address, phone, hearing level, notes, account status, creator.
    - `patient_profile` one-to-one nullable.
    - Duplicate guard inside organization by first/last/birth date and optional father name.
    - Indexes: `organization/last_name/birth_date`, `phone_number`, `is_account_created`.
    - Property: `full_name`.
    - Admin registered.
  - `PatientMedicalInfo(TimeStampedModel)`
    - One-to-one `patient`.
    - `blood_type`, `chronic_conditions`, `allergies`, `is_pregnant`, `is_breastfeeding`, `notes`.
    - Admin registered.
  - `PatientSettings(TimeStampedModel)`
    - One-to-one `patient`.
    - notification/dark mode/biometric booleans.
    - Admin registered.
  - `PatientLoginQR(TimeStampedModel)`
    - FK `patient`, `token_hash` unique indexed, `is_active`, `revoked_at`, `created_by`.
    - Indexes: `patient/is_active`, `is_active/revoked_at`.
    - Method: `revoke`.
    - Admin registered.
  - `PatientSessionQR(TimeStampedModel)`
    - FK `patient`, `token_hash` unique indexed, `expires_at`, `used_at`, `revoked_at`.
    - Indexes: `patient/used_at/revoked_at`, `expires_at`, `used_at`, `revoked_at`.
    - Properties/methods: `is_expired`, `mark_used`, `revoke`.
    - Admin registered.
  - `PatientSession(TimeStampedModel)`
    - FK `patient`, `pharmacist`, `pharmacy`.
    - `access_type`, `status`, `qr_code_value_snapshot`, `started_at`, `ended_at`, `expires_at`.
    - Statuses: `active`, `completed`, `cancelled`, `expired`.
    - Validates pharmacist pharmacy matches session pharmacy.
    - Indexes: patient/pharmacist/pharmacy with started date, `access_type`, `status/expires_at`.
    - Admin registered.

Pharmacies:

- `pharmacies/models.py`
  - `Pharmacy(TimeStampedModel)`
    - `name`, `owner_user`, `address`, `latitude`, `longitude`, `is_contracted_with_organization`, `organization`, `phone_number`.
    - Validates contracted pharmacies must have organization.
    - Indexes: `organization/is_contracted_with_organization`, `name`.
    - Admin registered.
  - `PharmacistProfile(TimeStampedModel)`
    - `user` one-to-one auth user.
    - `pharmacy` FK.
    - `full_name`, `license_number`, `is_approved`.
    - Validates user role is pharmacist.
    - Indexes: `pharmacy`, `is_approved`.
    - Admin registered.

Prescriptions:

- `prescriptions/models.py`
  - `Prescription(TimeStampedModel)`
    - FK `patient`, `pharmacist`, `pharmacy`, nullable `session`, nullable `reused_from`.
    - `doctor_name`, `doctor_specialty`, `diagnosis`, `status`, `prescribed_at`, `submitted_at`, `delivered_at`, `notes`, `total_price`, `currency`.
    - Statuses from `PrescriptionStatusChoices`: `draft`, `submitted`, `cancelled`, `confirmed`, `delivered`, `archived`.
    - Validates pharmacist pharmacy matches prescription pharmacy.
    - Method: `recalculate_total_price`.
    - Indexes: patient/prescribed date, pharmacist/status, pharmacy/status, session.
    - Admin registered.
  - `PrescriptionItem(TimeStampedModel)`
    - FK `prescription`.
    - Medicine fields: `medicine_name`, `dosage`, `frequency`, `duration`, `instructions_text`, `medicine_image`.
    - Pricing: legacy `price`, `unit_price`, `quantity`, `line_total`.
    - Audio/transcription: `instructions_audio`, `transcription_status`, provider, timestamps, error, raw/edited transcript.
    - Sign: `sign_language_video`, `supporting_text`, `sign_status`, `is_confirmed`.
    - Validates upload size/type/extensions; derives transcription status; calculates totals; updates prescription total on save/delete.
    - Indexes: `prescription/is_confirmed`, `prescription/sign_status`, `medicine_name`.
    - Admin registered.
  - `SignQualityReport(TimeStampedModel)`
    - FK `patient`, `prescription`, `prescription_item`.
    - `medicine_name`, `approved_instruction_text`, `report_type`, `status`.
    - Report type: `sign_unclear`.
    - Statuses: `open`, `reviewed`, `resolved`, `dismissed`.
    - Unique constraint: one open report per `patient/prescription_item/report_type`.
    - Admin registered.
  - `PrescriptionAccessLog`
    - FK `prescription`, nullable FK `accessed_by`, `access_type`, `timestamp`.
    - Access types: `view`, `item_update`, `confirm`, `transcribe`.
    - Indexes: `prescription/timestamp`, `access_type`.
    - Admin registered.

Transcriptions:

- No models found in `transcriptions/`.

## 6. Serializers

Accounts serializers in `accounts/serializers.py`:

- Auth and user serializers: `UserSerializer`, `LoginSerializer`, `LogoutSerializer`, `ChangePasswordSerializer`, `AuthMeSerializer`, `AdminAuthMeSerializer`.
- OTP serializers: `RegistrationOTPRequestSerializer`, `PatientRegistrationOTPRequestSerializer`.
- Admin approval serializer: `AdminApprovalRequestSerializer`.
- QR login serializer: `PatientQRLoginSerializer`.
- Registration serializer: `PatientSelfRegisterSerializer`.
- Response helpers build compatibility payloads for user, patient profile, pharmacy, pharmacist profile, admin auth.

Patients serializers in `patients/serializers.py`:

- Patient data: `PatientProfileSerializer`, `PatientMedicalInfoSerializer`, `PatientSelfProfileSerializer`, `PatientSettingsSerializer`.
- Admin patients: `AdminPatientSerializer`, `AdminPatientUpdateSerializer`, `AdminPatientCreateAccountSerializer`.
- QR: `AdminPatientQRSerializer`, `GeneratePatientQRSerializer`, `GeneratePatientLoginQRSerializer`, `RevokePatientLoginQRSerializer`, `GeneratePatientSessionQRSerializer`, `StartPatientSessionByQRSerializer`, `StartPatientSessionSerializer`.
- Sessions: `PharmacistPatientSessionSerializer`, `PatientSessionSerializer`.
- Enrollment/account: `PatientEnrollmentSerializer`, `CreatePatientAccountSerializer`.

Pharmacies serializers in `pharmacies/serializers.py`:

- `PharmacySerializer`, `AdminPharmacySerializer`, `AdminPharmacyWriteSerializer`, `SafePharmacySerializer`, `PharmacyCompatSerializer`.
- `PharmacistProfileSerializer`, `AdminPharmacistSerializer`, `AdminPharmacistWriteSerializer`, `PharmacistRegisterSerializer`, `PharmacistMeUpdateSerializer`.

Prescriptions serializers in `prescriptions/serializers.py`:

- Items: `PrescriptionItemContractSerializer`, `PrescriptionItemSerializer`, `SafePrescriptionItemSerializer`, `PrescriptionItemCreateSerializer`, `PrescriptionItemUpdateSerializer`, `PharmacistPrescriptionItemInputSerializer`, `PharmacistPrescriptionItemSerializer`.
- Prescriptions: `PrescriptionSerializer`, `PrescriptionCreateSerializer`, `PrescriptionConfirmSerializer`, `PharmacistPrescriptionSerializer`, `PharmacistPrescriptionListSerializer`, `PharmacistPrescriptionCreateSerializer`, `PharmacistPrescriptionUpdateSerializer`, `PharmacistPrescriptionSubmitSerializer`.
- Transcription/sign: `PrescriptionItemTranscriptionRequestSerializer`, `PharmacistPrescriptionItemAudioTranscriptionSerializer`, `ApproveTranscriptSerializer`, `TranscribedPrescriptionItemSerializer`.
- Admin logs/reports: `AdminPrescriptionLogListSerializer`, `AdminPrescriptionLogDetailSerializer`, `AdminPrescriptionLogItemSerializer`, `AdminPrescriptionAccessLogSerializer`, `SignQualityReportSerializer`, `PatientSignQualityReportCreateSerializer`, `AdminSignQualityReportSerializer`, `AdminSignQualityReportUpdateSerializer`.

Organizations serializers in `organizations/serializers.py`:

- `OrganizationSerializer`
- `OrganizationStaffProfileSerializer`
- No URL/view exposure found.

Transcriptions:

- No separate serializer file. `transcriptions/views.py` performs inline request handling and uses upload validators.

## 7. Views and ViewSets

Accounts:

- `accounts/views.py`
  - `AuthViewSet`: registration, OTP request, login, admin login/me/logout/dashboard, approval requests, user approve/reject, logout, change password, me, patient QR login.
  - Public actions: pharmacist register, login, admin login, patient register/self-register, OTP request endpoints, patient QR login.
  - Authenticated actions: logout, change password, me, admin endpoints.
- `accounts/jwt.py`
  - `ApprovalAwareTokenRefreshView`: refresh token endpoint with account approval enforcement.
- `accounts/authentication.py`
  - `ApprovalAwareJWTAuthentication`: rejects inactive/pending/rejected non-staff/non-superuser accounts.

Patients:

- `patients/views.py`
  - `PatientEnrollmentViewSet`: enrollment CRUD-ish, create patient account from enrollment.
  - `PatientManagementViewSet`: legacy/admin QR generation.
  - `AdminPatientViewSet`: admin list/retrieve/patch/soft-delete/generate QR.
  - `AdminQRCodeViewSet`: admin QR list/detail/regenerate/disable/reactivate.
  - `PatientSelfProfileViewSet`: patient `me`.
  - `PatientSettingsViewSet`: patient settings.
  - `PatientSessionQRViewSet`: patient-generated session QR token.
  - `AdminPatientAccountViewSet`: admin creates patient account.
  - `AdminPatientLoginQRViewSet`: admin creates/revokes login QR token.
  - `PatientSessionViewSet`: legacy pharmacist start session by persistent QR code.
  - `PharmacistPatientSessionViewSet`: current pharmacist session list/start-by-session-QR/end.

Pharmacies:

- `pharmacies/views.py`
  - `PharmacyViewSet`: router-backed pharmacy list/create/contracted, scoped by role.
  - `AdminPharmacyViewSet`: admin pharmacy CRUD.
  - `AdminPharmacistViewSet`: admin pharmacist CRUD.
  - `PublicContractedPharmacyViewSet`: unauthenticated contracted pharmacies.
  - `PatientPharmacyViewSet`: patient contracted pharmacies.
  - `PharmacistProfileViewSet`: pharmacist self profile.
  - `PharmacistPharmacyViewSet`: pharmacist own pharmacy.

Prescriptions:

- `prescriptions/views.py`
  - `PrescriptionViewSet`: legacy retrieve, disabled create, add item, confirm.
  - `PrescriptionItemViewSet`: legacy item update and placeholder backend transcription.
  - `PharmacistPrescriptionViewSet`: current pharmacist prescription workflow including create, item CRUD, audio transcription, transcript approval, gloss generation, submit/confirm/deliver/cancel/archive.
  - `PatientPrescriptionViewSet`: patient list/detail.
  - `PatientSignQualityReportViewSet`: patient sign quality report creation.
  - `AdminPrescriptionLogViewSet`: admin prescription logs.
  - `AdminSignQualityReportViewSet`: admin sign quality report list/detail/update.

Transcriptions:

- `transcriptions/views.py`
  - `TestTranscriptionView`: standalone authenticated multipart audio transcription test endpoint, restricted in code to approved pharmacist role.

## 8. URL Map and API Endpoints

All API endpoints below are under `/api/`.

Authentication and account endpoints:

| Method | Path | View/action | Serializer | Permission | Status |
|---|---|---|---|---|---|
| POST | `/auth/register/request-otp/` | `AuthViewSet.register_request_otp` | `RegistrationOTPRequestSerializer` | Public | Implemented |
| POST | `/auth/patient/register/request-otp/` | `AuthViewSet.patient_register_request_otp` | `PatientRegistrationOTPRequestSerializer` | Public | Implemented |
| POST | `/auth/pharmacist/register/request-otp/` | `AuthViewSet.pharmacist_register_request_otp` | `RegistrationOTPRequestSerializer` | Public | Implemented |
| POST | `/auth/patient/self-register/` | `AuthViewSet.patient_self_register` | `PatientSelfRegisterSerializer` | Public | Implemented |
| POST | `/auth/patient/register/` | `AuthViewSet.patient_register` | `PatientSelfRegisterSerializer` | Public | Implemented alias |
| POST | `/auth/pharmacist/register/` | `AuthViewSet.pharmacist_register` | `PharmacistRegisterSerializer` | Public | Implemented |
| POST | `/auth/login/` | `AuthViewSet.login` | `LoginSerializer` | Public | Implemented |
| POST | `/auth/patient/qr-login/` | `AuthViewSet.patient_qr_login` | `PatientQRLoginSerializer` | Public | Implemented |
| POST | `/auth/refresh/` | `ApprovalAwareTokenRefreshView` | `ApprovalAwareTokenRefreshSerializer` | Public with refresh token | Implemented |
| POST | `/auth/logout/` | `AuthViewSet.logout` | `LogoutSerializer` | Authenticated | Implemented |
| POST | `/auth/change-password/` | `AuthViewSet.change_password` | `ChangePasswordSerializer` | Authenticated | Implemented |
| GET | `/auth/me/` | `AuthViewSet.me` | `AuthMeSerializer` | Authenticated | Implemented |

Admin auth and dashboard:

| Method | Path | View/action | Serializer | Permission | Status |
|---|---|---|---|---|---|
| POST | `/admin/auth/login/` | `AuthViewSet.admin_login` | `LoginSerializer`, `AdminAuthMeSerializer` | Public credentials, admin role required after validation | Implemented |
| GET | `/admin/auth/me/` | `AuthViewSet.admin_me` | `AdminAuthMeSerializer` | Authenticated admin | Implemented |
| POST | `/admin/auth/logout/` | `AuthViewSet.admin_logout` | `LogoutSerializer` | Authenticated | Implemented |
| GET | `/admin/dashboard/stats/` | `AuthViewSet.admin_dashboard_stats` | Inline payload | Authenticated admin | Implemented, some placeholder dimensions |

Admin approval:

| Method | Path | View/action | Permission | Query/body | Status |
|---|---|---|---|---|---|
| GET | `/admin/registration-requests/` | `registration_requests` | Admin/staff with approval management | none | Legacy/simple implemented |
| GET | `/admin/approval-requests/` | `approval_requests` | Admin/staff with approval management | `type`, `status`, `search`, `page_size` | Implemented |
| GET | `/admin/approval-requests/<pk>/` | `approval_request_detail` | Same | none | Implemented |
| POST | `/admin/approval-requests/<pk>/approve/` | `approve_approval_request` | Same | empty | Implemented |
| POST | `/admin/approval-requests/<pk>/reject/` | `reject_approval_request` | Same | `reason` | Implemented |
| POST | `/admin/users/<pk>/approve/` | `approve_user` | Same | empty | Legacy implemented |
| POST | `/admin/users/<pk>/reject/` | `reject_user` | Same | `reason` | Legacy implemented |

Patient/admin patient endpoints:

| Method | Path | View/action | Serializer | Permission | Status |
|---|---|---|---|---|---|
| GET, POST | `/patients/enrollments/` | `PatientEnrollmentViewSet` | `PatientEnrollmentSerializer` | Can manage patients | Implemented |
| GET, PATCH | `/patients/enrollments/<pk>/` | `PatientEnrollmentViewSet` | `PatientEnrollmentSerializer` | Can manage patients | Implemented; router advertises PUT/DELETE but view restricts methods |
| POST | `/patients/enrollments/<pk>/create-account/` | `create_account` | `CreatePatientAccountSerializer` | Can manage patients | Implemented |
| GET, PATCH | `/patients/me/` | `PatientSelfProfileViewSet` | `PatientSelfProfileSerializer` | Patient | Implemented |
| GET, PATCH | `/patients/me/settings/` | `PatientSettingsViewSet` | `PatientSettingsSerializer` | Patient | Implemented |
| POST | `/patients/me/session-qr/` | `PatientSessionQRViewSet` | `GeneratePatientSessionQRSerializer` | Patient | Implemented |
| POST | `/patients/<pk>/generate-qr/` | `PatientManagementViewSet.generate_qr` | `GeneratePatientQRSerializer` | Can manage patients | Legacy/admin implemented |
| GET | `/admin/patients/` | `AdminPatientViewSet.list` | `AdminPatientSerializer` | Can manage patients | Implemented |
| GET, PATCH, DELETE | `/admin/patients/<pk>/` | `AdminPatientViewSet` | `AdminPatientSerializer` / `AdminPatientUpdateSerializer` | Can manage patients | Implemented; delete is soft deactivation |
| POST | `/admin/patients/create-account/` | `AdminPatientAccountViewSet` | `AdminPatientCreateAccountSerializer` | Can manage patients | Implemented |
| POST | `/admin/patients/<pk>/generate-qr/` | `AdminPatientViewSet.generate_qr` | `GeneratePatientQRSerializer` | Can manage patients | Implemented |
| GET | `/admin/qr-codes/` | `AdminQRCodeViewSet.list` | `AdminPatientQRSerializer` | Can manage patients | Implemented |
| GET | `/admin/qr-codes/<pk>/` | `AdminQRCodeViewSet.retrieve` | `AdminPatientQRSerializer` | Can manage patients | Implemented |
| POST | `/admin/qr-codes/<pk>/regenerate/` | `AdminQRCodeViewSet.regenerate` | `AdminPatientQRSerializer` | Can manage patients | Implemented |
| POST | `/admin/qr-codes/<pk>/disable/` | `AdminQRCodeViewSet.disable` | `AdminPatientQRSerializer` | Can manage patients | Implemented |
| POST | `/admin/qr-codes/<pk>/reactivate/` | `AdminQRCodeViewSet.reactivate` | `AdminPatientQRSerializer` | Can manage patients | Implemented |
| POST | `/admin/patients/<patient_id>/login-qr/` | `AdminPatientLoginQRViewSet.generate` | `GeneratePatientLoginQRSerializer` | Can manage patients | Implemented |
| POST | `/admin/patients/<patient_id>/login-qr/revoke/` | `AdminPatientLoginQRViewSet.revoke` | `RevokePatientLoginQRSerializer` | Can manage patients | Implemented |

Patient session endpoints:

| Method | Path | View/action | Serializer | Permission | Status |
|---|---|---|---|---|---|
| POST | `/patient-sessions/start-by-qr/` | `PatientSessionViewSet.start_by_qr` | `StartPatientSessionSerializer` | Approved pharmacist | Legacy persistent-QR session start |
| GET | `/pharmacist/sessions/` | `PharmacistPatientSessionViewSet.list` | `PharmacistPatientSessionSerializer` | Approved pharmacist | Implemented |
| POST | `/pharmacist/sessions/start-by-qr/` | `PharmacistPatientSessionViewSet.start_by_qr` | `StartPatientSessionByQRSerializer` | Approved pharmacist | Implemented current session QR flow |
| POST | `/pharmacist/sessions/<session_id>/end/` | `PharmacistPatientSessionViewSet.end` | Inline | Approved pharmacist | Implemented |

Pharmacy/pharmacist endpoints:

| Method | Path | View/action | Serializer | Permission | Status |
|---|---|---|---|---|---|
| GET, POST | `/pharmacies/` | `PharmacyViewSet` | `PharmacySerializer` | Pharmacist for list, admin manager for create/admin role | Implemented but mixed role behavior |
| GET | `/pharmacies/contracted/` | `PharmacyViewSet.contracted` | `PharmacySerializer` | Authenticated role-dependent | Implemented |
| GET | `/auth/contracted-pharmacies/` | `PublicContractedPharmacyViewSet.list` | `SafePharmacySerializer` | Public | Implemented |
| GET | `/patients/pharmacies/` | `PatientPharmacyViewSet.list` | `SafePharmacySerializer` | Patient | Implemented |
| GET, PATCH | `/pharmacists/me/` | `PharmacistProfileViewSet` | `PharmacistProfileSerializer`, `PharmacistMeUpdateSerializer` | Pharmacist | Implemented |
| GET, PATCH | `/pharmacist/me/` | same | same | Pharmacist | Implemented alias |
| GET, PATCH | `/pharmacist/me/pharmacy/` | `PharmacistPharmacyViewSet` | `PharmacyCompatSerializer` | Pharmacist | Implemented |
| GET, POST | `/admin/pharmacies/` | `AdminPharmacyViewSet` | `AdminPharmacySerializer`, `AdminPharmacyWriteSerializer` | Can manage pharmacists | Implemented |
| GET, PATCH, DELETE | `/admin/pharmacies/<pk>/` | `AdminPharmacyViewSet` | same | Can manage pharmacists | Implemented |
| GET, POST | `/admin/pharmacists/` | `AdminPharmacistViewSet` | `AdminPharmacistSerializer`, `AdminPharmacistWriteSerializer` | Can manage pharmacists | Implemented |
| GET, PATCH, DELETE | `/admin/pharmacists/<pk>/` | `AdminPharmacistViewSet` | same | Can manage pharmacists | Implemented; delete deactivates user/profile |

Prescription endpoints:

| Method | Path | View/action | Serializer | Permission | Status |
|---|---|---|---|---|---|
| POST | `/prescriptions/` | `PrescriptionViewSet.create` | `PrescriptionCreateSerializer` | Approved pharmacist | Disabled/legacy; returns instruction to use pharmacist workflow |
| GET | `/prescriptions/<pk>/` | `PrescriptionViewSet.retrieve` | `PrescriptionSerializer` | Role-scoped authenticated | Implemented legacy retrieve |
| POST | `/prescriptions/<pk>/items/` | `PrescriptionViewSet.add_item` | `PrescriptionItemCreateSerializer` | Approved pharmacist owner | Legacy implemented |
| POST | `/prescriptions/<pk>/confirm/` | `PrescriptionViewSet.confirm` | `PrescriptionConfirmSerializer` | Approved pharmacist owner | Legacy implemented |
| PATCH | `/prescriptions/items/<pk>/` | `PrescriptionItemViewSet.partial_update` | `PrescriptionItemUpdateSerializer` | Approved pharmacist owner | Legacy implemented |
| POST | `/prescriptions/items/<pk>/transcribe/` | `PrescriptionItemViewSet.transcribe` | `PrescriptionItemTranscriptionRequestSerializer` | Approved pharmacist owner | Legacy placeholder/failing backend |
| GET | `/patients/me/prescriptions/` | `PatientPrescriptionViewSet.list` | `PrescriptionSerializer` | Patient | Implemented |
| GET | `/patients/me/prescriptions/<pk>/` | `PatientPrescriptionViewSet.retrieve` | `PrescriptionSerializer` | Patient owner | Implemented |
| POST | `/patients/me/prescriptions/items/<item_id>/report-sign-issue/` | `PatientSignQualityReportViewSet.create` | `PatientSignQualityReportCreateSerializer` | Patient owner | Implemented |
| GET, POST | `/pharmacist/prescriptions/` | `PharmacistPrescriptionViewSet.list/create` | `PharmacistPrescriptionListSerializer`, `PharmacistPrescriptionCreateSerializer` | Pharmacist; create requires approved profile | Implemented |
| GET | `/pharmacist/prescriptions/doctor-specialties/` | `doctor_specialties` | Inline | Pharmacist | Implemented |
| GET, PATCH | `/pharmacist/prescriptions/<prescription_id>/` | retrieve/update | `PharmacistPrescriptionSerializer`, `PharmacistPrescriptionUpdateSerializer` | Pharmacist owner | Implemented |
| POST | `/pharmacist/prescriptions/<prescription_id>/items/` | `add_item` | `PharmacistPrescriptionItemInputSerializer` | Approved pharmacist owner, draft only | Implemented |
| PATCH, DELETE | `/pharmacist/prescriptions/<prescription_id>/items/<item_id>/` | `update_item`, `delete_item` | `PharmacistPrescriptionItemInputSerializer` | Approved pharmacist owner, draft only | Implemented |
| POST | `/pharmacist/prescriptions/<prescription_id>/items/<item_id>/transcribe-audio/` | `transcribe_audio` | `PharmacistPrescriptionItemAudioTranscriptionSerializer` | Approved pharmacist owner, draft only | Implemented Gemini path |
| POST | `/pharmacist/prescriptions/<prescription_id>/items/<item_id>/approve-transcript/` | `approve_transcript` | `ApproveTranscriptSerializer` | Approved pharmacist owner, draft only | Implemented |
| POST | `/pharmacist/prescriptions/<prescription_id>/items/<item_id>/generate-sign/` | `generate_sign` | Inline | Approved pharmacist owner, draft/submitted only | Implemented gloss-only |
| POST | `/pharmacist/prescriptions/<prescription_id>/submit/` | `submit` | `PharmacistPrescriptionSubmitSerializer` | Approved pharmacist owner | Implemented |
| POST | `/pharmacist/prescriptions/<prescription_id>/confirm/` | `confirm` | Inline | Approved pharmacist owner | Implemented |
| POST | `/pharmacist/prescriptions/<prescription_id>/deliver/` | `deliver` | Inline | Approved pharmacist owner | Implemented |
| POST | `/pharmacist/prescriptions/<prescription_id>/cancel/` | `cancel` | Inline | Approved pharmacist owner | Implemented |
| POST | `/pharmacist/prescriptions/<prescription_id>/archive/` | `archive` | Inline | Approved pharmacist owner | Implemented |

Admin prescription/sign endpoints:

| Method | Path | View/action | Serializer | Permission | Status |
|---|---|---|---|---|---|
| GET | `/admin/prescription-logs/` | `AdminPrescriptionLogViewSet.list` | `AdminPrescriptionLogListSerializer` | Can manage patients | Implemented |
| GET | `/admin/prescription-logs/<pk>/` | `AdminPrescriptionLogViewSet.retrieve` | `AdminPrescriptionLogDetailSerializer` | Can manage patients | Implemented |
| GET | `/admin/sign-quality-reports/` | `AdminSignQualityReportViewSet.list` | `AdminSignQualityReportSerializer` | Can manage patients | Implemented |
| GET, PATCH | `/admin/sign-quality-reports/<pk>/` | `AdminSignQualityReportViewSet.retrieve/partial_update` | `AdminSignQualityReportSerializer`, `AdminSignQualityReportUpdateSerializer` | Can manage patients | Implemented |

Standalone transcription:

| Method | Path | View | Request | Permission | Status |
|---|---|---|---|---|---|
| POST | `/transcriptions/test/` | `TestTranscriptionView` | multipart `audio` | Authenticated approved pharmacist role enforced in view | Implemented test/utility endpoint |

## 9. Authentication and Permissions

Login:

- User login endpoint: `POST /api/auth/login/`.
- Accepts either `email` or `phone_number`/`phone`, plus `password`.
- Returns `user`, `profile`, `access`, `refresh`.
- Blocks inactive users in `LoginSerializer`.
- Blocks pending/rejected users in `AuthViewSet._approval_block_response`.
- Blocks pharmacist users whose `pharmacist_profile.is_approved` is false.

Admin login:

- `POST /api/admin/auth/login/`.
- Same credential serializer, then requires `is_superuser` or role `admin`.
- Returns admin-shaped `user`, `profile`, `access`, `refresh`.

Logout:

- `POST /api/auth/logout/` and `/api/admin/auth/logout/`.
- Requires refresh token body: `{ "refresh": "..." }`.
- Blacklists refresh token using SimpleJWT token blacklist.

Refresh:

- `POST /api/auth/refresh/`.
- Uses `ApprovalAwareTokenRefreshSerializer`.
- Enforces account approval before issuing a new access token.
- Refresh token rotation is enabled.

Registration:

- Patient OTP request: `POST /api/auth/patient/register/request-otp/`.
- Generic OTP request: `POST /api/auth/register/request-otp/` with `role`.
- Pharmacist OTP request: `POST /api/auth/pharmacist/register/request-otp/`.
- Patient registration: `POST /api/auth/patient/register/` and `/auth/patient/self-register/`.
- Pharmacist registration: `POST /api/auth/pharmacist/register/`.
- Both patient and pharmacist self-registration create users with `approval_status = pending`, `is_verified = False`.

OTP:

- Stored in `PhoneOTP` with hashed code, expiry 300 seconds, max 5 attempts.
- Previous unused OTPs for same phone/purpose are marked used when a new OTP is generated.
- Delivery channels: debug and Telegram.
- In `DEBUG=True`, OTP responses include `debug_otp`.
- In production-like settings without provider, request fails.

Roles:

- `admin`
- `pharmacist`
- `patient`

Approval workflow:

- Admin/staff can list, retrieve, approve, reject approval requests based on organization staff capabilities.
- Approving a pharmacist also sets `PharmacistProfile.is_approved = True`.
- Rejecting a pharmacist sets `is_approved = False` and blacklists outstanding tokens for the user.
- Approval-aware authentication blocks pending/rejected non-staff users even when they already have tokens.

Admin/staff:

- `is_admin_role()` allows superuser or `role == admin`.
- Staff organization scoping is implemented in admin dashboard, patient, pharmacy, pharmacist, prescription log, sign quality report, and approval querysets.
- `OrganizationStaffProfile` controls `can_manage_patients` and `can_manage_pharmacists`.

Patient permissions:

- Patient profile/settings/session QR/prescriptions require `IsPatientRole`.
- Patient prescriptions are scoped to own `PatientProfile`.
- Patient sign report endpoint validates item belongs to own prescription.

Pharmacist permissions:

- Prescription workflow uses pharmacist ownership.
- Current session start/list/end uses `IsApprovedPharmacistRole`.
- Some pharmacist profile endpoints use only `IsPharmacistRole`, so approved status is not required for viewing/updating self profile.

## 10. Core Workflows

A. Patient registration and login:

- Sequence: `POST /api/auth/patient/register/request-otp/`, then `POST /api/auth/patient/register/`, then admin approval, then `POST /api/auth/login/`.
- Payload: phone/phone_number, OTP, password, full_name/name, optional email, birth/gender/address/hearing level/record access PIN.
- Result: pending patient account with `PatientProfile`, `PatientMedicalInfo`, generated persistent QR code.
- Risk: registration creates `qr_code_value` before approval; login remains blocked until approval.

B. Pharmacist registration and login:

- Sequence: `POST /api/auth/pharmacist/register/request-otp/`, then `POST /api/auth/pharmacist/register/`, admin approval, then `POST /api/auth/login/`.
- Payload: phone/phone_number, OTP, password, full_name/name, license_number/license_id, either contracted `pharmacy_id` or new pharmacy details.
- Result: pending pharmacist user and `PharmacistProfile`; new pharmacy owner set if created inline.
- Risk: self-created pharmacies are not contracted by default; admin review must reconcile.

C. Admin authentication:

- Sequence: `POST /api/admin/auth/login/`, `GET /api/admin/auth/me/`, optionally `POST /api/admin/auth/logout/`.
- Requires role admin or superuser.
- Response includes user and organization staff profile details where present.

D. OTP flow:

- OTP request creates `PhoneOTP`, hashes code, sends through debug or Telegram.
- Registration validates latest unused OTP by phone/purpose, checks attempts/expiry, marks used on success or lock/expiry.
- Risk: no rate limit/throttle is configured in DRF settings.

E. Patient login QR flow:

- Admin creates token: `POST /api/admin/patients/<patient_id>/login-qr/`.
- Patient logs in: `POST /api/auth/patient/qr-login/` with `qr_token`.
- Admin revokes: `POST /api/admin/patients/<patient_id>/login-qr/revoke/`.
- Alternate legacy payload: `qr_code_value` + `pin`.
- Risk: generated login QR tokens are bearer login credentials until revoked; no expiry field exists on `PatientLoginQR`.

F. Patient session QR flow:

- Patient creates short-lived session token: `POST /api/patients/me/session-qr/`.
- Pharmacist scans: `POST /api/pharmacist/sessions/start-by-qr/` with `qr_token` or `qr_payload`.
- Token is single-use, expires in 300 seconds, and creates a 30-minute active `PatientSession`.
- Risk: active session reuse logic marks a new QR as used and returns existing session if active.

G. Pharmacist starts patient session:

- Current flow: approved pharmacist uses patient-generated session QR.
- Legacy flow: `POST /api/patient-sessions/start-by-qr/` with persistent `qr_code_value`.
- Access is checked by `pharmacist_can_access_patient`: patients without organization are accessible; organization-linked patients require contracted pharmacy in same organization.
- Risk: legacy persistent QR flow bypasses expiring session QR concept.

H. Prescription creation:

- Current flow: `POST /api/pharmacist/prescriptions/`.
- Required: `session_id`, `patient_id`, `doctor_name`, optional doctor specialty, diagnosis, notes, items.
- Requires active session owned by pharmacist, matching patient, not expired.
- Creates draft prescription and optional items.
- Legacy `/api/prescriptions/` create is disabled with a 400 response.

I. Prescription items:

- Add: `POST /api/pharmacist/prescriptions/<id>/items/`.
- Update/delete: `PATCH`/`DELETE /api/pharmacist/prescriptions/<id>/items/<item_id>/`.
- Draft-only.
- Required on create: medication name and pricing (`unit_price` or legacy `price`).
- Supports image upload and quantity/price line totals.

J. Audio upload / transcription:

- Current prescription item transcription: `POST /api/pharmacist/prescriptions/<id>/items/<item_id>/transcribe-audio/` multipart with `audio`, `audio_file`, or `voice`.
- Saves audio, marks processing, calls `transcriptions.services.transcribe_audio_file`, stores raw transcript and provider/model.
- Requires draft prescription.
- Legacy item transcription: `POST /api/prescriptions/items/<pk>/transcribe/`, using `PRESCRIPTION_TRANSCRIPTION_BACKEND` placeholder/failing backend.
- Standalone test: `POST /api/transcriptions/test/`.

K. Transcript approval:

- `POST /api/pharmacist/prescriptions/<id>/items/<item_id>/approve-transcript/`.
- Body: `{ "approved_instruction_text": "..." }`.
- Draft-only.
- Stores edited transcript and returns `transcription_status = "approved"` in response, while model status remains `completed`.

L. Gloss/sign/video generation:

- `POST /api/pharmacist/prescriptions/<id>/items/<item_id>/generate-sign/`.
- Uses edited transcript, raw transcript, or instructions text.
- Calls Gemini sign model and stores generated gloss in `supporting_text`.
- Returns `video_url: null`, `output_type: gloss_only`, `video_generation_supported: false`.
- No actual sign-language video generation is implemented.

M. Prescription status transitions:

- Implemented in `PRESCRIPTION_STATUS_TRANSITIONS` in `prescriptions/views.py`.
- Allowed:
  - `draft -> submitted`
  - `submitted -> confirmed` or `cancelled`
  - `confirmed -> delivered` or `cancelled`
  - `delivered -> archived`
  - `cancelled -> archived`
  - `archived -> none`
- `submit` requires at least one item.
- Submitted/delivered timestamps are set on transition.

N. Patient prescription viewing:

- List/detail under `/api/patients/me/prescriptions/`.
- Excludes drafts unless `include_drafts=true`.
- Logs view access on detail.

O. Admin management flows:

- Admin auth/me/logout/dashboard exists.
- Admin patients CRUD is soft delete.
- Admin pharmacies CRUD is implemented, hard delete blocked when related records exist.
- Admin pharmacists CRUD is implemented, delete deactivates user and marks profile unapproved.
- Admin approval/rejection exists.
- Admin QR code generation/revocation exists.
- Admin prescription logs and sign quality reports exist.
- Organization CRUD API, settings API, and analytics/report export APIs are missing.

## 11. Admin Backend Support

| Feature | Status | Endpoint(s) | Files | Needed |
|---|---|---|---|---|
| Admin login | Exists fully | `/api/admin/auth/login/` | `accounts/urls.py`, `accounts/views.py` | Harden throttling/audit logs |
| Admin me/profile | Exists fully | `/api/admin/auth/me/` | `accounts/views.py` | None urgent |
| Admin logout | Exists fully | `/api/admin/auth/logout/` | `accounts/views.py` | None urgent |
| Dashboard stats | Exists partially | `/api/admin/dashboard/stats/` | `accounts/views.py` | Real city/region/location dimensions |
| Patients CRUD | Exists mostly | `/api/admin/patients/`, `/api/admin/patients/<pk>/` | `patients/views.py`, `patients/serializers.py` | Clarify soft delete contract |
| Pharmacists CRUD | Exists mostly | `/api/admin/pharmacists/`, `/api/admin/pharmacists/<pk>/` | `pharmacies/views.py` | Clarify delete/deactivate semantics |
| Pharmacies CRUD | Exists mostly | `/api/admin/pharmacies/`, `/api/admin/pharmacies/<pk>/` | `pharmacies/views.py` | Add real city/region/status/license/notes if frontend requires |
| Registration approval/rejection | Exists fully | `/api/admin/approval-requests/...`, legacy `/api/admin/users/...` | `accounts/views.py` | Deprecate duplicate legacy routes |
| QR generation/revocation | Exists partially | `/api/admin/qr-codes/...`, `/api/admin/patients/<id>/login-qr/...` | `patients/views.py` | Add login QR expiry and audit trail if needed |
| Prescription logs | Exists fully | `/api/admin/prescription-logs/` | `prescriptions/views.py` | Add export if required |
| Sign quality reports | Exists fully | `/api/admin/sign-quality-reports/` | `prescriptions/views.py` | Add comment/resolution metadata if needed |
| Settings | Missing | none found | none | Define model/API |
| Reports/analytics | Exists partially | dashboard stats only | `accounts/views.py` | Add reporting/export/filter dimensions |
| Organizations CRUD | Missing API | none found | `organizations/models.py`, `serializers.py`, `admin.py` | Add URL/viewset if admin UI needs it |

## 12. Tests

Test files:

- `accounts/tests.py`
  - OTP delivery, Telegram safety, registration OTP, patient/pharmacist registration, login approval blocks, token refresh approval behavior, logout/token blacklist, admin auth/me/dashboard, approval request list/detail/approve/reject.
- `patients/tests.py`
  - Legacy QR session flow, patient me/settings, admin patient account creation, login QR generation/revocation/login, patient session QR flow, pharmacist session list/start/end, admin patient/QR management, staff organization scoping.
- `pharmacies/tests.py`
  - Pharmacy scoping, pharmacist self endpoints, public/patient contracted pharmacy list, admin pharmacy CRUD, admin pharmacist CRUD.
- `prescriptions/tests.py`
  - Prescription permissions, patient prescription access, legacy disabled create, sign quality reports, admin prescription logs, pharmacist prescription workflow, lifecycle transitions, media upload validation/storage, transcription pipeline, sign/gloss generation behavior.
- `transcriptions/tests.py`
  - Gemini transcription service behavior, error sanitization, standalone transcription endpoint permissions, validation, provider failure.

Workflows covered:

- OTP registration and delivery safety.
- Approval-gated login and token refresh.
- Admin auth and dashboard.
- Patient/pharmacist/admin role permissions.
- QR login and session QR flows.
- Prescription lifecycle and item/media/transcription/sign quality flows.
- Admin management for patients/pharmacies/pharmacists/approvals/logs/reports.

Workflows not fully covered or unclear from inspected tests:

- Full production deployment settings behavior.
- Real external Telegram/Gemini integration beyond mocks.
- Organization CRUD API, because no API exists.
- Real sign-language video generation, because implementation is gloss-only.
- Concurrency/race conditions for single-use QR token scanning.
- API throttling/rate limiting, because no throttling config exists.

Verification command:

- `python manage.py test`
- Attempted result: discovered 263 tests and reported no system check issues, but timed out after 120 seconds before completion.

## 13. Bugs, Risks, and Gaps

1. Secret exposure risk in `.env`
   - Files: `.env`, `pharmasign/settings.py`, `accounts/otp_delivery.py`, `transcriptions/services.py`.
   - `.env` contains live-looking Telegram/Gemini credentials. Rotate them and keep `.env` out of source control.

2. No API throttling configured for OTP/login
   - Files: `pharmasign/settings.py`, `accounts/views.py`, `accounts/services.py`.
   - OTP and login endpoints are public and no DRF throttling/rate limit is configured.

3. Login QR tokens do not expire
   - Files: `patients/models.py`, `patients/services.py`, `accounts/serializers.py`.
   - `PatientLoginQR` has `is_active` and `revoked_at` but no `expires_at`. A leaked active token remains usable until manual revocation.

4. Legacy persistent QR session start remains active
   - Files: `patients/urls.py`, `patients/views.py`.
   - `/api/patient-sessions/start-by-qr/` uses persistent `PatientProfile.qr_code_value`, while the newer flow uses expiring single-use `PatientSessionQR`.

5. Organization APIs are missing
   - Files: `organizations/models.py`, `organizations/serializers.py`, `pharmasign/api_urls.py`.
   - Models/serializers/admin exist, but no `organizations/urls.py` or views are exposed.

6. Admin placeholder fields may create unstable contracts
   - Files: `patients/serializers.py`, `pharmacies/serializers.py`, `accounts/views.py`.
   - Fields such as `city`, `region`, `diagnosis`, `license_number`, `status`, `notes`, and `patients_by_city` are returned as `None` or empty arrays because no backing fields exist.

7. Gloss generation is not video generation
   - Files: `prescriptions/views.py`, `prescriptions/services.py`, `prescriptions/serializers.py`.
   - `generate-sign` stores gloss text only and always returns `video_url: null`.

8. Duplicate/legacy prescription transcription paths
   - Files: `prescriptions/urls.py`, `prescriptions/views.py`, `prescriptions/transcription.py`, `transcriptions/services.py`.
   - Legacy `/api/prescriptions/items/<pk>/transcribe/` uses placeholder/failing backend; current `/api/pharmacist/.../transcribe-audio/` uses Gemini.

9. Router-resolved methods can look broader than allowed methods
   - Files: `patients/urls.py`, `pharmacies/urls.py`, `prescriptions/urls.py`.
   - DRF routers show mappings for PUT/DELETE in URL resolution for some ViewSets, while `http_method_names` restricts actual allowed methods. This can confuse generated API docs.

10. Token rotation may not blacklist old refresh tokens after refresh
   - File: `pharmasign/settings.py`, `accounts/jwt.py`.
   - `ROTATE_REFRESH_TOKENS=True`, but `BLACKLIST_AFTER_ROTATION` is not explicitly configured.

11. Approval-aware authentication bypasses approval checks for staff/superusers
   - File: `accounts/authentication.py`.
   - Intended for admin access, but admin-role non-staff users rely on `is_admin_role`, not staff. Review whether all admin role users should bypass approval.

12. Delete semantics are inconsistent
   - Files: `patients/views.py`, `pharmacies/views.py`.
   - Admin patient/pharmacist delete soft-deactivates users. Admin pharmacy delete hard-deletes only when unlinked.

13. Test command did not complete within timeout
   - Files: `accounts/tests.py`, `patients/tests.py`, `pharmacies/tests.py`, `prescriptions/tests.py`, `transcriptions/tests.py`.
   - Full green status is not confirmed in this audit run.

## 14. Priority Backend Fix Plan

| Task title | Files likely affected | Why it matters | Expected result | Risk level |
|---|---|---|---|---|
| Rotate leaked secrets and remove `.env` from source control | `.env`, `.gitignore`, deployment env config | Prevents live provider credentials from being abused | Secrets rotated, `.env` untracked, `.env.example` remains safe | High |
| Add throttling for OTP and login | `pharmasign/settings.py`, `accounts/views.py`, tests | Public auth endpoints are abuse targets | Rate limits for OTP request, login, QR login | High |
| Add expiry to patient login QR tokens | `patients/models.py`, migration, `patients/services.py`, `accounts/serializers.py`, tests | Active login QR is a bearer credential with no expiry | Login QR includes expiry and rejects expired tokens | High |
| Deprecate or protect legacy persistent QR session endpoint | `patients/urls.py`, `patients/views.py`, tests/docs | Persistent QR conflicts with safer single-use session QR flow | Clear migration path or stricter permissions/audit for legacy endpoint | High |
| Consolidate transcription paths | `prescriptions/urls.py`, `prescriptions/views.py`, `prescriptions/transcription.py`, `transcriptions/services.py`, tests | Two backends create inconsistent behavior | One documented transcription pipeline with stable responses | Medium |
| Add organization admin API or document as intentionally admin-site only | `organizations/views.py`, `organizations/urls.py`, `pharmasign/api_urls.py`, tests | Existing models/serializers are not reachable by API | Admin UI can manage organizations through supported API if needed | Medium |
| Replace placeholder admin fields with real fields or remove from contract | `patients/models.py`, `pharmacies/models.py`, serializers, migrations, tests | `None` placeholders make frontend contracts unstable | Either real city/region/status fields or explicit documented absence | Medium |
| Make sign generation contract explicit | `prescriptions/views.py`, `prescriptions/serializers.py`, tests/docs | Endpoint name implies video/sign generation but returns gloss only | API contract states gloss-only or adds real video generation pipeline | Medium |
| Configure refresh token blacklist after rotation | `pharmasign/settings.py`, tests | Reduces refresh token replay window | Old refresh token is blacklisted when rotated | Medium |
| Clarify delete semantics across admin APIs | `patients/views.py`, `pharmacies/views.py`, docs/tests | Avoid accidental hard delete or inconsistent UI expectations | Consistent soft-delete/archive policy or documented exceptions | Low |

## 15. Recommended Next Steps

1. Immediately rotate the credentials currently present in `.env`, then ensure `.env` is not committed or distributed.
2. Run `python manage.py test` with a longer timeout and record the final result.
3. Decide whether the legacy persistent QR and legacy prescription endpoints should remain public API, be marked deprecated, or be removed.
4. Add throttling and login/OTP audit logging before production exposure.
5. Stabilize the admin contract: either implement organization/location/settings/reporting fields or remove placeholder fields from API responses.
6. Document the current prescription workflow as session-required and make `/api/pharmacist/prescriptions/` the canonical creation path.
