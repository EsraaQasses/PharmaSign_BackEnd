# Admin Backend Discovery

Discovery date: 2026-05-13

Scope: backend only. No backend implementation, endpoint creation, migrations, or frontend changes were performed.

## 1. Existing Backend Architecture

### Project API Routing

- Root API include: `pharmasign/urls.py` mounts `pharmasign.api_urls` at `/api/`.
- API modules included from `pharmasign/api_urls.py`:
  - `accounts.urls`
  - `patients.urls`
  - `pharmacies.urls`
  - `prescriptions.urls`
  - `transcriptions.urls` under `/api/transcriptions/`
- DRF defaults in `pharmasign/settings.py`:
  - Authentication: `accounts.authentication.ApprovalAwareJWTAuthentication`
  - Default permission: `IsAuthenticated`
  - Pagination: `PageNumberPagination`, page size `20`
- JWT refresh is approval-aware through `accounts.jwt.ApprovalAwareTokenRefreshView`.

### accounts

Files:

- Models: `accounts/models.py`
- Serializers: `accounts/serializers.py`
- Views: `accounts/views.py`
- URLs: `accounts/urls.py`
- Auth/JWT: `accounts/authentication.py`, `accounts/jwt.py`
- Services: `accounts/services.py`
- Tests: `accounts/tests.py`

Models:

- `User`
  - Custom auth model.
  - Fields relevant to admin: `email`, `phone_number`, `role`, `is_staff`, `is_active`, `is_verified`, `approval_status`, `approved_at`, `approved_by`, `rejection_reason`, `created_at`, `updated_at`.
  - Roles come from `common.choices.RoleChoices`: `admin`, `pharmacist`, `patient`.
  - Approval status comes from `common.choices.ApprovalStatusChoices`: `pending`, `approved`, `rejected`.
- `PhoneOTP`
  - Registration OTP challenge for patient/pharmacist registration.

Serializers:

- `UserSerializer`
- `LoginSerializer`
- `LogoutSerializer`
- `AuthMeSerializer`
- `ChangePasswordSerializer`
- `RegistrationOTPRequestSerializer`
- `PatientRegistrationOTPRequestSerializer`
- `PatientQRLoginSerializer`
- `PatientSelfRegisterSerializer`
- Compatibility payload builders:
  - `build_compat_user_payload`
  - `build_compat_patient_profile_payload`
  - `build_compat_pharmacy_payload`
  - `build_compat_pharmacist_profile_payload`

Views:

- `AuthViewSet`
  - Login/logout/me/change-password.
  - Patient/pharmacist registration and OTP request.
  - Admin registration request list.
  - Admin user approve/reject actions.

Permissions/authorization:

- Public actions use `AllowAny`.
- Protected actions use `IsAuthenticated`.
- Admin registration management is implemented inside `AuthViewSet` via:
  - `_can_manage_registration_requests`
  - `_manageable_registration_roles`
  - `_can_manage_user_role`
- Approval-aware JWT authentication blocks non-staff pending/rejected/inactive users.

URLs:

- `POST /api/auth/login/`, URL name `accounts:login`
- `POST /api/auth/logout/`, URL name `accounts:logout`
- `GET /api/auth/me/`, URL name `accounts:me`
- `POST /api/auth/refresh/`, URL name `accounts:token_refresh`
- `POST /api/auth/change-password/`, URL name `accounts:change_password`
- `GET /api/admin/registration-requests/`, URL name `accounts:registration_requests`
- `POST /api/admin/users/<pk>/approve/`, URL name `accounts:approve_user`
- `POST /api/admin/users/<pk>/reject/`, URL name `accounts:reject_user`
- Registration and OTP endpoints under `/api/auth/...`

Tests:

- `accounts/tests.py` covers login, approval gating, JWT protected access, and admin approve/reject flows.

### common

Files:

- Permissions: `common/permissions.py`
- Choices: `common/choices.py`
- Utilities: `common/utils.py`
- Base model: `common/models.py`

Permissions:

- `IsAdminRole`
- `IsPharmacistRole`
- `IsPatientRole`
- `CanManagePatients`
- `CanManagePharmacists`
- `IsAdminOrPharmacistRole`
- `IsApprovedPharmacistRole`

Important helpers:

- `is_admin_role(user)` returns true for authenticated superuser or `role == admin`.
- `has_patient_management_access(user)` requires admin role and, if organization staff profile exists, `can_manage_patients`.
- `has_pharmacist_management_access(user)` requires admin role and, if organization staff profile exists, `can_manage_pharmacists`.
- `pharmacist_can_access_patient(user, patient_profile)` scopes pharmacist patient access by organization/contracted pharmacy.

### organizations

Files:

- Models: `organizations/models.py`
- Serializers: `organizations/serializers.py`
- Admin: `organizations/admin.py`
- No `organizations/views.py` or `organizations/urls.py` found.

Models:

- `Organization`
  - Fields: `name`, `description`, `phone`, `address`, `created_at`, `updated_at`.
- `OrganizationStaffProfile`
  - Fields: `user`, `organization`, `job_title`, `can_manage_patients`, `can_manage_pharmacists`, `created_at`, `updated_at`.
  - Requires linked `User.role == admin`.

Serializers:

- `OrganizationSerializer`
- `OrganizationStaffProfileSerializer`

Endpoints:

- Missing. No organization/settings REST endpoint exists.

### patients

Files:

- Models: `patients/models.py`
- Serializers: `patients/serializers.py`
- Views: `patients/views.py`
- URLs: `patients/urls.py`
- Services: `patients/services.py`
- Tests: `patients/tests.py`

Models:

- `PatientProfile`
  - Fields: `user`, `organization`, `full_name`, `phone_number`, `birth_date`, `gender`, `address`, `hearing_disability_level`, `is_self_registered`, `qr_code_value`, `qr_is_active`, `record_access_pin_hash`, `created_at`, `updated_at`.
- `PatientEnrollment`
  - Organization-driven enrollment record before account creation.
  - Fields: `organization`, `patient_profile`, `join_date`, `first_name`, `last_name`, `father_name`, `mother_name`, `birth_date`, `gender`, `address`, `phone_number`, `hearing_disability_level`, `notes`, `is_account_created`, `created_by`, timestamps.
- `PatientMedicalInfo`
  - Fields: `patient`, `blood_type`, `chronic_conditions`, `allergies`, `is_pregnant`, `is_breastfeeding`, `notes`.
- `PatientSettings`
  - Patient self settings only.
- `PatientLoginQR`
  - Persistent login QR token hash, active/revoked state.
- `PatientSessionQR`
  - Short-lived patient session QR token hash.
- `PatientSession`
  - Patient-pharmacist-pharmacy session created after QR scan.

Serializers:

- `PatientProfileSerializer`
- `PatientMedicalInfoSerializer`
- `PatientSelfProfileSerializer`
- `PatientSettingsSerializer`
- `PatientEnrollmentSerializer`
- `CreatePatientAccountSerializer`
- `AdminPatientCreateAccountSerializer`
- `GeneratePatientQRSerializer`
- `PatientLoginQRSerializer`
- `GeneratePatientLoginQRSerializer`
- `RevokePatientLoginQRSerializer`
- `GeneratePatientSessionQRSerializer`
- `StartPatientSessionByQRSerializer`
- `PatientSessionSerializer`
- `PharmacistPatientSessionSerializer`

Views:

- `PatientEnrollmentViewSet`
  - CRUD-limited enrollment management: list/create/retrieve/patch, no delete.
  - Admin/scoped through `CanManagePatients`.
- `PatientManagementViewSet`
  - Only retrieve mixin plus `generate_qr` action. No list/update/delete wired.
- `AdminPatientAccountViewSet`
  - Admin patient account creation.
