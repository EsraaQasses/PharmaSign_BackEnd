# Gemini-to-Pose Backend Connection Verification

## 1. Executive Summary

As requested, a comprehensive audit was conducted on the PharmaSign Django REST Framework backend to verify the state of integration between the **Gemini Text-to-Gloss model** and the **FastAPI Gloss-to-Pose model**.

The audit confirms that **both services are individually functional and integrated into the Django codebase, but they currently operate as separate, decoupled steps.** There is no automated single-request pipeline that automatically feeds the generated Gemini Text-to-Gloss output directly into the AI pose generation model during the prescription lifecycle.

* **Gemini Text-to-Gloss** is fully integrated within the `prescriptions` app and is stored in the database.
* **AI Gloss-to-Pose** is fully integrated within the `ai_integration` app with modular API endpoints and custom CLI testing commands.
* **The Connection** is currently split; the outputs are not chained inside a single transaction or automated endpoint.

---

## 2. Gemini Text-to-Gloss Flow

The Gemini translation flow is configured inside the `prescriptions` application:

* **Prompt Template**: `SIGN_GLOSS_PROMPT_TEMPLATE` located in `prescriptions/services.py` (Lines 12–47). It instructs the model to translate prescription instructions into Syrian/Levantine Arabic sign-language glosses.
* **Core Service**: `generate_sign_gloss(approved_text)` in `prescriptions/services.py` (Lines 131–159). It initializes the Google GenAI client and uses the model designated in `settings.GEMINI_SIGN_MODEL`.
* **Database Storage**: The generated gloss text is stored directly on the `PrescriptionItem` model under the `supporting_text` field using `mark_prescription_item_sign_completed(item, gloss_text)` in `prescriptions/services.py` (Lines 167–172).
* **Source Text Fields and Priority Order**: The source text is retrieved from the `PrescriptionItem` instance using a strict fallback prioritization in `generate_sign` in `prescriptions/views.py` (Lines 796–800):
  1. `instructions_transcript_edited` (Approved edit)
  2. `instructions_transcript_raw` (Raw audio transcription)
  3. `instructions_text` (Manual prescription text inputs)
* **Lifecycle Status Changes**: During generation, the item's `sign_status` transitions from `pending` $\rightarrow$ `processing` $\rightarrow$ `completed` (or `failed` in case of errors).

---

## 3. AI Pose Generation Flow

The AI pose generator client is built inside the newly integrated `ai_integration` application:

* **App Name**: `ai_integration` (registered under `LOCAL_APPS` in `settings.py`).
* **Service Client**: `generate_pose_from_gloss(gloss, return_format)` in `ai_integration/services.py`. It uses the `requests` library to make synchronous HTTP POST requests to `{AI_SERVICE_URL}/generate-pose`.
* **Endpoints**:
  * `POST /api/ai/generate-pose/` (View: `AIPoseGenerationView` in `ai_integration/views.py`) — generates the pose.
  * `GET /api/ai/health/` (View: `AIServiceHealthView` in `ai_integration/views.py`) — returns FastAPI service status.
* **Configurations**: Handled via `python-decouple` in `pharmasign/settings.py`:
  * `AI_SERVICE_URL` (Default: `http://127.0.0.1:8002`)
  * `AI_SERVICE_API_KEY` (Default: `""`)
  * `AI_SERVICE_TIMEOUT` (Default: `60`)
* **Payload Structure**: Django communicates with the FastAPI service by sending:
  ```json
  {
    "gloss": "<gloss_text>",
    "return_format": "npy"
  }
  ```
* **Storage**: The backend does **not** save the returned `file_path` anywhere. It is only passed back to the client/console as part of the response payload.

---

## 4. Is Gemini Output Passed to Pose Model?

> [!WARNING]
> **No.** The backend currently has Gemini gloss generation and AI pose generation as separate flows.

There is no code in the entire backend that routes the output of `generate_sign_gloss(...)` or the saved `supporting_text` directly to `generate_pose_from_gloss(...)` during the prescription or sign-generation flows.

### Independent Operations:
1. **Gemini Gloss Generation Flow**: Converts instructions to Arabic text gloss and saves it to `supporting_text`.
2. **AI Pose Generation Flow**: Takes an arbitrary text input from the client, queries the FastAPI service, and returns the `.npy` output path without persisting it.

### Missing Link:
Orchestration within `PharmacistPrescriptionViewSet.generate_sign` to trigger `generate_pose_from_gloss()` using the newly generated `gloss_text`, and database columns to persist the pose file path, shape, and metadata.

---

## 5. Prescription Item Sign Endpoint

The endpoint for generating sign-related outputs for a prescription item is analyzed below:

* **Exact Path**: `/api/pharmacist/prescriptions/<prescription_id>/items/<item_id>/generate-sign/`
* **View Action**: `generate_sign` inside `PharmacistPrescriptionViewSet` in `prescriptions/views.py` (Lines 782–858).
* **Permissions**: Protected by `[IsAuthenticated, IsPharmacistRole]`.
* **Request Body**: Empty POST request (`{}`).
* **Source Text Used**: Priority: `instructions_transcript_edited` $\rightarrow$ `instructions_transcript_raw` $\rightarrow$ `instructions_text`.
* **Does it call Gemini?**: **Yes**, via `result = generate_sign_gloss(source_text)` (Line 828).
* **Does it call AI Pose Service?**: **No**.
* **Response Shape**:
  ```json
  {
    "item_id": 2,
    "sign_status": "completed",
    "gloss_text": "دواء حبة الصبح قبل الاكل",
    "supporting_text": "دواء حبة الصبح قبل الاكل",
    "video_url": null,
    "output_type": "gloss_only",
    "video_generation_supported": false,
    "detail": "Gloss generated successfully"
  }
  ```
