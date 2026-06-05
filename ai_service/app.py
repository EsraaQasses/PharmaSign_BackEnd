import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional
from uuid import uuid4

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from matplotlib.animation import writers
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_service")

try:
    from ai_service.avatar_renderer import render_avatar_from_npy
except Exception as exc:
    render_avatar_from_npy = None
    logger.exception("Failed to import PharmaSign avatar renderer: %s", exc)

BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_GENERATED_DIR = MEDIA_ROOT / "generated"
POSE_OUTPUT_DIR = MEDIA_GENERATED_DIR / "poses"
SKELETON_VIDEO_OUTPUT_DIR = MEDIA_GENERATED_DIR / "skeleton_videos"
AVATAR_VIDEO_OUTPUT_DIR = MEDIA_GENERATED_DIR / "avatar_videos"
SIGN_RETRIEVAL_PROJECT_ROOT = Path(
    os.getenv(
        "SIGN_RETRIEVAL_PROJECT_ROOT",
        str(BASE_DIR / "external_data" / "sign_retrieval" / "large_sentence_experiment"),
    )
).resolve()

if str(SIGN_RETRIEVAL_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(SIGN_RETRIEVAL_PROJECT_ROOT))

try:
    from src.sign_retrieval.generator import SignGenerator
    from src.sign_retrieval.gloss_normalizer import normalize_gloss_to_vocabulary
    from src.sign_retrieval import config
except Exception as exc:
    SignGenerator = None
    normalize_gloss_to_vocabulary = None
    config = None
    logger.exception("Failed to import original SignGenerator retrieval system: %s", exc)

for output_dir in (POSE_OUTPUT_DIR, SKELETON_VIDEO_OUTPUT_DIR, AVATAR_VIDEO_OUTPUT_DIR):
    output_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PharmaSign Gloss-to-Pose Retrieval Service", version="2.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(
    "/media/generated",
    StaticFiles(directory=str(MEDIA_GENERATED_DIR)),
    name="media_generated",
)

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

POSE_CONNECTIONS = [
    (11, 12),
    (11, 13), (13, 15),
    (12, 14), (14, 16),
    (11, 23), (12, 24),
    (23, 24),
]


class GenerateRequest(BaseModel):
    text: Optional[str] = None
    gloss: Optional[str] = None
    pose_format: Optional[str] = None
    return_format: Optional[str] = None
    return_video: Optional[bool] = False
    return_avatar: Optional[bool] = False
    debug_segments: Optional[bool] = False


class CachedSignGenerator(SignGenerator if SignGenerator is not None else object):
    def __init__(self):
        if SignGenerator is None:
            raise RuntimeError("SignGenerator is not available.")
        super().__init__()
        self._resources_loaded_by_format: set[str] = set()

    def load_resources(self, pose_format: str = "576"):
        if pose_format in self._resources_loaded_by_format:
            return
        super().load_resources(pose_format=pose_format)
        self._resources_loaded_by_format.add(pose_format)


generator = CachedSignGenerator() if SignGenerator is not None else None


def _normalize_pose_format(request: GenerateRequest) -> str:
    if request.pose_format:
        requested = request.pose_format.lower().strip()
    elif request.return_avatar:
        requested = "full"
    else:
        requested = (request.return_format or "576").lower().strip()
    if requested in {"npy", "json", "pose", "default"}:
        return "576"
    if requested in {"576", "full"}:
        return requested
    raise HTTPException(
        status_code=400,
        detail="Invalid pose format. Supported values: '576', 'full', 'npy', or 'json'.",
    )


def _media_url(path: Path | None) -> str | None:
    if not path:
        return None
    try:
        relative_path = path.resolve().relative_to(MEDIA_ROOT.resolve())
    except ValueError:
        return None
    return f"/media/{relative_path.as_posix()}"