- `AdminPatientLoginQRViewSet`
  - Generate/revoke persistent login QR for a patient.
- Patient self/profile/settings and pharmacist session flows.

URLs:

- `GET/POST/PATCH /api/patients/enrollments/`, URL basename `patient-enrollment`
- `POST /api/patients/enrollments/<id>/create-account/`
- `POST /api/admin/patients/create-account/`, URL name `admin-patient-create-account`
- `POST /api/admin/patients/<patient_id>/login-qr/`, URL name `admin-patient-login-qr`
- `POST /api/admin/patients/<patient_id>/login-qr/revoke/`, URL name `admin-patient-login-qr-revoke`
- `POST /api/patients/<pk>/generate-qr/`, URL name `patient-generate-qr`
- Patient self/session endpoints under `/api/patients/me/...`, `/api/pharmacist/sessions/...`

Services:

- `assign_patient_qr_code`
- `generate_patient_login_qr`
- `revoke_patient_login_qr`
- `generate_patient_session_qr`
- `create_patient_account_from_enrollment`
- `build_patient_summary`

Tests:

- `patients/tests.py` covers patient session flow, patient login QR generation/revocation, organization staff scoping, and session QR flow.

### pharmacies / pharmacists

Files:

- Models: `pharmacies/models.py`
- Serializers: `pharmacies/serializers.py`
- Views: `pharmacies/views.py`
- URLs: `pharmacies/urls.py`
- Tests: `pharmacies/tests.py`

Models:

- `Pharmacy`
  - Fields: `name`, `owner_user`, `address`, `latitude`, `longitude`, `is_contracted_with_organization`, `organization`, `phone_number`, timestamps.
  - No explicit `license_number`, `city`, `region`, `status`, or `notes`.
- `PharmacistProfile`
  - Fields: `user`, `pharmacy`, `full_name`, `license_number`, `is_approved`, timestamps.
  - Account status lives on linked `User`.

Serializers:

- `PharmacySerializer`
- `PharmacyCompatSerializer`
- `SafePharmacySerializer`
- `PharmacistProfileSerializer`
- `PharmacistRegisterSerializer`
- `PharmacistMeUpdateSerializer`

Views:

- `PharmacyViewSet`
  - `ModelViewSet` but `http_method_names = ["get", "post", "head", "options"]`.
  - Supports list/retrieve/create only. No update/delete.
  - Admins need `CanManagePharmacists`; pharmacists see only own pharmacy.
  - `contracted` action lists contracted pharmacies.
- `PublicContractedPharmacyViewSet`
- `PatientPharmacyViewSet`
- `PharmacistProfileViewSet`
  - Pharmacist self retrieve/update only.
- `PharmacistPharmacyViewSet`
  - Pharmacist self pharmacy retrieve/update compatibility endpoint.

URLs:

- `GET/POST /api/pharmacies/`, URL basename `pharmacy`
- `GET /api/pharmacies/<id>/`
- `GET /api/pharmacies/contracted/`
- `GET /api/auth/contracted-pharmacies/`
- `GET /api/patients/pharmacies/`
- `GET/PATCH /api/pharmacists/me/`
- `GET/PATCH /api/pharmacist/me/`
- `GET/PATCH /api/pharmacist/me/pharmacy/`

Tests:

- `pharmacies/tests.py` covers pharmacy scoping, staff permission denial, pharmacist self endpoints, public/patient contracted pharmacy lists.

### prescriptions

Files:

- Models: `prescriptions/models.py`
- Serializers: `prescriptions/serializers.py`
- Views: `prescriptions/views.py`
- URLs: `prescriptions/urls.py`
- Services: `prescriptions/services.py`
- Constants: `prescriptions/constants.py`
- Tests: `prescriptions/tests.py`

Models:

- `Prescription`
  - Fields: `patient`, `pharmacist`, `pharmacy`, `session`, `doctor_name`, `doctor_specialty`, `diagnosis`, `status`, `prescribed_at`, `submitted_at`, `delivered_at`, `notes`, `reused_from`, timestamps.
- `PrescriptionItem`
  - Fields include medicine details, media files, transcription status/provider/timestamps/error, raw/edited transcript, sign video, supporting text/gloss, sign status, confirmation flag, timestamps.
- `SignQualityReport`
  - Fields: `patient`, `prescription`, `prescription_item`, `medicine_name`, `approved_instruction_text`, `report_type`, `status`, timestamps.
  - Status choices: `open`, `reviewed`, `resolved`, `dismissed`.
  - No `reviewer_notes` field.
- `PrescriptionAccessLog`
  - Fields: `prescription`, `accessed_by`, `access_type`, `timestamp`.

Serializers:

- Prescription:
  - `PrescriptionSerializer`
  - `PrescriptionCreateSerializer`
  - `PharmacistPrescriptionSerializer`
  - `PharmacistPrescriptionListSerializer`
  - `PharmacistPrescriptionCreateSerializer`
  - `PharmacistPrescriptionUpdateSerializer`
  - `PharmacistPrescriptionSubmitSerializer`
- Items/transcription/sign:
  - `PrescriptionItemSerializer`
  - `PrescriptionItemContractSerializer`
  - `PrescriptionItemCreateSerializer`
  - `PrescriptionItemUpdateSerializer`
  - `PharmacistPrescriptionItemInputSerializer`
  - `PharmacistPrescriptionItemAudioTranscriptionSerializer`
  - `ApproveTranscriptSerializer`
  - `TranscribedPrescriptionItemSerializer`
- Sign quality:
  - `SignQualityReportSerializer`
  - `PatientSignQualityReportCreateSerializer`
  - `AdminSignQualityReportSerializer`
  - `AdminSignQualityReportUpdateSerializer`

Views:

- `PrescriptionViewSet`
  - Admins with patient-management permission can retrieve prescriptions and router list is available through `ListModelMixin`? No: class uses `CreateModelMixin`, `RetrieveModelMixin`, `GenericViewSet`, so list is not implemented despite router list URL.
  - Retrieve logs `PrescriptionAccessLog`.
- `PrescriptionItemViewSet`
  - Pharmacist item patch/transcribe.
- `PharmacistPrescriptionViewSet`
  - Pharmacist list/create/retrieve/update/items/transcription/sign generation/status transitions.
- `PatientPrescriptionViewSet`
  - Patient list/detail.
- `PatientSignQualityReportViewSet`
  - Patient creates sign quality report for a prescription item.
- `AdminSignQualityReportViewSet`
  - Admin list/detail/patch status for sign quality reports.

URLs:

- Router:
  - `/api/prescriptions/`
  - `/api/prescriptions/<id>/`
  - `/api/prescriptions/items/<id>/`
  - `/api/patients/me/prescriptions/`
- Admin sign quality:
  - `GET /api/admin/sign-quality-reports/`, URL name `admin-sign-quality-report-list`
  - `GET/PATCH /api/admin/sign-quality-reports/<pk>/`, URL name `admin-sign-quality-report-detail`
- Patient sign report:
  - `POST /api/patients/me/prescriptions/items/<item_id>/report-sign-issue/`
- Pharmacist workflow:
  - `/api/pharmacist/prescriptions/`
  - `/api/pharmacist/prescriptions/<prescription_id>/`
  - `/api/pharmacist/prescriptions/<prescription_id>/items/`
  - `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/`
  - `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/transcribe-audio/`
  - `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/approve-transcript/`
  - `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/generate-sign/`
  - `/api/pharmacist/prescriptions/<prescription_id>/submit|confirm|deliver|cancel|archive/`

Services:

- `log_prescription_access`
- `transcribe_prescription_item`
- `generate_sign_gloss`
- `mark_prescription_item_sign_processing`
- `mark_prescription_item_sign_completed`
- `mark_prescription_item_sign_failed`

Tests:

