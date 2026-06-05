# Security Notes

## Field-Level Encryption

Sensitive medical text is protected with field-level symmetric encryption using
`cryptography.fernet`. Django encrypts values before writing them to the
database and decrypts them automatically when authorized backend code reads them
through the ORM.

Encrypted medical fields include patient medical notes, allergies, chronic
conditions, prescription diagnosis and notes, medication instructions,
transcripts, approved instruction text, and generated sign gloss text.

## Secrets

`FIELD_ENCRYPTION_KEY` must be stored outside Git, normally in `.env` or the
deployment secret manager. Generate a valid key with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

When `DEBUG=False`, the backend refuses to start without
`FIELD_ENCRYPTION_KEY`. In local development only, if no key is configured, the
backend derives a deterministic development key from `SECRET_KEY` so tests and
local data remain readable across restarts. Do not rely on that fallback in
production.

Losing `FIELD_ENCRYPTION_KEY` means losing the ability to read encrypted medical
data. Changing the key requires a planned key-rotation migration.

## Encryption vs Hashing

Medical data uses encryption, not hashing, because the application must read it
again for authorized users.

Passwords remain hashed by Django authentication, which is correct because
passwords should never be decrypted.

OTP codes, QR tokens, and access PINs remain hashed, which is correct because
they are verification secrets and do not need to be recovered as plaintext.

## Access Control

Encryption protects data at rest in the database. It does not replace JWT
authentication, role-based permissions, pharmacist/patient scoping, or admin
authorization checks. API responses still return decrypted values only through
the existing authorized backend endpoints.
