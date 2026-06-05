# Medical Data Encryption Report

## Summary

PharmaSign now uses field-level encryption for sensitive medical text stored in
the database. API field names and serializer behavior remain unchanged: the
frontend sends and receives normal plaintext through authorized endpoints, while
the database stores ciphertext.

## Encrypted Fields

Patient medical data:

- `PatientMedicalInfo.chronic_conditions`
- `PatientMedicalInfo.allergies`
- `PatientMedicalInfo.notes`

Prescription medical data:

- `Prescription.diagnosis`
- `Prescription.notes`
- `PrescriptionItem.instructions_text`
- `PrescriptionItem.instructions_transcript_raw`
- `PrescriptionItem.instructions_transcript_edited`
- `PrescriptionItem.supporting_text`
- `SignQualityReport.approved_instruction_text`

Fields intentionally not encrypted include IDs, statuses, dates, role fields,
foreign keys, patient names, phone numbers, and fields commonly used for direct
filtering/search. Passwords, OTP codes, QR tokens, and PINs remain hashed.

## Algorithm

The implementation uses symmetric authenticated encryption via
`cryptography.fernet.Fernet`.

Custom Django model fields:

- `common.fields.EncryptedTextField`
- `common.fields.EncryptedCharField`

These fields encrypt automatically in `get_prep_value()` before database writes
and decrypt automatically in `from_db_value()` / `to_python()` when read through
the Django ORM.

## Encryption Key

The key is read from:

```text
FIELD_ENCRYPTION_KEY
```

Generate a valid key:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add it to `.env` locally or to the deployment secret manager in production. The
key must not be committed to Git.

When `DEBUG=False`, startup fails if `FIELD_ENCRYPTION_KEY` is missing. In local
development only, the backend derives a deterministic fallback key from
`SECRET_KEY` so local tests can run without committing a real encryption key.

## Why Encryption, Not Hashing

Medical data must be readable later by authorized users, so reversible
encryption is required. Hashing is one-way and would make patient medical notes,
prescription instructions, and sign gloss text unrecoverable.

Passwords, OTP codes, QR tokens, and PINs remain hashed because the backend only
needs to verify them, not display them.

## Files Modified

- `common/fields.py`
- `pharmasign/settings.py`
- `.env.example`
- `requirements.txt`
- `patients/admin.py`
- `patients/models.py`
- `patients/migrations/0008_alter_patientmedicalinfo_allergies_and_more.py`
- `patients/migrations/0009_encrypt_existing_patient_medical_info.py`
- `prescriptions/models.py`
- `prescriptions/migrations/0008_alter_prescription_diagnosis_and_more.py`
- `prescriptions/migrations/0010_encrypt_existing_prescription_medical_text.py`
- `patients/tests.py`
- `prescriptions/tests.py`
- `SECURITY_NOTES.md`

## Migration Plan

Run:

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test patients.tests.PatientMedicalInfoEncryptionTests prescriptions.tests.PrescriptionItemEncryptionTests
```

The `0008` migrations change sensitive text fields to encrypted field classes.
The follow-up data migrations re-save existing plaintext values through the
encrypted field layer, converting stored database values to Fernet ciphertext.

## Verification

Create or update a patient medical record or prescription item, then inspect the
database directly. The raw column value should start with a Fernet token prefix
like:

```text
gAAAAA...
```

The raw database value must not contain medical plaintext such as allergy names,
diagnoses, transcripts, or instructions.

Reading the same object through Django ORM or the API should return the original
plaintext value to the authorized user.

## Limitations

Field-level encryption prevents direct plaintext search over encrypted columns.
The current implementation intentionally avoids encrypting commonly filtered
identity/status fields. If future search over encrypted medical text is needed,
add a separate privacy-preserving search design instead of querying ciphertext.

Key rotation is not implemented yet. Rotating `FIELD_ENCRYPTION_KEY` requires a
planned migration that decrypts with the old key and re-encrypts with the new
key.

This improves database-at-rest protection, but it does not make the backend
"100% secure" by itself. Authentication, authorization, transport security,
secret management, backup security, audit logging, and deployment hardening
remain required.