- `prescriptions/tests.py` covers prescription permissions, sign quality reports, pharmacist prescription MVP, media uploads, and transcription pipeline.

### transcriptions / sign generation

Files:

- Views: `transcriptions/views.py`
- URLs: `transcriptions/urls.py`
- Services: `transcriptions/services.py`
- Validators: `transcriptions/validators.py`
- Exceptions: `transcriptions/exceptions.py`
- Tests: `transcriptions/tests.py`

Models:

- None found.

Views:

- `TestTranscriptionView`
  - `POST /api/transcriptions/test/`
  - Requires authenticated approved pharmacist role.
  - Upload field: `audio`.
  - Calls Gemini transcription service.

Services:

- `transcribe_audio_file`
- `transcribe_audio_file_with_gemini`
- `get_gemini_modules`

Sign generation lives mostly in `prescriptions/services.py` and `PharmacistPrescriptionViewSet.generate_sign`.

### Approval Workflow

Existing approval model:

- No separate `ApprovalRequest` model exists.
- Approval request state is currently represented by `accounts.User.approval_status`, with related `PatientProfile` or `PharmacistProfile`.
- Approve/reject endpoints update `User.approval_status`; pharmacist approval also updates `PharmacistProfile.is_approved`.

Existing approval endpoints:

- `GET /api/admin/registration-requests/`
- `POST /api/admin/users/<pk>/approve/`
- `POST /api/admin/users/<pk>/reject/`

Limitations:

- Registration request list only returns basic user fields, not joined patient/pharmacist/pharmacy detail.
- No detail endpoint for one approval request.
- No request type abstraction beyond `User.role`.

### Reports / Statistics

- No report/statistics app found.
- No dashboard stats endpoint found.
- Counts can be computed from existing models but are not exposed as an API.

### Organization / Settings

- `Organization` and `OrganizationStaffProfile` models exist.
- Serializers exist.
- No REST views/urls exist.
- Patient-only settings exist at `PatientSettings`; this does not support admin organization settings.

## 2. Existing Endpoints That Can Support Admin Frontend

| Feature | Existing endpoint | Method | View/Serializer | Auth/permission | Response shape summary | Can admin frontend use it? | Notes |
|---|---|---:|---|---|---|---|---|
| Admin/staff login/auth | `/api/auth/login/` | POST | `AuthViewSet.login` / `LoginSerializer`, `AuthMeSerializer` | `AllowAny`; approval block for pending/rejected | `{user, profile, access, refresh}` | Partial | Does not enforce admin role at login; frontend must call `me` and verify `user.role == admin` or add admin-specific login wrapper. |
| Current user/profile | `/api/auth/me/` | GET | `AuthViewSet.me` / `AuthMeSerializer` | `IsAuthenticated`; approval-aware JWT | `{user, profile}` | Yes | Good for role verification. Admin organization staff profile is included through `UserSerializer`, but `AuthMeSerializer` currently only builds patient/pharmacist profile; admin `profile` is `{}`. |
| Logout | `/api/auth/logout/` | POST | `AuthViewSet.logout` / `LogoutSerializer` | `IsAuthenticated` | `{detail}` | Yes | Requires refresh token body. |
| Patient list | Missing | GET | N/A | Should be `IsAuthenticated + CanManagePatients` | N/A | No | `PatientManagementViewSet` has no list route. |
| Patient detail | `/api/prescriptions/<id>/` is not patient detail; `/api/patients/<pk>/generate-qr/` has object lookup only | GET | N/A | N/A | N/A | No | No patient detail endpoint is wired. |
| Patient create | `/api/admin/patients/create-account/` | POST | `AdminPatientAccountViewSet.create_account` / `AdminPatientCreateAccountSerializer` | `IsAuthenticated + CanManagePatients` | `{user, profile, temporary_password_generated, temporary_password?}` | Partial | Creates patient account, not full admin CRUD. Missing city/region/diagnosis/current medications/account status controls. |
| Patient update/delete | Missing | PATCH/DELETE | N/A | Should be `CanManagePatients` | N/A | No | No admin patient update/delete endpoints. |
| Patient QR generation/status | `/api/patients/<pk>/generate-qr/` | POST | `PatientManagementViewSet.generate_qr` / `GeneratePatientQRSerializer` | `IsAuthenticated + CanManagePatients` | `{qr_code_value, qr_is_active}` | Partial | Generates profile QR. No list/status endpoint. |
| Patient login QR generate | `/api/admin/patients/<patient_id>/login-qr/` | POST | `AdminPatientLoginQRViewSet.generate` / `GeneratePatientLoginQRSerializer` | `IsAuthenticated + CanManagePatients` | `{patient_id, qr_token, qr_payload, is_active, created_at, revoked_at}` | Partial | Token is only returned at generation. Stored hash is not returned. |
| Patient login QR revoke | `/api/admin/patients/<patient_id>/login-qr/revoke/` | POST | `AdminPatientLoginQRViewSet.revoke` / `RevokePatientLoginQRSerializer` | `IsAuthenticated + CanManagePatients` | `{patient_id, is_active: false}` | Partial | No reactivate; regenerate is same as generate. |
| Pharmacist list/detail/create/update/delete | Missing | GET/POST/PATCH/DELETE | N/A | Should be `CanManagePharmacists` | N/A | No | Only pharmacist self endpoints exist. Approval list can expose pending pharmacists but not CRUD. |
| Pharmacy list/detail/create | `/api/pharmacies/`, `/api/pharmacies/<id>/` | GET/POST | `PharmacyViewSet` / `PharmacySerializer` | Admin: `IsAuthenticated + CanManagePharmacists`; pharmacist scoped otherwise | Paginated list/detail with model fields | Partial | Admin can list/detail/create if `CanManagePharmacists`. No PATCH/DELETE due `http_method_names`. |
| Pharmacy update/delete | Missing | PATCH/DELETE | N/A | Should be `CanManagePharmacists` | N/A | No | Existing `PharmacyViewSet` blocks update/delete. |
| Contracted pharmacies | `/api/pharmacies/contracted/` | GET | `PharmacyViewSet.contracted` / `PharmacySerializer` | Admin/pharmacist rules from `PharmacyViewSet` | Paginated contracted pharmacies | Partial | Admin use possible with manage-pharmacists permission. |
| Public contracted pharmacies | `/api/auth/contracted-pharmacies/` | GET | `PublicContractedPharmacyViewSet` / `SafePharmacySerializer` | `AllowAny` | List of safe contracted pharmacy fields | No for protected admin | Useful for registration selector, not admin dashboard. |
| Pharmacist approval | `/api/admin/users/<pk>/approve/` | POST | `AuthViewSet.approve_user` | Authenticated admin/staff with manageable role | `{detail, user}` | Yes | Reuses user approval; also sets `PharmacistProfile.is_approved = true`. |
| Pharmacist rejection | `/api/admin/users/<pk>/reject/` | POST | `AuthViewSet.reject_user` | Authenticated admin/staff with manageable role | `{detail, user}` | Yes | Body uses `reason`, not `rejectionReason`. Blacklists tokens. |
| Patient approval | `/api/admin/users/<pk>/approve/`, `/api/admin/users/<pk>/reject/` | POST | `AuthViewSet` | Authenticated admin/staff with manageable role | `{detail, user}` | Yes | Same User workflow supports patient role. |
| Approval request list | `/api/admin/registration-requests/` | GET | `AuthViewSet.registration_requests` | Authenticated admin/staff with manageable role | Array of `{id,email,phone_number,role,approval_status,created_at}` | Partial | No pagination, no joined detail, no pharmacy/license info. |
| Approval request detail | Missing | GET | N/A | Should be admin/staff scoped | N/A | No | Need detail serializer joining patient/pharmacist/pharmacy. |
| QR list | Missing | GET | N/A | Should be `CanManagePatients` | N/A | No | Models exist: `PatientProfile.qr_code_value`, `PatientLoginQR`, `PatientSessionQR`. |
| QR regenerate | `/api/admin/patients/<patient_id>/login-qr/` and `/api/patients/<pk>/generate-qr/` | POST | QR serializers | `CanManagePatients` | Token or profile QR payload | Partial | No unified QR resource or regenerate action by QR id. |
| QR disable/reactivate | `/api/admin/patients/<patient_id>/login-qr/revoke/` | POST | `RevokePatientLoginQRSerializer` | `CanManagePatients` | `{patient_id,is_active:false}` | Partial | Disable exists for active login QR. Reactivate missing. |
| Prescription list/detail/logs | `/api/prescriptions/<id>/` | GET | `PrescriptionViewSet.retrieve` / `PrescriptionSerializer` | Admin with `CanManagePatients`, patient, or approved pharmacist scoped | Prescription detail with nested items | Partial | Detail usable. List is not implemented by the viewset. No access log list endpoint. |
| Prescription medicines/items | Nested in prescription detail; pharmacist item endpoints | GET/PATCH/POST | Prescription item serializers | Role scoped | Item details with transcript/sign fields | Partial | Admin read via detail only; no admin item update workflow. |
| Audio/transcription/gloss/sign records | Pharmacist item transcription/sign endpoints | POST | `PharmacistPrescriptionViewSet` serializers | `IsAuthenticated + IsPharmacistRole`; approved enforced inside methods | Transcription/sign generation payloads | No for admin | Pharmacist workflow endpoints are not admin monitoring APIs. |
| Standalone transcription test | `/api/transcriptions/test/` | POST | `TestTranscriptionView` | Approved pharmacist only | `{status,provider,model,transcript}` | No | Not an admin endpoint. |
| Sign quality report records | `/api/admin/sign-quality-reports/`, `/api/admin/sign-quality-reports/<pk>/` | GET/PATCH | `AdminSignQualityReportViewSet` / `AdminSignQualityReportSerializer`, `AdminSignQualityReportUpdateSerializer` | `IsAuthenticated + CanManagePatients` | Paginated reports with patient summary and status | Partial | Strong existing base. Missing pharmacy/pharmacist, reviewer notes, grouped medicines shape. |
| Dashboard statistics | Missing | GET | N/A | Should be admin protected | N/A | No | Counts can be computed from existing models. |
| Reports/export | Missing | GET | N/A | Should be admin protected | N/A | No | No reports/export module found. |
| Settings/organization profile | Missing | GET/PATCH | `OrganizationSerializer` exists but no view | Should be admin protected and org-scoped | N/A | No | Model exists; endpoint missing. |

