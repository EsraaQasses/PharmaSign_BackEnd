import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT.parents[2]
TOKEN_INDEX_PATH = PROJECT_ROOT / "outputs" / "token_index.json"
CLEANED_POSE_FULL_DIR = PROJECT_ROOT / "assets" / "cleaned_pose_full"


def ensure_import_paths():
    for path in (PROJECT_ROOT, BACKEND_ROOT):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


ensure_import_paths()
from src.sign_retrieval.generator import SignGenerator  # noqa: E402
from src.sign_retrieval.text_normalization import normalize_arabic_text  # noqa: E402


def pick_token(token_index: dict, requested_token: str | None) -> str:
    if requested_token:
        normalized = normalize_arabic_text(requested_token)
        if normalized in token_index:
            return normalized
        print(f"Requested token not found after normalization: {requested_token} -> {normalized}")

    preferred = normalize_arabic_text("الجلد")
    if preferred in token_index:
        return preferred

    if not token_index:
        raise RuntimeError("token_index.json is empty.")
    return sorted(token_index.keys())[0]


def main():
    parser = argparse.ArgumentParser(description="Test rebuilt PharmaSign token extraction outputs.")
    parser.add_argument("--token", default=None)
    parser.add_argument("--skip-generator", action="store_true")
    parser.add_argument("--try-avatar", action="store_true")
    args = parser.parse_args()

    if not TOKEN_INDEX_PATH.exists():
        raise FileNotFoundError(f"Missing token index: {TOKEN_INDEX_PATH}")

    with open(TOKEN_INDEX_PATH, "r", encoding="utf-8") as f:
        token_index = json.load(f)

    token = pick_token(token_index, args.token)
    take = token_index[token][0]
    pose_path = Path(take.get("full_pose_path") or CLEANED_POSE_FULL_DIR / token / f"{take['id']}.npy")

    print(f"Selected token: {token}")
    print(f"Selected take id: {take['id']}")
    print(f"Full pose path: {pose_path}")

    if not pose_path.exists():
        raise FileNotFoundError(f"Pose file not found: {pose_path}")

    arr = np.load(pose_path)
    print(f"Loaded shape: {arr.shape}")
    if arr.ndim != 2 or arr.shape[1] != 1629:
        raise AssertionError(f"Expected full pose shape (frames, 1629), got {arr.shape}")

    if not args.skip_generator:
        generator = SignGenerator()
        with tempfile.TemporaryDirectory(prefix="pharmasign_generator_test_") as tmp_dir:
            report = generator.generate(
                text=token,
                selection_mode="best",
                out_dir=Path(tmp_dir),
                pose_only=True,
                skip_video=True,
                blend_frames=8,
                smoothing_window=5,
                pose_format="full",
            )
            print(f"SignGenerator success: {bool(report.get('generated_assets', {}).get('pose'))}")
            print(f"Generated shape: {report.get('final_npy_shape')}")
            print(f"Missing tokens: {report.get('missing_tokens')}")
            if report.get("final_npy_shape", [None, None])[1] != 1629:
                raise AssertionError(f"SignGenerator did not produce full 1629 pose: {report.get('final_npy_shape')}")

    if args.try_avatar:
        try:
            from ai_service import avatar_renderer
            render_fn = getattr(avatar_renderer, "render_avatar_from_npy", None)
            if render_fn is None:
                print("Avatar renderer does not expose render_avatar_from_npy().")
            else:
                print("Avatar renderer is available; call it with this pose path if needed.")
        except Exception as exc:
            print(f"Avatar renderer import failed: {exc}")

    print("Rebuilt token dataset test passed.")


if __name__ == "__main__":
    main()
