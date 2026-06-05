import argparse
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT.parents[2]
DEFAULT_SOURCE_DIR = Path(r"C:\Users\alaan\Desktop\Sign_Tokens\Tokens")
BACKUP_DIR = PROJECT_ROOT.parent / "large_sentence_experiment_backup_before_tokens_rebuild"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
CLEANED_POSE_FULL_DIR = PROJECT_ROOT / "assets" / "cleaned_pose_full"
CLEANED_POSE_DIR = PROJECT_ROOT / "assets" / "cleaned_pose"

TOKEN_POSE_FULL_METADATA_PATH = OUTPUTS_DIR / "token_pose_full_metadata.csv"
TOKEN_POSE_METADATA_PATH = OUTPUTS_DIR / "token_pose_metadata.csv"
TOKEN_INDEX_PATH = OUTPUTS_DIR / "token_index.json"
TOKEN_VOCAB_PATH = OUTPUTS_DIR / "token_vocabulary.txt"
TOKEN_ALIAS_MAP_PATH = OUTPUTS_DIR / "token_alias_map.json"

INVALID_FILENAME_CHARS = r'<>:"/\|?*'
ARABIC_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670]")


def ensure_project_import_path():
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))


ensure_project_import_path()
from src.sign_retrieval.text_normalization import normalize_arabic_text  # noqa: E402


def ensure_backup():
    if BACKUP_DIR.exists():
        return
    print(f"Creating backup: {BACKUP_DIR}")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(PROJECT_ROOT, BACKUP_DIR, ignore=ignore)