## 3. Missing Backend Requirements

| Feature | Required endpoint | Method | Request body | Response body | Related model | New serializer/view needed? | Model fields missing? | Migration needed? | Risk | Priority |
|---|---|---:|---|---|---|---|---|---|---|---|
| Admin auth wrapper | `/api/admin/auth/login/` | POST | `{email or phone_number, password}` | `{user, profile, access, refresh}` with admin verification | `User`, `OrganizationStaffProfile` | Optional wrapper | No | No | Low | Phase A |
| Admin current user/profile | `/api/admin/auth/me/` | GET | None | Admin user plus staff/org permissions | `User`, `OrganizationStaffProfile`, `Organization` | Yes | No | No | Low | Phase A |
| Dashboard stats | `/api/admin/dashboard/stats/` | GET | Query filters optional | Counts, distributions, recent lists | Existing User/Profile/Pharmacy/Prescription/SignQualityReport | Yes | No for base counts; some fields partial | No initially | Medium | Phase A |
| Patient list/detail | `/api/admin/patients/`, `/api/admin/patients/<id>/` | GET | Query filters | Paginated admin patient rows/details | `PatientProfile`, `User`, `PatientMedicalInfo` | Yes | city/region/diagnosis/currentMedications/accountStatus mapping partial | Possibly if exact fields required | Medium | Phase B |
| Patient create/update/delete | `/api/admin/patients/`, `/api/admin/patients/<id>/` | POST/PATCH/DELETE | Patient + user + medical fields | Admin patient detail | `PatientProfile`, `User`, `PatientMedicalInfo` | Yes | city/region/diagnosis/currentMedications separate fields missing | Possibly | Medium | Phase B |
| QR list/detail | `/api/admin/qr-codes/`, `/api/admin/qr-codes/<id>/` | GET | Query filters | QR rows with patient info and status | `PatientProfile`, `PatientLoginQR` | Yes | Stable public QR value for `PatientLoginQR` is not stored, only hash | Possibly if list must show value | High | Phase B |
| QR disable/reactivate | `/api/admin/qr-codes/<id>/disable/`, `/reactivate/` | POST | Optional reason | QR status | `PatientLoginQR` or `PatientProfile` | Yes | Reactivate semantics missing | Maybe | Medium | Phase B |
| Pharmacy update/delete | `/api/admin/pharmacies/<id>/` | PATCH/DELETE | Pharmacy fields | Pharmacy detail | `Pharmacy` | Yes or extend existing view | licenseNumber/city/region/status/notes missing | Yes if required | Medium | Phase C |
| Pharmacy admin full serializer | `/api/admin/pharmacies/` | GET/POST | Pharmacy fields | Admin pharmacy detail | `Pharmacy` | Yes | `license_number`, `city`, `region`, `status`, `notes` missing | Yes if required | Medium | Phase C |
| Pharmacist CRUD | `/api/admin/pharmacists/`, `/api/admin/pharmacists/<id>/` | GET/POST/PATCH/DELETE | User/profile/pharmacy fields | Admin pharmacist detail | `User`, `PharmacistProfile`, `Pharmacy` | Yes | Pharmacist notes missing | Maybe | Medium | Phase C |
| Approval request detail | `/api/admin/approval-requests/<id>/` | GET | None | Joined pending/rejected/approved request detail | `User`, `PatientProfile`, `PharmacistProfile`, `Pharmacy` | Yes | No separate request model | No unless audit/history needed | Medium | Phase D |
| Approval request list shape | `/api/admin/approval-requests/` | GET | Query filters | Paginated frontend `ApprovalRequest` rows | Same as above | Yes | Some city/region fields missing | Maybe | Medium | Phase D |
| Prescription logs list | `/api/admin/prescription-logs/` | GET | Query filters | Paginated prescription log rows | `Prescription`, `PrescriptionItem` | Yes | None for core list | No | Medium | Phase E |
| Prescription log detail | `/api/admin/prescription-logs/<id>/` | GET | None | Prescription detail with items/access logs | `Prescription`, `PrescriptionAccessLog` | Yes | None for core detail | No | Medium | Phase E |
| Prescription access log list | Could be nested in detail or `/access-logs/` | GET | Query filters | Log rows | `PrescriptionAccessLog` | Yes | No | No | Low | Phase E |
| Sign quality detail/update shape | `/api/admin/sign-quality-records/` | GET/PATCH | Status, reviewer notes | Frontend shape with medicines | `SignQualityReport`, `PrescriptionItem` | Yes, can reuse model | `reviewer_notes`, per-medicine notes/status missing | Yes if required | Medium | Phase F |
| Reports summary/export | `/api/admin/reports/summary/` | GET | Query filters | Aggregated report summary | Existing models | Yes | Depends on product metrics | No initially | Medium | Phase G |
| Admin settings/org profile | `/api/admin/settings/` | GET/PATCH | Organization profile fields | Org/settings detail | `Organization` | Yes | Settings beyond org profile missing | Maybe | Low/Medium | Phase G |

## 4. Model-to-Admin Mapping