def render_pose_video(
    input_path: Path,
    output_path: Path,
    pose_format: str,
    width: int = 900,
    height: int = 900,
    fps: int = 25,
):
    pose = np.load(input_path)
    frame_count, pose_dim = pose.shape

    if pose_format == "full":
        expected_pose_dim = 1629
        num_landmarks = 543
        num_coords = 3
        face_offset = 33
        left_hand_offset = 501
        right_hand_offset = 522
    else:
        expected_pose_dim = 576
        num_landmarks = 144
        num_coords = 4
        face_offset = 75
        left_hand_offset = 33
        right_hand_offset = 54

    if pose_dim != expected_pose_dim:
        raise ValueError(
            f"Expected pose dimension {expected_pose_dim} for format '{pose_format}', got {pose_dim}."
        )

    landmarks = pose.reshape(frame_count, num_landmarks, num_coords)
    valid_xy = landmarks[:, :, :2][np.any(landmarks[:, :, :2] != 0.0, axis=2)]
    if valid_xy.size == 0:
        raise ValueError("Pose file contains only zeros.")

    min_x, min_y = valid_xy.min(axis=0)
    max_x, max_y = valid_xy.max(axis=0)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    scale = min(width * 0.85 / max(max_x - min_x, 1e-5), height * 0.85 / max(max_y - min_y, 1e-5))

    def to_screen(x, y):
        return int(width / 2.0 + (x - center_x) * scale), int(height / 2.0 + (y - center_y) * scale)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    try:
        for frame_idx in range(frame_count):
            frame_img = np.zeros((height, width, 3), dtype=np.uint8)
            points = {}
            for landmark_idx in range(num_landmarks):
                x = landmarks[frame_idx, landmark_idx, 0]
                y = landmarks[frame_idx, landmark_idx, 1]
                if x != 0.0 or y != 0.0:
                    points[landmark_idx] = to_screen(x, y)

            for a, b in POSE_CONNECTIONS:
                if a in points and b in points:
                    cv2.line(frame_img, points[a], points[b], (100, 255, 100), 2)

            for offset, color in ((left_hand_offset, (255, 0, 180)), (right_hand_offset, (0, 255, 255))):
                for a, b in HAND_CONNECTIONS:
                    la = offset + a
                    lb = offset + b
                    if la in points and lb in points:
                        cv2.line(frame_img, points[la], points[lb], color, 2)

            face_end = face_offset + 468 if pose_format == "full" else 144
            for landmark_idx in range(face_offset, face_end):
                if landmark_idx in points:
                    cv2.circle(frame_img, points[landmark_idx], 1, (200, 200, 200), -1)

            for landmark_idx in range(33):
                if landmark_idx in points:
                    cv2.circle(frame_img, points[landmark_idx], 4, (255, 150, 0), -1)

            writer.write(frame_img)
    finally:
        writer.release()


@app.get("/health")
def health_check():
    token_index_path = getattr(config, "TOKEN_INDEX_PATH", None) if config is not None else None
    cleaned_pose_dir = getattr(config, "CLEANED_POSE_DIR", None) if config is not None else None
    cleaned_pose_full_dir = getattr(config, "CLEANED_POSE_FULL_DIR", None) if config is not None else None

    ready = (
        SignGenerator is not None
        and SIGN_RETRIEVAL_PROJECT_ROOT.exists()
        and token_index_path is not None
        and Path(token_index_path).exists()
        and cleaned_pose_dir is not None
        and Path(cleaned_pose_dir).exists()
    )
    return {
        "status": "ok" if ready else "error",
        "service": "PharmaSign Gloss-to-Pose Retrieval Service",
        "retrieval_type": "original_sign_generator_pose_retrieval",
        "project_root": str(SIGN_RETRIEVAL_PROJECT_ROOT),
        "project_root_exists": SIGN_RETRIEVAL_PROJECT_ROOT.exists(),
        "token_index_path": str(token_index_path) if token_index_path else None,
        "token_index_exists": Path(token_index_path).exists() if token_index_path else False,
        "cleaned_pose_dir": str(cleaned_pose_dir) if cleaned_pose_dir else None,
        "cleaned_pose_dir_exists": Path(cleaned_pose_dir).exists() if cleaned_pose_dir else False,
        "cleaned_pose_full_dir": str(cleaned_pose_full_dir) if cleaned_pose_full_dir else None,
        "cleaned_pose_full_dir_exists": Path(cleaned_pose_full_dir).exists() if cleaned_pose_full_dir else False,
        "pose_output_dir": str(POSE_OUTPUT_DIR),
        "skeleton_video_output_dir": str(SKELETON_VIDEO_OUTPUT_DIR),
        "avatar_video_output_dir": str(AVATAR_VIDEO_OUTPUT_DIR),
        "avatar_renderer_available": render_avatar_from_npy is not None,
        "ffmpeg_available": writers.is_available("ffmpeg"),
    }


