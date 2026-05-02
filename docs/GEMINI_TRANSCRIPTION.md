# Gemini Transcription

## Purpose

This backend uses Django as the only layer that talks to Gemini for audio transcription.

The frontend uploads the audio file to Django. Django validates the user, validates the file, sends the audio to Gemini, and returns the transcript JSON response.

The frontend must not call Gemini directly.

## Get a Gemini API key

1. Open Google AI Studio.
2. Create or sign in to your Google account.
3. Generate an API key.
4. Copy the key into your backend `.env`.

## `.env` setup

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
MAX_AUDIO_UPLOAD_SIZE_MB=10
```

## Endpoint

```text
POST /api/transcriptions/test/
```

## Auth requirements

- JWT access token required
- User must be authenticated
- User must have `approval_status == "approved"`
- User role must be `pharmacist`

## Request format

`multipart/form-data`

Field:

- `audio`: file

Allowed content types:

- `audio/mpeg`
- `audio/mp3`
- `audio/wav`
- `audio/x-wav`
- `audio/webm`
- `audio/mp4`
- `audio/m4a`
- `audio/aac`
- `audio/ogg`

Max size:

- 25MB

## Success response

```json
{
  "status": "completed",
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "transcript": "..."
}
```

## Failure response

```json
{
  "status": "failed",
  "provider": "gemini",
  "error": "..."
}
```

## Postman test steps

1. Start the Django server.
2. Log in as an approved pharmacist and copy the access token.
3. Open Postman.
4. Send `POST http://127.0.0.1:8000/api/transcriptions/test/`
5. Add header:

```text
Authorization: Bearer <approved pharmacist access token>
```

6. Set body to `form-data`.
7. Add a file field named `audio`.
8. Upload a supported audio file such as `.mp3`, `.wav`, or `.m4a`.
9. Confirm the response includes:
   - `status`
   - `provider`
   - `model`
   - `transcript`

## Warning

- Gemini is the only transcription provider in this backend.
- Do not place the Gemini API key in the frontend.
- Do not call Gemini directly from the mobile app or web frontend.
- Django is the only layer that should communicate with Gemini.