### Patient

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| id | `PatientProfile` | `id` | `patients/models.py` | yes | Primary key. |
| fullName | `PatientProfile` | `full_name` | `patients/models.py` | yes | Serializer should camelCase/map. |
| phone | `PatientProfile` / `User` | `phone_number` | `patients/models.py`, `accounts/models.py` | yes | Existing code often falls back to `user.phone_number`. |
| gender | `PatientProfile` | `gender` | `patients/models.py` | yes | Values are `M`, `F`, `O`. |
| age | Derived | from `birth_date` | `patients/models.py` | partial | Not stored. Compute if needed. |
| birthDate | `PatientProfile` | `birth_date` | `patients/models.py` | yes | Existing self serializer also uses `date_of_birth`. |
| city | None | None | N/A | no | No city field. Possible fallback from `address` only. |
| region | None | None | N/A | no | No region field. |
| hearingSeverity | `PatientProfile` | `hearing_disability_level` | `patients/models.py` | yes | Values: mild/moderate/severe/profound. |
| diagnosis | `Prescription` | `diagnosis` | `prescriptions/models.py` | partial | Prescription-level diagnosis, not patient profile field. |
| allergies | `PatientMedicalInfo` | `allergies` | `patients/models.py` | yes | One-to-one via `PatientProfile.medical_info`. |
| chronicDiseases | `PatientMedicalInfo` | `chronic_conditions` | `patients/models.py` | partial | Naming differs. |
| currentMedications | `PatientMedicalInfo` | `notes` | `patients/models.py` | partial | No dedicated current medications field; existing compatibility maps regular medications to notes. |
| notes | `PatientMedicalInfo` / `PatientEnrollment` | `notes` | `patients/models.py` | partial | Patient profile itself has no notes. |
| accountStatus | `User` | `is_active`, `approval_status` | `accounts/models.py` | partial | Need frontend mapping. |
| qrStatus | `PatientProfile` / `PatientLoginQR` | `qr_is_active`, `is_active`, `revoked_at` | `patients/models.py` | yes/partial | Multiple QR concepts exist. |
| createdAt | `PatientProfile` / `User` | `created_at` | `patients/models.py`, `accounts/models.py` | yes | Choose profile creation for patient row. |

### Pharmacist

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| id | `PharmacistProfile` | `id` | `pharmacies/models.py` | yes | Primary key. |
| fullName | `PharmacistProfile` | `full_name` | `pharmacies/models.py` | yes |  |
| phone | `User` | `phone_number` | `accounts/models.py` | yes | Exposed by `PharmacistProfileSerializer`. |
| pharmacyId | `PharmacistProfile` | `pharmacy_id` | `pharmacies/models.py` | yes | Serializer currently nests pharmacy. |
| licenseNumber | `PharmacistProfile` | `license_number` | `pharmacies/models.py` | yes |  |
| accountStatus | `User` | `is_active`, `approval_status` | `accounts/models.py` | partial | Need mapping. |
| approvalStatus | `User` / `PharmacistProfile` | `approval_status`, `is_approved` | `accounts/models.py`, `pharmacies/models.py` | yes | Keep both synchronized. |
| createdAt | `PharmacistProfile` / `User` | `created_at` | `pharmacies/models.py`, `accounts/models.py` | yes | Choose profile or user consistently. |
| notes | None | None | N/A | no | Migration needed if required. |

### Pharmacy

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| id | `Pharmacy` | `id` | `pharmacies/models.py` | yes |  |
| name | `Pharmacy` | `name` | `pharmacies/models.py` | yes |  |
| phone | `Pharmacy` | `phone_number` | `pharmacies/models.py` | yes |  |
| city | None | None | N/A | no | `SafePharmacySerializer.get_city()` returns empty string. |
| region | None | None | N/A | no | `SafePharmacySerializer.get_region()` returns empty string. |
| address | `Pharmacy` | `address` | `pharmacies/models.py` | yes |  |
| licenseNumber | None | None | N/A | no | Migration needed if required. |
| pharmacistsCount | Derived | count `pharmacists` relation | `pharmacies/models.py` | partial | Can annotate `Count("pharmacists")`. |
| status | None | None | N/A | no | Could derive active/contracted, but no explicit status. |
| createdAt | `Pharmacy` | `created_at` | `pharmacies/models.py` | yes |  |
| notes | None | None | N/A | no | Migration needed if required. |
| latitude | `Pharmacy` | `latitude` | `pharmacies/models.py` | yes | Decimal. |
| longitude | `Pharmacy` | `longitude` | `pharmacies/models.py` | yes | Decimal. |
| isContractedWithOrganization | `Pharmacy` | `is_contracted_with_organization` | `pharmacies/models.py` | yes |  |

### ApprovalRequest

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| id | `User` | `id` | `accounts/models.py` | partial | No separate approval request id/model. |
| type | `User` | `role` | `accounts/models.py` | yes | Map patient/pharmacist. |
| name | `PatientProfile` / `PharmacistProfile` | `full_name` | `patients/models.py`, `pharmacies/models.py` | yes | Need joined serializer. |
| phone | `User` / profiles | `phone_number` | `accounts/models.py` | yes |  |
| city | None | None | N/A | no | No city field. |
| region | None | None | N/A | no | No region field. |
| requestDate | `User` | `created_at` | `accounts/models.py` | yes | Registration request date. |
| status | `User` | `approval_status` | `accounts/models.py` | yes |  |
| details | Joined serializer | Profile/pharmacy/medical fields | Multiple | partial | Not currently exposed. |
| rejectionReason | `User` | `rejection_reason` | `accounts/models.py` | yes |  |
| selectedPharmacyId | `PharmacistProfile` | `pharmacy_id` | `pharmacies/models.py` | partial | Only for pharmacists. |
| pharmacistLicenseNumber | `PharmacistProfile` | `license_number` | `pharmacies/models.py` | partial | Only for pharmacists. |

### QrCode

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| id | `PatientLoginQR` / `PatientProfile` | `id` | `patients/models.py` | partial | Need decide QR resource type. |
| patientId | `PatientLoginQR` / `PatientProfile` | `patient_id` / `id` | `patients/models.py` | yes |  |
| patientName | `PatientProfile` | `full_name` | `patients/models.py` | yes | Join. |
| patientPhone | `PatientProfile` / `User` | `phone_number` | `patients/models.py`, `accounts/models.py` | yes |  |
| patientCity | None | None | N/A | no | No city field. |
| patientRegion | None | None | N/A | no | No region field. |
| value | `PatientProfile` | `qr_code_value` | `patients/models.py` | partial | Login QR stores only hash; raw token cannot be listed later. |
| status | `PatientProfile` / `PatientLoginQR` | `qr_is_active` / `is_active`, `revoked_at` | `patients/models.py` | yes | Need normalize active/revoked. |
| createdAt | `PatientLoginQR` / `PatientProfile` | `created_at` | `patients/models.py` | yes |  |

### PrescriptionLog

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| id | `Prescription` | `id` | `prescriptions/models.py` | yes |  |
| patientName | `Prescription.patient` | `full_name` | `prescriptions/models.py`, `patients/models.py` | yes |  |
| pharmacyName | `Prescription.pharmacy` | `name` | `prescriptions/models.py`, `pharmacies/models.py` | yes |  |
| pharmacistName | `Prescription.pharmacist` | `full_name` | `prescriptions/models.py`, `pharmacies/models.py` | yes |  |
| date | `Prescription` | `prescribed_at` or `submitted_at` | `prescriptions/models.py` | yes | Product decision which date. |
| medicinesCount | Derived | count `items` | `prescriptions/models.py` | partial | Annotate count. |
| status | `Prescription` | `status` | `prescriptions/models.py` | yes |  |
| notes | `Prescription` | `notes` | `prescriptions/models.py` | yes |  |