* **Updated Fields on `PrescriptionItem`**:
  * `supporting_text`: updated with the generated gloss text.
  * `sign_status`: updated to `completed` or `failed`.
* **Response Details**:
  * `video_url` is hardcoded to `None`.
  * Pose `file_path` is completely absent.

---

## 6. Pose Result Storage

There are **no fields or tables** in the current database schema to support storing pose outputs:
* **What exists on `PrescriptionItem`**: `supporting_text` (stores the text gloss), `sign_language_video` (stores the final translated video file path), and `sign_status` (transitions).
* **What does NOT exist**: No fields such as `pose_file_path`, `pose_shape`, `ai_metadata`, or separate `SignPoseGeneration` tables exist.
* **Verdict**: The current data model **cannot store** FastAPI pose results. It only supports storing the gloss text and a final video URL.

---

## 7. Tests or Commands Run

To verify service functionality, targeted commands were run:

1. **System Check**:
   ```bash
   python manage.py check
   ```
   *Result: System check identified no issues (0 silenced).*

2. **Integration Verification CLI Tool**:
   ```bash
   python manage.py test_ai_pose --gloss "دواء حبة الصبح قبل الاكل"
   ```
   *Result: Successfully passed health check and pose generation against the active FastAPI service.*
   * **FastAPI Health**: `{'status': 'ok', 'model_loaded': True, 'device': 'cuda'}`
   * **Pose Output**: Generated file path `generated_outputs/gen_9e721705fed747b7a03beca8f4399818.npy` with shape `[128, 576]`.

---

## 8. Verdict

### **Partially connected**

The Gemini gloss generation works perfectly in the prescription lifecycle, and the AI pose generation works separately via its own REST endpoint and management command, but they are not yet orchestrated into a single prescription pipeline.

---

## 9. Missing Link If Any

1. **Pipeline Orchestration**: `generate_sign` in `prescriptions/views.py` lacks a call to `generate_pose_from_gloss` using the output returned by Gemini.
2. **Database Support**: The `PrescriptionItem` model lacks fields to store the generated pose `.npy` path, shape, and metadata.

---

## 10. Recommended Minimal Backend Change

To fully automate the pipeline so that approved text $\rightarrow$ Gemini gloss $\rightarrow$ AI pose is executed in a single request, the following changes are recommended:

### Step 1: Add Pose Storage Fields to `PrescriptionItem`
Modify `PrescriptionItem` in `prescriptions/models.py` to add storage fields (without requiring a separate table for simplicity):
```python
# prescriptions/models.py
pose_file_path = models.CharField(max_length=255, blank=True, default="")
pose_shape = models.JSONField(null=True, blank=True)
ai_metadata = models.JSONField(null=True, blank=True)
```
*(Add these fields to `update_fields` lists in save/update methods as appropriate).*

### Step 2: Orchestrate the View Pipeline
Update `generate_sign` in `prescriptions/views.py` to chain the calls:
```python
# prescriptions/views.py
from ai_integration.services import generate_pose_from_gloss
from ai_integration.exceptions import AIPoseGenerationError

# Inside generate_sign View Action:
# ... after calling Gemini and successfully saving supporting_text:
try:
    pose_result = generate_pose_from_gloss(
        gloss=item.supporting_text, 
        return_format="npy"
    )
    # Save the pose results directly on the item
    item.pose_file_path = pose_result.get("file_path", "")
    item.pose_shape = pose_result.get("pose_shape")
    item.ai_metadata = pose_result.get("metadata", {})
    item.save(update_fields=["pose_file_path", "pose_shape", "ai_metadata", "updated_at"])
except AIPoseGenerationError as e:
    # Set status to failed or log warning if pose generation is non-blocking
    logger.error(f"Failed to generate pose for item {item.id}: {e.message}")
    # Option: mark_prescription_item_sign_failed(item)
```

### Step 3: Update Response Payload
Update the API response structure to return full details to the frontend:
```python
return Response(
    {
        "item_id": item.id,
        "sign_status": item.sign_status,
        "gloss_text": item.supporting_text,
        "supporting_text": item.supporting_text,
        "pose": {
            "success": True,
            "pose_shape": item.pose_shape,
            "file_path": item.pose_file_path,
            "metadata": item.ai_metadata
        },
        "video_url": None,
        "output_type": "gloss_and_pose",
        "detail": "Gloss and Pose generated successfully",
    }
)
```

---

## 11. Exact Files Inspected

* **[`pharmasign/settings.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/pharmasign/settings.py)** — Application setup and Decouple settings.
* **[`pharmasign/api_urls.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/pharmasign/api_urls.py)** — centralized API routing.
* **[`prescriptions/models.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/prescriptions/models.py)** — prescription database tables.
* **[`prescriptions/services.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/prescriptions/services.py)** — Gemini prompting and status updates.
* **[`prescriptions/views.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/prescriptions/views.py)** — viewsets and prescription actions.
* **[`prescriptions/urls.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/prescriptions/urls.py)** — prescription endpoints definition.
* **[`ai_integration/services.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/ai_integration/services.py)** — FastAPI communication client.
* **[`ai_integration/views.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/ai_integration/views.py)** — AI API endpoints.
* **[`ai_integration/management/commands/test_ai_pose.py`](file:///c:/Users/alaan/Desktop/PharmaSign_BackEnd/ai_integration/management/commands/test_ai_pose.py)** — administrative verification commands.