def safe_file_id(token: str, used_ids: set[str]) -> str:
    cleaned = unicodedata.normalize("NFC", token).strip().replace(" ", "_")
    cleaned = "".join("_" if ch in INVALID_FILENAME_CHARS else ch for ch in cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    if not cleaned:
        cleaned = "token"

    candidate = cleaned
    counter = 2
    while candidate in used_ids:
        candidate = f"{cleaned}_{counter}"
        counter += 1
    used_ids.add(candidate)
    return candidate


def normalized_aliases(token: str) -> list[str]:
    aliases = {token, normalize_arabic_text(token)}
    no_diacritics = ARABIC_DIACRITICS.sub("", token)
    aliases.add(" ".join(no_diacritics.split()))
    aliases.add(normalize_arabic_text(no_diacritics))
    return sorted(alias for alias in aliases if alias)


def landmark_xyz_list(landmarks, count: int) -> list[float]:
    values: list[float] = []
    if landmarks is None:
        return [0.0] * count * 3
    source = landmarks.landmark
    for idx in range(count):
        if idx < len(source):
            lm = source[idx]
            values.extend([float(lm.x), float(lm.y), float(lm.z)])
        else:
            values.extend([0.0, 0.0, 0.0])
    return values


def landmark_xyzw_list(landmarks, count: int, include_visibility: bool) -> list[float]:
    values: list[float] = []
    if landmarks is None:
        return [0.0] * count * 4
    source = landmarks.landmark
    for idx in range(count):
        if idx < len(source):
            lm = source[idx]
            visibility = float(getattr(lm, "visibility", 1.0)) if include_visibility else 1.0
            values.extend([float(lm.x), float(lm.y), float(lm.z), visibility])
        else:
            values.extend([0.0, 0.0, 0.0, 0.0])
    return values


def extract_video(video_path: Path) -> tuple[np.ndarray, np.ndarray, float, float]:
    import mediapipe as mp

    solutions = getattr(mp, "solutions", None)
    holistic_module = getattr(solutions, "holistic", None) if solutions is not None else None
    if holistic_module is None:
        raise RuntimeError(
            "Installed MediaPipe does not expose mp.solutions.holistic. "
            "Install a MediaPipe build that includes the classic Holistic API."
        )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count_hint = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_seconds = frame_count_hint / fps if fps > 0 and frame_count_hint > 0 else 0.0

    full_frames: list[list[float]] = []
    compact_frames: list[list[float]] = []
    holistic = holistic_module.Holistic(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        enable_segmentation=False,
        refine_face_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = holistic.process(rgb)

            full_values = []
            full_values.extend(landmark_xyz_list(result.pose_landmarks, 33))
            full_values.extend(landmark_xyz_list(result.face_landmarks, 468))
            full_values.extend(landmark_xyz_list(result.left_hand_landmarks, 21))
            full_values.extend(landmark_xyz_list(result.right_hand_landmarks, 21))
            full_frames.append(full_values)

            compact_values = []
            compact_values.extend(landmark_xyzw_list(result.pose_landmarks, 33, include_visibility=True))
            compact_values.extend(landmark_xyzw_list(result.left_hand_landmarks, 21, include_visibility=False))
            compact_values.extend(landmark_xyzw_list(result.right_hand_landmarks, 21, include_visibility=False))
            compact_values.extend(landmark_xyzw_list(result.face_landmarks, 75, include_visibility=False))
            compact_frames.append(compact_values)
    finally:
        holistic.close()
        cap.release()

    if not full_frames:
        raise RuntimeError("No frames were decoded from the video.")

    full_arr = np.asarray(full_frames, dtype=np.float32)
    compact_arr = np.asarray(compact_frames, dtype=np.float32)
    if full_arr.ndim != 2 or full_arr.shape[1] != 1629:
        raise RuntimeError(f"Invalid full pose shape: {full_arr.shape}")
    if compact_arr.ndim != 2 or compact_arr.shape[1] != 576:
        raise RuntimeError(f"Invalid compact pose shape: {compact_arr.shape}")
    if duration_seconds == 0.0 and fps > 0:
        duration_seconds = len(full_arr) / fps
    return full_arr, compact_arr, fps, duration_seconds


def build_index_entry(file_id: str, token: str, video_path: Path) -> dict:
    return {
        "id": file_id,
        "video_path": str(video_path).replace("\\", "/"),
        "absolute_video_path": str(video_path.resolve()).replace("\\", "/"),
        "signer_id": "local",
        "take_id": "T01",
        "source_text": token,
        "token": token,
        "pose_path": str((CLEANED_POSE_DIR / normalize_arabic_text(token) / f"{file_id}.npy").resolve()).replace("\\", "/"),
        "full_pose_path": str((CLEANED_POSE_FULL_DIR / normalize_arabic_text(token) / f"{file_id}.npy").resolve()).replace("\\", "/"),
        "frames": None,
        "feature_dim": 1629,
        "source_video": str(video_path.resolve()).replace("\\", "/"),
    }


def main():
    parser = argparse.ArgumentParser(description="Extract MediaPipe Holistic token poses for PharmaSign retrieval.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()

    source_dir = args.source_dir
    if not source_dir.exists():
        raise FileNotFoundError(f"Source token video folder not found: {source_dir}")

    if not args.skip_backup:
        ensure_backup()

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_POSE_FULL_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_POSE_DIR.mkdir(parents=True, exist_ok=True)

    videos = sorted(source_dir.rglob("*.mp4"), key=lambda p: str(p.name))
    used_ids: set[str] = set()
    metadata_rows: list[dict] = []
    token_index: dict[str, list[dict]] = {}
    alias_map: dict[str, list[str]] = {}

    print(f"Videos found: {len(videos)}")
    for video_path in tqdm(videos, desc="Extracting token videos"):
        token = video_path.stem.strip()
        normalized_token = normalize_arabic_text(token)
        file_id = safe_file_id(token, used_ids)
        full_pose_path = CLEANED_POSE_FULL_DIR / normalized_token / f"{file_id}.npy"
        compact_pose_path = CLEANED_POSE_DIR / normalized_token / f"{file_id}.npy"
        row = {
            "id": file_id,
            "token": token,
            "normalized_token": normalized_token,
            "file_id": file_id,
            "video_path": str(video_path.resolve()),
            "pose_path": str(compact_pose_path.resolve()),
            "full_pose_path": str(full_pose_path.resolve()),
            "frames": 0,
            "feature_dim": 1629,
            "landmark_count": 543,
            "fps": 0.0,
            "duration_seconds": 0.0,
            "source_filename": video_path.name,
            "extraction_status": "failed",
            "success": False,
            "trim_start_frames": 0,
            "trim_end_frames": 0,
            "error_message": "",
        }

        try:
            full_arr, compact_arr, fps, duration_seconds = extract_video(video_path)
            full_pose_path.parent.mkdir(parents=True, exist_ok=True)
            compact_pose_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(full_pose_path, full_arr)
            np.save(compact_pose_path, compact_arr)

            row.update(
                {
                    "frames": int(full_arr.shape[0]),
                    "fps": fps,
                    "duration_seconds": duration_seconds,
                    "extraction_status": "success",
                    "success": True,
                    "error_message": "",
                }
            )
            entry = build_index_entry(file_id, token, video_path)
            entry["frames"] = int(full_arr.shape[0])
            token_index.setdefault(normalized_token, []).append(entry)
            alias_map[normalized_token] = normalized_aliases(token)
        except Exception as exc:
            row["error_message"] = str(exc)

        metadata_rows.append(row)

    metadata_df = pd.DataFrame(metadata_rows)
    success_count = int((metadata_df["extraction_status"] == "success").sum())
    failed_count = int((metadata_df["extraction_status"] == "failed").sum())

    if success_count == 0:
        failed_full_metadata = OUTPUTS_DIR / "token_pose_full_metadata_failed.csv"
        failed_compact_metadata = OUTPUTS_DIR / "token_pose_metadata_failed.csv"
        metadata_df.to_csv(failed_full_metadata, index=False, encoding="utf-8-sig")
        compact_df = metadata_df.copy()
        compact_df["feature_dim"] = 576
        compact_df["landmark_count"] = 144
        compact_df.to_csv(failed_compact_metadata, index=False, encoding="utf-8-sig")
        print("No videos were successfully extracted. Existing active retrieval index files were not replaced.")
        print(f"Failed full metadata written to: {failed_full_metadata}")
        print(f"Failed compact metadata written to: {failed_compact_metadata}")
        sample_token = None
    else:
        metadata_df.to_csv(TOKEN_POSE_FULL_METADATA_PATH, index=False, encoding="utf-8-sig")

        compact_df = metadata_df.copy()
        compact_df["feature_dim"] = 576
        compact_df["landmark_count"] = 144
        compact_df.to_csv(TOKEN_POSE_METADATA_PATH, index=False, encoding="utf-8-sig")

        vocabulary = sorted(token_index.keys())
        with open(TOKEN_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(token_index, f, ensure_ascii=False, indent=2)
        with open(TOKEN_VOCAB_PATH, "w", encoding="utf-8") as f:
            for token in vocabulary:
                f.write(token + "\n")
        with open(TOKEN_ALIAS_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(alias_map, f, ensure_ascii=False, indent=2)
        sample_token = vocabulary[0] if vocabulary else None

    print("Extraction complete.")
    print(f"Videos found: {len(videos)}")
    print(f"Successfully extracted: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"cleaned_pose_full: {CLEANED_POSE_FULL_DIR}")
    print(f"cleaned_pose: {CLEANED_POSE_DIR}")
    print(f"token_pose_full_metadata: {TOKEN_POSE_FULL_METADATA_PATH}")
    print(f"token_pose_metadata: {TOKEN_POSE_METADATA_PATH}")
    print(f"token_index: {TOKEN_INDEX_PATH}")
    print(f"token_vocabulary: {TOKEN_VOCAB_PATH}")
    print(f"token_alias_map: {TOKEN_ALIAS_MAP_PATH}")
    print(f"Sample token: {sample_token}")


if __name__ == "__main__":
    main()