### SignQualityRecord

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| id | `SignQualityReport` | `id` | `prescriptions/models.py` | yes | Existing report id. |
| prescriptionId | `SignQualityReport` | `prescription_id` | `prescriptions/models.py` | yes |  |
| patientName | `SignQualityReport.patient` | `full_name` | `prescriptions/models.py`, `patients/models.py` | yes | Current serializer includes patient object. |
| patientPhone | `PatientProfile` / `User` | `phone_number` | `patients/models.py`, `accounts/models.py` | yes | Current admin serializer includes patient phone. |
| pharmacyName | `Prescription.pharmacy` | `name` | `prescriptions/models.py`, `pharmacies/models.py` | partial | Not currently in `AdminSignQualityReportSerializer`. |
| pharmacistName | `Prescription.pharmacist` | `full_name` | `prescriptions/models.py`, `pharmacies/models.py` | partial | Not currently in serializer. |
| date | `SignQualityReport` | `created_at` | `prescriptions/models.py` | yes |  |
| medicinesCount | Derived | count items/reports | `prescriptions/models.py` | partial | Product decision: prescription item count or report count. |
| qualityStatus | `SignQualityReport` | `status` | `prescriptions/models.py` | yes |  |
| reason | `SignQualityReport` | `report_type` | `prescriptions/models.py` | yes | Only `sign_unclear` exists. |
| reviewerNotes | None | None | N/A | no | Migration needed if required. |
| medicines | `PrescriptionItem` / `SignQualityReport` | related item/report fields | `prescriptions/models.py` | partial | Current model is one report per item, not grouped record with medicines array. |

SignQualityRecord medicine:

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| id | `PrescriptionItem` | `id` | `prescriptions/models.py` | yes | Or report id, product decision. |
| medicineName | `PrescriptionItem` / `SignQualityReport` | `medicine_name` | `prescriptions/models.py` | yes | Snapshot exists on report. |
| approvedInstructionText | `SignQualityReport` / `PrescriptionItem` | `approved_instruction_text` / `instructions_transcript_edited` | `prescriptions/models.py` | yes | Report stores snapshot. |
| signVideoUrl | `PrescriptionItem` | `sign_language_video` | `prescriptions/models.py` | yes | Existing sign generation currently returns `video_url: null`; gloss only. |
| medicineQualityStatus | `SignQualityReport` | `status` | `prescriptions/models.py` | partial | Status is report-level. |
| notes | None | None | N/A | no | Migration needed if per-medicine notes are required. |

### DashboardStats

| Frontend field | Existing backend model | Existing backend field | Exact file path | Exists? | Notes/fallback |
|---|---|---|---|---|---|
| patientsCount | `PatientProfile` | count ids | `patients/models.py` | partial | Compute. |
| pharmacistsCount | `PharmacistProfile` | count ids | `pharmacies/models.py` | partial | Compute. |
| pharmaciesCount | `Pharmacy` | count ids | `pharmacies/models.py` | partial | Compute. |
| prescriptionsCount | `Prescription` | count ids | `prescriptions/models.py` | partial | Compute. |
| activeQrCount | `PatientProfile` / `PatientLoginQR` | `qr_is_active` / `is_active` | `patients/models.py` | partial | Need QR type decision. |
| pendingApprovalsCount | `User` | `approval_status=pending` | `accounts/models.py` | partial | Compute by manageable roles. |
| signQualityFollowUpCount | `SignQualityReport` | status open/reviewed | `prescriptions/models.py` | partial | Product decision which statuses count. |
| patientsByCity | None | None | N/A | no | Cannot compute without city. |
| genderDistribution | `PatientProfile` | `gender` | `patients/models.py` | partial | Compute. |
| hearingSeverityDistribution | `PatientProfile` | `hearing_disability_level` | `patients/models.py` | partial | Compute. |
| ageGroups | `PatientProfile` | `birth_date` | `patients/models.py` | partial | Compute. |
| recentPatients | `PatientProfile` | `created_at` | `patients/models.py` | partial | Compute. |
| recentApprovalRequests | `User` | `approval_status`, `created_at` | `accounts/models.py` | partial | Compute with joined profile summary. |

## 5. Recommended Backend Implementation Plan

### Phase A - Admin Auth and Dashboard Stats

- Endpoints to reuse:
  - `POST /api/auth/login/`
  - `GET /api/auth/me/`
  - `POST /api/auth/logout/`
  - `POST /api/auth/refresh/`
- Endpoints to add:
  - `POST /api/admin/auth/login/` as an admin-only wrapper or documented alias with role enforcement.
  - `GET /api/admin/auth/me/` returning admin staff profile and organization permissions.
  - `GET /api/admin/dashboard/stats/`.
- Serializers to create:
  - `AdminMeSerializer`
  - `AdminDashboardStatsSerializer` or plain response builder.
- Permissions:
  - `IsAuthenticated + IsAdminRole` for admin me/stats.
  - For stats, apply org scoping if `OrganizationStaffProfile` exists.
- Filters/search:
  - Optional date range for stats.
- Migrations:
  - None for baseline counts/distributions, except city-based stats cannot be implemented exactly.
- Tests:
  - Admin/non-admin access.
  - Organization staff scoping.
  - Dashboard count correctness.
- Risk:
  - Low/Medium. The main risk is ambiguous admin profile shape and missing city fields.
- Frontend adapter notes:
  - Adapter can call existing `/api/auth/login/` now, but should reject non-admin users client-side until admin wrapper exists.

### Phase B - Patients / QR Admin APIs

- Endpoints to reuse:
  - `POST /api/admin/patients/create-account/`
  - `POST /api/patients/<id>/generate-qr/`
  - `POST /api/admin/patients/<id>/login-qr/`
  - `POST /api/admin/patients/<id>/login-qr/revoke/`
- Endpoints to add:
  - `GET/POST /api/admin/patients/`
  - `GET/PATCH/DELETE /api/admin/patients/<id>/`
  - `GET /api/admin/qr-codes/`
  - `GET /api/admin/qr-codes/<id>/`
  - `POST /api/admin/qr-codes/<id>/regenerate/`
  - `POST /api/admin/qr-codes/<id>/disable/`
  - `POST /api/admin/qr-codes/<id>/reactivate/` only if product confirms semantics.
- Serializers to create:
  - `AdminPatientListSerializer`
  - `AdminPatientDetailSerializer`
  - `AdminPatientCreateUpdateSerializer`
  - `AdminQRCodeSerializer`
- Permissions:
  - `IsAuthenticated + CanManagePatients`.
- Filters/search:
  - `search`: full name, phone.
  - `gender`, `hearing_disability_level`, `qr_is_active`, `approval_status`, `organization`, created date range.
- Migrations:
  - None for basic patient API.
  - Required if exact `city`, `region`, dedicated `current_medications`, patient `notes`, or patient-level `diagnosis` are required.
  - Required if QR list must expose persistent raw login QR values because current `PatientLoginQR` stores hashes only.
- Tests:
  - CRUD permission/scoping.
  - QR generate/revoke/regenerate behavior.
  - Non-admin denial.
- Risk:
  - Medium/High for QR value/status semantics.
- Frontend adapter notes:
  - Use backend snake_case or add camelCase adapter in frontend/API layer.

### Phase C - Pharmacies / Pharmacists Admin APIs

- Endpoints to reuse:
  - `GET/POST /api/pharmacies/`
  - `GET /api/pharmacies/<id>/`
- Endpoints to add:
  - `GET/POST /api/admin/pharmacies/`
  - `GET/PATCH/DELETE /api/admin/pharmacies/<id>/`
  - `GET/POST /api/admin/pharmacists/`
  - `GET/PATCH/DELETE /api/admin/pharmacists/<id>/`