@app.post("/generate-pose")
@app.post("/generate-sign")
def generate_pose_endpoint(request: GenerateRequest):
    if generator is None:
        raise HTTPException(
            status_code=503,
            detail="Original SignGenerator retrieval system is not available.",
        )

    input_text = (request.gloss or request.text or "").strip()
    if not input_text:
        raise HTTPException(
            status_code=400,
            detail="Missing parameter: 'text' or 'gloss' must be provided.",
        )

    pose_format = _normalize_pose_format(request)
    normalization = normalize_gloss_to_vocabulary(input_text) if normalize_gloss_to_vocabulary else None
    retrieval_text = (
        normalization.get("normalized_gloss")
        if normalization and normalization.get("normalized_gloss")
        else input_text
    )
    output_id = uuid4().hex
    pose_path = POSE_OUTPUT_DIR / f"pose_{output_id}.npy"
    report = None

    with tempfile.TemporaryDirectory(prefix="pharmasign_pose_") as tmp_dir:
        work_dir = Path(tmp_dir)
        try:
            report = generator.generate(
                text=retrieval_text,
                selection_mode="best",
                out_dir=work_dir,
                pose_only=True,
                skip_video=True,
                blend_frames=8,
                smoothing_window=5,
                pose_format=pose_format,
                debug_segments=bool(request.debug_segments),
            )
        except Exception as exc:
            logger.exception("Original SignGenerator retrieval failed.")
            return {
                "success": False,
                "error": str(exc),
                "text": input_text,
                "gloss": input_text,
                "normalized_gloss": retrieval_text,
                "pose_file": None,
                "video_path": None,
                "generated_video_url": None,
                "avatar_video_path": None,
                "missing_tokens": [],
            }

        generated_assets = report.get("generated_assets") or {}
        generated_pose = Path(generated_assets["pose"]) if generated_assets.get("pose") else None
        if generated_pose and generated_pose.exists():
            shutil.copy2(generated_pose, pose_path)

    pose_shape = report.get("final_npy_shape") if report else None
    if pose_shape is None and pose_path.exists():
        try:
            pose_shape = list(np.load(pose_path).shape)
        except Exception:
            logger.warning("Could not read generated pose shape from %s", pose_path)

    skeleton_video_path = None
    skeleton_video_url = None
    if request.return_video and pose_path.exists():
        skeleton_video_path = SKELETON_VIDEO_OUTPUT_DIR / f"skeleton_{output_id}.mp4"
        try:
            render_pose_video(pose_path, skeleton_video_path, pose_format)
            skeleton_video_url = _media_url(skeleton_video_path)
        except Exception as exc:
            skeleton_video_path = None
            logger.exception("Skeleton video rendering failed: %s", exc)

    pose_url = _media_url(pose_path) if pose_path.exists() else None
    avatar_video_path = None
    avatar_video_url = None
    avatar_rendering_success = False
    avatar_error = None

    if request.return_avatar:
        if render_avatar_from_npy is None:
            avatar_error = "Avatar renderer is not available."
        elif not pose_path.exists():
            avatar_error = "Avatar rendering skipped because no pose file was generated."
        elif not pose_shape or len(pose_shape) < 2 or int(pose_shape[1]) != 1629:
            avatar_error = f"Avatar rendering requires pose shape [frames, 1629], got {pose_shape}."
        else:
            avatar_video_file = AVATAR_VIDEO_OUTPUT_DIR / f"avatar_{output_id}.mp4"
            try:
                render_avatar_from_npy(str(pose_path), str(avatar_video_file), fps=24, bitrate=5000)
                avatar_video_url = _media_url(avatar_video_file)
                avatar_video_path = avatar_video_url
                avatar_rendering_success = bool(avatar_video_url)
            except Exception as exc:
                avatar_error = str(exc)
                logger.exception("Avatar video rendering failed: %s", exc)

    if report is not None:
        report.setdefault("generated_assets", {})
        report["generated_assets"]["pose"] = pose_url
        report["generated_assets"]["video"] = skeleton_video_url
        report["generated_assets"]["avatar_video"] = avatar_video_url
        report["avatar_rendering"] = {
            "requested": bool(request.return_avatar),
            "success": avatar_rendering_success,
            "avatar_video_path": avatar_video_path,
            "avatar_video_url": avatar_video_url,
            "error": avatar_error,
        }
        report["original_input_text"] = input_text
        report["normalized_retrieval_gloss"] = retrieval_text
        report["gloss_normalization"] = normalization

    return {
        "success": bool(pose_url),
        "text": input_text,
        "gloss": input_text,
        "normalized_gloss": retrieval_text,
        "pose_shape": pose_shape,
        "pose_file": pose_url,
        "file_path": pose_url,
        "npy_path": pose_url,
        "video_file": skeleton_video_url,
        "video_path": skeleton_video_url,
        "generated_video_path": skeleton_video_url,
        "generated_video_url": skeleton_video_url,
        "avatar_rendering_success": avatar_rendering_success,
        "avatar_video_path": avatar_video_path,
        "avatar_video_url": avatar_video_url,
        "avatar_error": avatar_error,
        "missing_tokens": report.get("missing_tokens", []) if report else [],
        "matched_units": report.get("matched_units", []) if report else [],
        "retrieved_tokens": report.get("retrieved_tokens", []) if report else [],
        "gloss_normalization": normalization,
        "metadata": {
            "retrieval_type": "original_sign_generator_pose_retrieval",
            "project_root": str(SIGN_RETRIEVAL_PROJECT_ROOT),
            "gloss_normalization": normalization,
            "report": report,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_service.app:app", host="127.0.0.1", port=8002, reload=True)
