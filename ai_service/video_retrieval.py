import re
import shutil
from pathlib import Path


ARABIC_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670]")


def normalize_token(text: str) -> str:
    value = str(text or "").strip().lower()
    value = ARABIC_DIACRITICS.sub("", value)
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
        "ـ": "",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"[^\w\s\u0600-\u06ff]", " ", value)
    return " ".join(value.split())


def _load_clip_index(clips_root: Path) -> dict[str, Path]:
    if not clips_root.exists():
        raise FileNotFoundError(f"Sign retrieval clips folder does not exist: {clips_root}")
    if not clips_root.is_dir():
        raise NotADirectoryError(f"Sign retrieval clips path is not a folder: {clips_root}")

    index = {}
    for clip_path in clips_root.glob("*.mp4"):
        token = normalize_token(clip_path.stem)
        if token:
            index[token] = clip_path
    if not index:
        raise FileNotFoundError(f"No .mp4 sign clips found in: {clips_root}")
    return index


def _match_gloss_units(gloss: str, clip_index: dict[str, Path]) -> tuple[list[dict], list[str]]:
    words = normalize_token(gloss).split()
    max_phrase_len = max((len(token.split()) for token in clip_index), default=1)
    matched = []
    missing = []
    i = 0

    while i < len(words):
        found = None
        for phrase_len in range(min(max_phrase_len, len(words) - i), 0, -1):
            phrase = " ".join(words[i : i + phrase_len])
            clip_path = clip_index.get(phrase)
            if clip_path is not None:
                found = {
                    "phrase": phrase,
                    "token": phrase,
                    "clip_path": str(clip_path),
                    "words_count": phrase_len,
                    "match_type": "filename",
                }
                break

        if found is None:
            missing.append(words[i])
            i += 1
        else:
            matched.append(found)
            i += found["words_count"]

    return matched, missing


def _copy_single_clip(source_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, output_path)


def _concatenate_with_opencv(clip_paths: list[Path], output_path: Path) -> dict:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "opencv-python is required to concatenate sign clips. "
            "Install it with: pip install opencv-python"
        ) from exc

    if not clip_paths:
        raise ValueError("At least one matched sign clip is required.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    first = cv2.VideoCapture(str(clip_paths[0]))
    if not first.isOpened():
        raise RuntimeError(f"Cannot open sign clip: {clip_paths[0]}")

    width = int(first.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    height = int(first.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    fps = first.get(cv2.CAP_PROP_FPS) or 25
    first.release()

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Cannot create output video: {output_path}")

    frames_written = 0
    try:
        for clip_path in clip_paths:
            capture = cv2.VideoCapture(str(clip_path))
            if not capture.isOpened():
                raise RuntimeError(f"Cannot open sign clip: {clip_path}")
            try:
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if frame.shape[1] != width or frame.shape[0] != height:
                        frame = cv2.resize(frame, (width, height))
                    writer.write(frame)
                    frames_written += 1
            finally:
                capture.release()
    finally:
        writer.release()

    if frames_written == 0:
        raise RuntimeError("No frames were written to the generated avatar video.")

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "frames_written": frames_written,
    }


def generate_video_from_gloss(gloss: str, clips_root: str, output_path: str) -> dict:
    """
    Retrieves local sign-language MP4 clips by matching gloss tokens/phrases to
    filenames and concatenates them into one avatar/sign video.
    """
    if not gloss or not str(gloss).strip():
        raise ValueError("Gloss text cannot be empty.")

    clips_root_path = Path(clips_root)
    output_video_path = Path(output_path)
    clip_index = _load_clip_index(clips_root_path)
    matched_units, missing_tokens = _match_gloss_units(gloss, clip_index)

    if not matched_units:
        return {
            "success": False,
            "error": "No matching sign clips were found for the provided gloss.",
            "gloss": gloss,
            "matched_units": [],
            "missing_tokens": missing_tokens,
        }

    clip_paths = [Path(unit["clip_path"]) for unit in matched_units]
    if len(clip_paths) == 1:
        _copy_single_clip(clip_paths[0], output_video_path)
        video_metadata = {"frames_written": None, "copied_single_clip": True}
    else:
        video_metadata = _concatenate_with_opencv(clip_paths, output_video_path)

    return {
        "success": True,
        "gloss": gloss,
        "normalized_gloss": normalize_token(gloss),
        "matched_units": matched_units,
        "missing_tokens": missing_tokens,
        "video_path": str(output_video_path),
        "metadata": {
            "retrieval_type": "local_mp4_video",
            "clips_root": str(clips_root_path),
            "matched_count": len(matched_units),
            **video_metadata,
        },
    }