- Serializers to create:
  - `AdminPharmacySerializer` with `pharmacists_count`.
  - `AdminPharmacistSerializer` joining `User`, `PharmacistProfile`, and nested/summary `Pharmacy`.
  - Create/update serializers that manage linked `User`.
- Permissions:
  - `IsAuthenticated + CanManagePharmacists`.
- Filters/search:
  - Pharmacies: name, phone, contracted, organization.
  - Pharmacists: name, phone, license number, pharmacy, approval/account status.
- Migrations:
  - Required only if pharmacy `license_number`, `city`, `region`, `status`, `notes` or pharmacist `notes` are mandatory.
- Tests:
  - Admin CRUD, org scoping, linked-user updates, duplicate phone/license validation.
- Risk:
  - Medium because pharmacist CRUD crosses `User` and profile models.
- Frontend adapter notes:
  - Keep pharmacy selection by id. Existing public contracted pharmacy endpoint can support registration dropdown, not admin management.

### Phase D - Approval Requests

- Endpoints to reuse:
  - `GET /api/admin/registration-requests/`
  - `POST /api/admin/users/<id>/approve/`
  - `POST /api/admin/users/<id>/reject/`
- Endpoints to add:
  - `GET /api/admin/approval-requests/`
  - `GET /api/admin/approval-requests/<id>/`
  - `POST /api/admin/approval-requests/<id>/approve/`
  - `POST /api/admin/approval-requests/<id>/reject/`
- Serializers to create:
  - `AdminApprovalRequestListSerializer`
  - `AdminApprovalRequestDetailSerializer`
  - `AdminApprovalRejectSerializer`
- Permissions:
  - Reuse `AuthViewSet` role-management logic or extract to shared permission/service.
- Filters/search:
  - `type`, `status`, `search`, created date range.
- Migrations:
  - None if requests remain `User`-backed.
  - Required only if product needs approval history or non-registration request types.
- Tests:
  - Patient/pharmacist role scoping.
  - Approve/reject state changes.
  - Rejection reason.
- Risk:
  - Medium. Main risk is product expecting a separate request lifecycle.
- Frontend adapter notes:
  - `ApprovalRequest.id` should map to `User.id` unless a dedicated model is introduced later.

### Phase E - Prescription Logs

- Endpoints to reuse:
  - `GET /api/prescriptions/<id>/` for admin detail, with existing permission.
- Endpoints to add:
  - `GET /api/admin/prescription-logs/`
  - `GET /api/admin/prescription-logs/<id>/`
- Serializers to create:
  - `AdminPrescriptionLogListSerializer`
  - `AdminPrescriptionLogDetailSerializer`
  - Optional `AdminPrescriptionAccessLogSerializer`.
- Permissions:
  - `IsAuthenticated + CanManagePatients`, with organization scoping.
- Filters/search:
  - Patient name/phone, pharmacy, pharmacist, status, prescribed/submitted date range.
- Migrations:
  - None for baseline logs.
- Tests:
  - Admin list/detail, org scoping, item count, access logs.
- Risk:
  - Medium because existing router has a prescription list URL but view does not implement list.
- Frontend adapter notes:
  - Use prescription id as log id.

### Phase F - Sign Quality Monitoring

- Endpoints to reuse:
  - `GET /api/admin/sign-quality-reports/`
  - `GET/PATCH /api/admin/sign-quality-reports/<id>/`
- Endpoints to add or alias:
  - `GET /api/admin/sign-quality-records/`
  - `GET /api/admin/sign-quality-records/<id>/`
  - `PATCH /api/admin/sign-quality-records/<id>/`
- Serializers to create:
  - `AdminSignQualityRecordListSerializer`
  - `AdminSignQualityRecordDetailSerializer`
  - `AdminSignQualityRecordUpdateSerializer`
- Permissions:
  - `IsAuthenticated + CanManagePatients`.
- Filters/search:
  - `status`, `report_type`, `patient_id`, `prescription_id`, pharmacy, pharmacist.
- Migrations:
  - None if only status update is required.
  - Required for `reviewer_notes`, per-medicine notes, and extra quality statuses beyond current choices.
- Tests:
  - Existing coverage for list/update; add detail shape and filters.
- Risk:
  - Medium due frontend grouped `medicines` shape vs current one-report-per-item model.
- Frontend adapter notes:
  - Prefer using existing report id as record id unless product wants grouping by prescription.

### Phase G - Reports / Settings If Supported

- Endpoints to reuse:
  - None for reports.
  - `OrganizationSerializer` exists but no view.
- Endpoints to add:
  - `GET /api/admin/reports/summary/`
  - `GET/PATCH /api/admin/settings/`
- Serializers to create:
  - `AdminReportSummarySerializer` or service response.
  - `AdminOrganizationSettingsSerializer`.
- Permissions:
  - `IsAuthenticated + IsAdminRole`.
  - Org staff can only access their own organization.
- Filters/search:
  - Date range and organization scope for reports.
- Migrations:
  - None for basic organization profile.
  - Required if settings include configurable feature flags, branding, or contact fields beyond `Organization`.
- Tests:
  - Admin/scoped access and update.
- Risk:
  - Low/Medium depending on settings scope.
- Frontend adapter notes:
  - Treat settings as optional until product confirms organization profile fields.

## 6. Proposed Admin URL Namespace

Recommendation: introduce an explicit `/api/admin/` namespace for the admin dashboard and keep existing mobile/patient/pharmacist endpoints stable. Where existing behavior already exists, the admin URL can either wrap/reuse the same serializer/service or internally delegate to existing logic.

