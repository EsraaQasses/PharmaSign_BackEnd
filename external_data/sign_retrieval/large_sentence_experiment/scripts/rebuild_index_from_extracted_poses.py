import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_VIDEO_DIR = Path(r"C:\Users\alaan\Desktop\Sign_Tokens\Tokens")
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
METADATA_DIR = PROJECT_ROOT / "metadata"
CLEANED_POSE_DIR = PROJECT_ROOT / "assets" / "cleaned_pose"
CLEANED_POSE_FULL_DIR = PROJECT_ROOT / "assets" / "cleaned_pose_full"

TOKEN_INDEX_PATH = OUTPUTS_DIR / "token_index.json"
TOKEN_VOCAB_PATH = OUTPUTS_DIR / "token_vocabulary.txt"
TOKEN_ALIAS_MAP_PATH = OUTPUTS_DIR / "token_alias_map.json"
TOKEN_POSE_METADATA_PATH = OUTPUTS_DIR / "token_pose_metadata.csv"
TOKEN_POSE_FULL_METADATA_PATH = OUTPUTS_DIR / "token_pose_full_metadata.csv"
TOKEN_FOLDER_METADATA_PATH = METADATA_DIR / "metadata_tokens_from_folders.csv"


def ensure_project_import_path():
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))


ensure_project_import_path()
from src.sign_retrieval.text_normalization import normalize_arabic_text  # noqa: E402


def to_forward_slash(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def source_video_for_token(token: str) -> Path:
    exact = SOURCE_VIDEO_DIR / f"{token}.mp4"
    if exact.exists():
        return exact

    normalized_token = normalize_arabic_text(token)
    for video_path in SOURCE_VIDEO_DIR.glob("*.mp4"):
        if normalize_arabic_text(video_path.stem) == normalized_token:
            return video_path
    return exact


def first_npy(folder: Path) -> Path | None:
    files = sorted(folder.glob("*.npy"), key=lambda p: p.name)
    return files[0] if files else None


def aliases_for(token: str) -> list[str]:
    aliases = {token, normalize_arabic_text(token)}
    return sorted(alias for alias in aliases if alias)


def main():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    token_dirs = sorted(
        [path for path in CLEANED_POSE_FULL_DIR.iterdir() if path.is_dir()],
        key=lambda p: normalize_arabic_text(p.name),
    )

    token_index: dict[str, list[dict]] = {}
    vocabulary: list[str] = []
    alias_map: dict[str, list[str]] = {}
    token_folder_rows: list[dict] = []
    full_pose_rows: list[dict] = []
    compact_pose_rows: list[dict] = []

    token_counter = 1
    for token_dir in token_dirs:
        token = token_dir.name
        normalized_token = normalize_arabic_text(token)
        if not normalized_token:
            continue

        full_pose_path = first_npy(token_dir)
        compact_token_dir = CLEANED_POSE_DIR / token
        compact_pose_path = first_npy(compact_token_dir)
        if full_pose_path is None:
            continue

        stable_id = f"TOK_{token_counter:04d}_T01"
        target_full_pose = token_dir / f"{stable_id}.npy"
        if full_pose_path.name != target_full_pose.name:
            target_full_pose.write_bytes(full_pose_path.read_bytes())
        full_pose_path = target_full_pose

        if compact_pose_path is not None:
            target_compact_pose = compact_token_dir / f"{stable_id}.npy"
            if compact_pose_path.name != target_compact_pose.name:
                target_compact_pose.write_bytes(compact_pose_path.read_bytes())
            compact_pose_path = target_compact_pose

        source_video = source_video_for_token(token)
        video_rel = f"Tokens/{source_video.name}"
        take = {
            "id": stable_id,
            "video_path": video_rel,
            "absolute_video_path": to_forward_slash(source_video),
            "signer_id": "S01",
            "take_id": "T01",
            "source_text": token,
        }
        token_index[normalized_token] = [take]
        vocabulary.append(normalized_token)
        alias_map[normalized_token] = aliases_for(token)

        full_arr = np.load(full_pose_path, mmap_mode="r")
        full_frames = int(full_arr.shape[0]) if full_arr.ndim == 2 else 0
        full_feature_dim = int(full_arr.shape[1]) if full_arr.ndim == 2 else 0
        compact_frames = 0
        compact_feature_dim = 0
        if compact_pose_path and compact_pose_path.exists():
            compact_arr = np.load(compact_pose_path, mmap_mode="r")
            compact_frames = int(compact_arr.shape[0]) if compact_arr.ndim == 2 else 0
            compact_feature_dim = int(compact_arr.shape[1]) if compact_arr.ndim == 2 else 0

        base_row = {
            "id": stable_id,
            "token": token,
            "gloss_clean": token,
            "file_id": stable_id,
            "video_path": video_rel,
            "absolute_video_path": to_forward_slash(source_video),
            "source_filename": source_video.name,
            "extraction_status": "success",
            "success": True,
            "signer_id": "S01",
            "take_id": "T01",
            "trim_start_frames": 0,
            "trim_end_frames": 0,
            "error_message": "",
        }

        full_pose_rows.append(
            {
                **base_row,
                "pose_path": to_forward_slash(compact_pose_path) if compact_pose_path else "",
                "full_pose_path": to_forward_slash(full_pose_path),
                "frames": full_frames,
                "feature_dim": full_feature_dim,
                "landmark_count": 543,
            }
        )
        compact_pose_rows.append(
            {
                **base_row,
                "pose_path": to_forward_slash(compact_pose_path) if compact_pose_path else "",
                "full_pose_path": to_forward_slash(full_pose_path),
                "frames": compact_frames,
                "feature_dim": compact_feature_dim,
                "landmark_count": 144 if compact_feature_dim == 576 else 0,
            }
        )
        token_folder_rows.append(
            {
                "id": stable_id,
                "category": "token",
                "gloss_clean": token,
                "video_path": video_rel,
                "absolute_video_path": to_forward_slash(source_video),
                "signer_id": "S01",
                "take_id": "T01",
                "video_exists": bool(source_video.exists()),
            }
        )
        token_counter += 1

    vocabulary = sorted(vocabulary)
    with open(TOKEN_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(token_index, f, ensure_ascii=False, indent=2)
    with open(TOKEN_VOCAB_PATH, "w", encoding="utf-8") as f:
        for token in vocabulary:
            f.write(token + "\n")
    with open(TOKEN_ALIAS_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(alias_map, f, ensure_ascii=False, indent=2)

    pd.DataFrame(full_pose_rows).to_csv(TOKEN_POSE_FULL_METADATA_PATH, index=False, encoding="utf-8-sig")
    pd.DataFrame(compact_pose_rows).to_csv(TOKEN_POSE_METADATA_PATH, index=False, encoding="utf-8-sig")
    pd.DataFrame(token_folder_rows).to_csv(TOKEN_FOLDER_METADATA_PATH, index=False, encoding="utf-8-sig")

    print(f"Rebuilt tokens: {len(token_index)}")
    print(f"token_index: {TOKEN_INDEX_PATH}")
    print(f"token_vocabulary: {TOKEN_VOCAB_PATH}")
    print(f"token_alias_map: {TOKEN_ALIAS_MAP_PATH}")
    print(f"token_pose_full_metadata: {TOKEN_POSE_FULL_METADATA_PATH}")
    print(f"token_pose_metadata: {TOKEN_POSE_METADATA_PATH}")
    print(f"metadata_tokens_from_folders: {TOKEN_FOLDER_METADATA_PATH}")


if __name__ == "__main__":
    main()