| Endpoint | Method | Purpose | Permission | Existing or new | Migration needed? |
|---|---:|---|---|---|---|
| `/api/admin/auth/login/` | POST | Admin login with role verification | `AllowAny` then enforce admin role | New wrapper over existing login | No |
| `/api/admin/auth/me/` | GET | Current admin/staff profile and permissions | `IsAuthenticated + IsAdminRole` | New | No |
| `/api/admin/auth/logout/` | POST | Logout/blacklist refresh token | `IsAuthenticated` | Existing behavior alias | No |
| `/api/admin/patients/` | GET | Patient list | `CanManagePatients` | New | No for base |
| `/api/admin/patients/` | POST | Create patient | `CanManagePatients` | Existing create-account behavior can be reused | Maybe for missing fields |
| `/api/admin/patients/<id>/` | GET | Patient detail | `CanManagePatients` | New | No for base |
| `/api/admin/patients/<id>/` | PATCH | Update patient/user/medical info | `CanManagePatients` | New | Maybe for missing fields |
| `/api/admin/patients/<id>/` | DELETE | Deactivate/delete patient | `CanManagePatients` | New | No |
| `/api/admin/patients/<id>/generate-qr/` | POST | Generate/regenerate patient profile QR | `CanManagePatients` | Existing behavior | No |
| `/api/admin/pharmacies/` | GET | Pharmacy list | `CanManagePharmacists` | Existing partial/new preferred | No for base |
| `/api/admin/pharmacies/` | POST | Create pharmacy | `CanManagePharmacists` | Existing partial/new preferred | Maybe for missing fields |
| `/api/admin/pharmacies/<id>/` | GET | Pharmacy detail | `CanManagePharmacists` | Existing partial/new preferred | No |
| `/api/admin/pharmacies/<id>/` | PATCH | Update pharmacy | `CanManagePharmacists` | New | Maybe |
| `/api/admin/pharmacies/<id>/` | DELETE | Delete/deactivate pharmacy | `CanManagePharmacists` | New | No |
| `/api/admin/pharmacists/` | GET | Pharmacist list | `CanManagePharmacists` | New | No for base |
| `/api/admin/pharmacists/` | POST | Create pharmacist and linked user/profile | `CanManagePharmacists` | New | Maybe |
| `/api/admin/pharmacists/<id>/` | GET | Pharmacist detail | `CanManagePharmacists` | New | No |
| `/api/admin/pharmacists/<id>/` | PATCH | Update pharmacist/user/pharmacy link | `CanManagePharmacists` | New | Maybe |
| `/api/admin/pharmacists/<id>/` | DELETE | Delete/deactivate pharmacist | `CanManagePharmacists` | New | No |
| `/api/admin/approval-requests/` | GET | Approval request list | Admin/staff manageable roles | Existing partial/new preferred | No |
| `/api/admin/approval-requests/<id>/` | GET | Approval request detail | Admin/staff manageable roles | New | No |
| `/api/admin/approval-requests/<id>/approve/` | POST | Approve user request | Admin/staff manageable roles | Existing behavior | No |
| `/api/admin/approval-requests/<id>/reject/` | POST | Reject user request | Admin/staff manageable roles | Existing behavior | No |
| `/api/admin/qr-codes/` | GET | QR list | `CanManagePatients` | New | Maybe if raw login QR value required |
| `/api/admin/qr-codes/<id>/` | GET | QR detail | `CanManagePatients` | New | Maybe |
| `/api/admin/qr-codes/<id>/regenerate/` | POST | Regenerate QR | `CanManagePatients` | Existing service partial | Maybe |
| `/api/admin/qr-codes/<id>/disable/` | POST | Disable/revoke QR | `CanManagePatients` | Existing revoke partial | No |
| `/api/admin/qr-codes/<id>/reactivate/` | POST | Reactivate QR | `CanManagePatients` | New | Maybe |
| `/api/admin/prescription-logs/` | GET | Prescription log list | `CanManagePatients` | New | No |
| `/api/admin/prescription-logs/<id>/` | GET | Prescription log detail | `CanManagePatients` | Existing detail partial/new preferred | No |
| `/api/admin/sign-quality-records/` | GET | Sign quality list | `CanManagePatients` | Existing partial/new alias | No for base |
| `/api/admin/sign-quality-records/<id>/` | GET | Sign quality detail | `CanManagePatients` | Existing partial/new alias | No for base |
| `/api/admin/sign-quality-records/<id>/` | PATCH | Update quality status/notes | `CanManagePatients` | Existing status update partial | Maybe for notes |
| `/api/admin/dashboard/stats/` | GET | Dashboard statistics | `IsAdminRole` plus scope | New | No for base |
| `/api/admin/reports/summary/` | GET | Report summary/export base | `IsAdminRole` plus scope | New | No for base |
| `/api/admin/settings/` | GET | Organization/admin settings | `IsAdminRole` plus scope | New | Maybe |
| `/api/admin/settings/` | PATCH | Update organization/admin settings | `IsAdminRole` plus scope | New | Maybe |

## Summary

The backend already has solid foundations for JWT auth, approval-aware authentication, admin/staff permission helpers, patient account creation, pharmacy list/create, prescription detail, QR generation/revocation, and sign quality report list/update. It is not yet ready for the full React Admin Dashboard because most admin CRUD/list/detail endpoints and dashboard/reporting APIs are missing or only partially aligned with frontend shapes.

## Can Reuse Immediately

- `POST /api/auth/login/`
- `GET /api/auth/me/`
- `POST /api/auth/logout/`
- `POST /api/auth/refresh/`
- `GET /api/admin/registration-requests/`
- `POST /api/admin/users/<pk>/approve/`
- `POST /api/admin/users/<pk>/reject/`
- `POST /api/admin/patients/create-account/`
- `POST /api/patients/<pk>/generate-qr/`
- `POST /api/admin/patients/<patient_id>/login-qr/`
- `POST /api/admin/patients/<patient_id>/login-qr/revoke/`
- `GET/POST /api/pharmacies/` and `GET /api/pharmacies/<id>/` for limited pharmacy admin use.
- `GET /api/prescriptions/<id>/` for admin prescription detail.
- `GET /api/admin/sign-quality-reports/`
- `GET/PATCH /api/admin/sign-quality-reports/<pk>/`

## Must Implement

- Admin-specific `me` response and, preferably, admin auth namespace wrappers.
- Admin patient list/detail/update/delete.
- Unified QR list/detail/status/regenerate/disable/reactivate semantics.
- Admin pharmacist list/detail/create/update/delete.
- Admin pharmacy update/delete and dashboard-friendly serializer.
- Approval request detail and richer list payload.
- Prescription log list/detail APIs.
- Dashboard stats endpoint.
- Admin sign quality record serializer matching frontend fields.
- Optional report summary endpoint.
- Optional settings/organization profile endpoint.

## Needs Product Decision

- Whether patient/pharmacy `city` and `region` are required as real structured fields or can be derived from `address`.
- Whether pharmacy `licenseNumber`, `status`, and `notes` are required.
- Whether pharmacist `notes` are required.
- Whether patient `diagnosis` and `currentMedications` should be patient-level fields or derived from prescriptions/medical notes.
- Which QR model is the admin dashboard concept: `PatientProfile.qr_code_value`, `PatientLoginQR`, or both.
- Whether QR list must display the actual QR token value. Current login QR tokens are stored as hashes and cannot be recovered after generation.
- Whether approval requests need a dedicated model/audit trail or can remain `User`-backed.
- Whether sign quality records should be one row per `SignQualityReport` or grouped by prescription with a medicines array.
- Whether reviewer notes and per-medicine quality notes are required.
- Which date should drive prescription logs: `prescribed_at`, `submitted_at`, or `created_at`.
- What organization/settings fields the dashboard should manage.

## Migration Risks

- Adding structured patient/pharmacy location fields: `city`, `region`.
- Adding pharmacy fields: `license_number`, `status`, `notes`.
- Adding pharmacist notes.
- Adding patient-level notes/current medications/diagnosis if existing `PatientMedicalInfo.notes` and `Prescription.diagnosis` are insufficient.
- Storing recoverable QR display values for `PatientLoginQR` would be a security-sensitive migration; current hashes are safer.
- Adding `reviewer_notes` and per-medicine quality notes/status to sign quality workflow.
- Adding a dedicated `ApprovalRequest` model if approval history or non-registration requests are required.
- Adding configurable settings beyond the existing `Organization` model.

## Recommended Next Prompt

Act as a senior Django REST Framework backend engineer.

Implement Phase A only from `ADMIN_BACKEND_DISCOVERY.md`.

Rules:
- Backend only.
- Do not modify frontend code.
- Keep existing mobile/patient/pharmacist endpoints backward compatible.
- Add protected admin APIs under `/api/admin/`.
- Reuse existing auth behavior where possible.
- Do not create migrations unless absolutely required for Phase A.

Phase A requirements:
1. Add `POST /api/admin/auth/login/`.
   - Accept the same credentials as `/api/auth/login/`.
   - Return the same token payload plus admin/staff profile data.
   - Reject authenticated credentials unless the user is superuser or `role == admin`.
   - Preserve approval-aware behavior.
2. Add `GET /api/admin/auth/me/`.
   - Require authenticated admin/superuser.
   - Return user fields plus organization staff profile and organization summary when available.
   - Include booleans for `can_manage_patients` and `can_manage_pharmacists`.
3. Add `POST /api/admin/auth/logout/`.
   - Reuse existing logout behavior.
4. Add `GET /api/admin/dashboard/stats/`.
   - Require admin/superuser.
   - Scope organization staff users to their organization.
   - Return counts for patients, pharmacists, pharmacies, prescriptions, active QR, pending approvals, sign quality follow-up, gender distribution, hearing severity distribution, age groups, recent patients, and recent approval requests.
   - For `patientsByCity`, return an empty list and comment in code/report that structured city does not exist yet.
5. Add tests for admin/non-admin access, organization scoping, and core stat counts.

After implementation, run the relevant Django tests and report changed files and test results.
