import json
import random
import cv2
import numpy as np
import pandas as pd
from pathlib import Path
from src.sign_retrieval.text_normalization import normalize_arabic_text, load_alias_map, resolve_aliases
from src.sign_retrieval.semantic_matcher import SemanticMatcher
from src.sign_retrieval.utils import get_logger, clean_windows_path
from src.sign_retrieval import config

logger = get_logger("generator")

def longest_match_first_tokenize(text: str, 
                                 token_index: dict, 
                                 alias_map: dict, 
                                 semantic_matcher: SemanticMatcher = None,
                                 max_phrase_len: int = 4) -> list[dict]:
    """
    Tokenizes input sentence using longest-match-first greedy matching.
    Matches against exact vocabulary, alias mapping, or semantic embeddings.
    """
    normalized_text = normalize_arabic_text(text)
    words = normalized_text.split()
    
    matched_units = []
    i = 0
    N = len(words)
    
    while i < N:
        matched = False
        # Try phrases of lengths from max_phrase_len down to 1
        for length in range(min(max_phrase_len, N - i), 0, -1):
            phrase_words = words[i:i+length]
            phrase = " ".join(phrase_words)
            norm_phrase = normalize_arabic_text(phrase)
            
            # 1. Try Exact match
            if norm_phrase in token_index:
                matched_units.append({
                    "phrase": phrase,
                    "token": norm_phrase,
                    "match_type": "exact",
                    "score": 1.0,
                    "words_count": length
                })
                i += length
                matched = True
                break
                
            # 2. Try Alias match
            resolved_alias = resolve_aliases(norm_phrase, alias_map)
            if resolved_alias != norm_phrase and resolved_alias in token_index:
                matched_units.append({
                    "phrase": phrase,
                    "token": resolved_alias,
                    "match_type": "alias",
                    "score": 1.0,
                    "words_count": length
                })
                i += length
                matched = True
                break
                
            # 3. Try Semantic match
            if semantic_matcher is not None:
                matched_vocab, score = semantic_matcher.match(norm_phrase)
                if matched_vocab is not None and matched_vocab in token_index:
                    matched_units.append({
                        "phrase": phrase,
                        "token": matched_vocab,
                        "match_type": "semantic",
                        "score": score,
                        "words_count": length
                    })
                    i += length
                    matched = True
                    break
                    
        if not matched:
            # Word at index i is unrecognized/missing
            matched_units.append({
                "phrase": words[i],
                "token": None,
                "match_type": "missing",
                "score": 0.0,
                "words_count": 1
            })
            i += 1
            
    return matched_units

def concatenate_videos(video_paths: list[Path], output_path: Path) -> bool:
    """
    Concatenates multiple video files into one output video using OpenCV.
    Resizes all video frames to match the dimensions of the first video.
    """
    if not video_paths:
        logger.warning("No video paths provided for concatenation.")
        return False
        
    logger.info(f"Concatenating {len(video_paths)} videos using OpenCV to: {output_path}")
    
    # 1. Read first video to establish baseline frame dimensions and FPS
    cap_first = cv2.VideoCapture(str(video_paths[0]))
    if not cap_first.isOpened():
        logger.error(f"Cannot open first video: {video_paths[0]}")
        return False
        
    width = int(cap_first.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap_first.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap_first.get(cv2.CAP_PROP_FPS)
    cap_first.release()
    
    if width <= 0 or height <= 0:
        width, height = 640, 480  # safe default
        fps = 25.0
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    
    frames_written = 0
    
    for v_path in video_paths:
        cap = cv2.VideoCapture(str(v_path))
        if not cap.isOpened():
            logger.warning(f"Skipping unopenable video: {v_path}")
            continue
            
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Resize if dimension mismatch
            f_h, f_w = frame.shape[:2]
            if f_h != height or f_w != width:
                frame = cv2.resize(frame, (width, height))
                
            writer.write(frame)
            frames_written += 1
            
        cap.release()
        
    writer.release()
    logger.info(f"Video concatenation complete. Written {frames_written} frames.")
    return True

POSE_ANCHOR_IDS = [11, 12, 23, 24]
POSE_SCALE_PAIRS = [(11, 12), (23, 24), (11, 23), (12, 24)]
DEFAULT_TRIM_EDGE_FRAMES = 2


def pose_layout(pose_format: str) -> tuple[int, int]:
    if pose_format == "full":
        return 543, 3
    return 144, 4


def valid_landmark_mask(points: np.ndarray) -> np.ndarray:
    return np.isfinite(points).all(axis=1) & (np.abs(points).sum(axis=1) > 1e-8)


def frame_anchor_and_scale(frame: np.ndarray) -> tuple[np.ndarray, float]:
    xyz = frame[:, :3]
    anchor_points = []
    for idx in POSE_ANCHOR_IDS:
        if idx < len(xyz) and valid_landmark_mask(xyz[[idx]])[0]:
            anchor_points.append(xyz[idx])
    if anchor_points:
        anchor = np.mean(anchor_points, axis=0)
    else:
        valid = valid_landmark_mask(xyz)
        anchor = np.mean(xyz[valid], axis=0) if valid.any() else np.zeros(3, dtype=float)

    distances = []
    for a, b in POSE_SCALE_PAIRS:
        if a < len(xyz) and b < len(xyz) and valid_landmark_mask(xyz[[a, b]]).all():
            dist = float(np.linalg.norm(xyz[a, :2] - xyz[b, :2]))
            if np.isfinite(dist) and dist > 1e-6:
                distances.append(dist)
    scale = float(np.median(distances)) if distances else 1.0
    if not np.isfinite(scale) or scale < 1e-6:
        scale = 1.0
    return anchor, scale


def normalize_pose_segment(segment: np.ndarray, pose_format: str) -> np.ndarray:
    num_landmarks, num_coords = pose_layout(pose_format)
    landmarks = segment.reshape(segment.shape[0], num_landmarks, num_coords).astype(np.float32, copy=True)

    frame_scales = []
    for frame_idx in range(len(landmarks)):
        anchor, scale = frame_anchor_and_scale(landmarks[frame_idx])
        valid = valid_landmark_mask(landmarks[frame_idx, :, :3])
        landmarks[frame_idx, valid, :3] = (landmarks[frame_idx, valid, :3] - anchor) / scale
        frame_scales.append(scale)

    return landmarks.reshape(segment.shape)


def trim_pose_segment(segment: np.ndarray, trim_edge_frames: int = DEFAULT_TRIM_EDGE_FRAMES) -> tuple[np.ndarray, dict]:
    original_frames = int(segment.shape[0])
    if trim_edge_frames <= 0 or original_frames <= (trim_edge_frames * 2 + 8):
        return segment, {
            "original_frames": original_frames,
            "trim_start_frames": 0,
            "trim_end_frames": 0,
            "kept_frames": original_frames,
        }

    trimmed = segment[trim_edge_frames:-trim_edge_frames]
    return trimmed, {
        "original_frames": original_frames,
        "trim_start_frames": trim_edge_frames,
        "trim_end_frames": trim_edge_frames,
        "kept_frames": int(trimmed.shape[0]),
    }


def visible_centroid(frame: np.ndarray, pose_format: str) -> np.ndarray:
    num_landmarks, num_coords = pose_layout(pose_format)
    landmarks = frame.reshape(num_landmarks, num_coords)
    xyz = landmarks[:, :3]
    valid = valid_landmark_mask(xyz)
    if not valid.any():
        return np.zeros(3, dtype=np.float32)
    return np.mean(xyz[valid], axis=0)


def shift_segment(segment: np.ndarray, offset: np.ndarray, pose_format: str) -> np.ndarray:
    num_landmarks, num_coords = pose_layout(pose_format)
    landmarks = segment.reshape(segment.shape[0], num_landmarks, num_coords).copy()
    for frame_idx in range(len(landmarks)):
        valid = valid_landmark_mask(landmarks[frame_idx, :, :3])
        landmarks[frame_idx, valid, :3] = landmarks[frame_idx, valid, :3] + offset
    return landmarks.reshape(segment.shape)


def interpolate_frames(a: np.ndarray, b: np.ndarray, count: int) -> np.ndarray:
    if count <= 0:
        return np.empty((0, a.shape[0]), dtype=np.float32)
    frames = []
    for idx in range(1, count + 1):
        t = idx / (count + 1)
        smooth_t = t * t * (3.0 - 2.0 * t)
        frames.append(((1.0 - smooth_t) * a) + (smooth_t * b))
    return np.asarray(frames, dtype=np.float32)


def smooth_pose_sequence(sequence: np.ndarray, smoothing_window: int) -> np.ndarray:
    if smoothing_window <= 1 or len(sequence) < smoothing_window:
        return sequence
    if smoothing_window % 2 == 0:
        smoothing_window += 1
    half_window = smoothing_window // 2
    smoothed = sequence.copy()
    for frame_idx in range(len(sequence)):
        start = max(0, frame_idx - half_window)
        end = min(len(sequence), frame_idx + half_window + 1)
        smoothed[frame_idx] = np.mean(sequence[start:end], axis=0)
    return smoothed


def blend_pose_segments(
    segments: list[np.ndarray],
    blend_frames: int = 8,
    smoothing_window: int = 5,
    pose_format: str = "576",
    debug_segments_dir: Path | None = None,
) -> tuple[np.ndarray, dict]:
    """
    Blends consecutive pose segments by overlapping them and performing linear interpolation.
    Applies moving average temporal smoothing across the entire concatenated sequence.
    """
    if not segments:
        return None, {}

    trim_info = []
    prepared_segments = []
    for idx, segment in enumerate(segments):
        trimmed, info = trim_pose_segment(segment)
        normalized = normalize_pose_segment(trimmed, pose_format)
        info["segment_index"] = idx
        info["normalized"] = True
        trim_info.append(info)
        prepared_segments.append(normalized)
        if debug_segments_dir is not None:
            debug_segments_dir.mkdir(parents=True, exist_ok=True)
            np.save(debug_segments_dir / f"segment_{idx:02d}_stabilized.npy", normalized)

    transition_frames_used = []
    result = prepared_segments[0].copy()

    for idx in range(1, len(prepared_segments)):
        next_seg = prepared_segments[idx].copy()
        transition_count = min(blend_frames, max(0, len(result) // 4), max(0, len(next_seg) // 4))

        offset = visible_centroid(result[-1], pose_format) - visible_centroid(next_seg[0], pose_format)
        next_seg = shift_segment(next_seg, offset, pose_format)
        bridge = interpolate_frames(result[-1], next_seg[0], transition_count)
        result = np.concatenate([result, bridge, next_seg], axis=0)
        transition_frames_used.append(
            {
                "from_segment": idx - 1,
                "to_segment": idx,
                "frames": int(transition_count),
                "translation_offset": [float(x) for x in offset],
            }
        )

    smoothed = smooth_pose_sequence(result, smoothing_window)
    metadata = {
        "trim_info": trim_info,
        "transition_frames_used": transition_frames_used,
        "smoothing_applied": smoothing_window > 1,
        "smoothing_window": smoothing_window,
        "stabilization": {
            "method": "per_frame_torso_anchor_scale_normalization",
            "anchor_landmarks": POSE_ANCHOR_IDS,
            "scale_pairs": POSE_SCALE_PAIRS,
        },
    }
    return smoothed, metadata

def concatenate_poses(
    pose_paths: list[Path],
    output_path: Path,
    blend_frames: int = 8,
    smoothing_window: int = 5,
    pose_format: str = "576",
    debug_segments_dir: Path | None = None,
) -> tuple[np.ndarray | None, list[str], list[int], dict]:
    """
    Loads, blends, and smooths 2D pose arrays along the frame axis (axis 0).
    Checks that each array has shape (T, POSE_DIM) where POSE_DIM is 576 or 1629.
    Returns (blended_array, skipped_pose_files, original_lengths).
    """
    poses = []
    skipped = []
    original_lengths = []
    
    expected_pose_dim = config.POSE_DIM_FULL if pose_format == "full" else config.POSE_DIM
    
    for p_path in pose_paths:
        if not p_path.exists():
            skipped.append(f"{p_path.name} (does not exist)")
            continue
            
        try:
            arr = np.load(p_path)
            if arr.ndim != 2 or arr.shape[1] != expected_pose_dim:
                logger.warning(f"Skipping pose {p_path.name} due to shape mismatch: {arr.shape} != (T, {expected_pose_dim})")
                skipped.append(f"{p_path.name} (shape mismatch: {arr.shape})")
                continue
                
            poses.append(arr)
            original_lengths.append(int(arr.shape[0]))
        except Exception as e:
            logger.error(f"Error loading pose {p_path.name}: {e}")
            skipped.append(f"{p_path.name} (load error)")
            
    if not poses:
        logger.warning("No valid poses to concatenate.")
        return None, skipped, [], {}

    concatenated, merge_metadata = blend_pose_segments(
        poses,
        blend_frames,
        smoothing_window,
        pose_format=pose_format,
        debug_segments_dir=debug_segments_dir,
    )
    
    if concatenated is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, concatenated)
        logger.info(f"Pose blending/concatenation complete. Saved array of shape {concatenated.shape} to {output_path}")
    
    return concatenated, skipped, original_lengths, merge_metadata


class SignGenerator:
    def __init__(self):
        self.token_index = {}
        self.alias_map = {}
        self.semantic_matcher = SemanticMatcher()
        self.pose_metadata_df = None
        
    def load_resources(self, pose_format: str = "576"):
        """Loads index, aliases, embeddings, and preprocessing metadata."""
        # Load token index
        try:
            with open(config.TOKEN_INDEX_PATH, "r", encoding="utf-8") as f:
                self.token_index = json.load(f)
            logger.info("Loaded token index.")
        except Exception as e:
            logger.error(f"Failed to load token index from {config.TOKEN_INDEX_PATH}. Error: {e}")
            
        # Load aliases
        self.alias_map = load_alias_map()
        
        # Load semantic embeddings index
        self.semantic_matcher.load_cached_embeddings()
        
        # Load pose metadata if available
        metadata_path = config.TOKEN_POSE_FULL_METADATA_PATH if pose_format == "full" else config.TOKEN_POSE_METADATA_PATH
        if metadata_path.exists():
            try:
                self.pose_metadata_df = pd.read_csv(metadata_path)
                logger.info(f"Loaded preprocessing pose metadata from {metadata_path.name}.")
            except Exception as e:
                logger.warning(f"Could not load pose metadata: {e}")

    def select_take(self, token: str, selection_mode: str = "best") -> dict:
        """Selects a specific take/record for a token based on selection_mode."""
        takes = self.token_index.get(token, [])
        if not takes:
            raise KeyError(f"No takes found in index for token: {token}")
            
        if len(takes) == 1:
            return takes[0]
            
        if selection_mode == "random":
            return random.choice(takes)
            
        if selection_mode == "best" and self.pose_metadata_df is not None:
            # Filter metadata for these takes
            take_ids = [t["id"] for t in takes]
            # Match metadata rows where id in take_ids and success is True
            sub_df = self.pose_metadata_df[
                (self.pose_metadata_df["id"].isin(take_ids)) &
                (self.pose_metadata_df["success"] == True)
            ]
            
            if not sub_df.empty:
                # Calculate total trim size: trim_start_frames + trim_end_frames
                # Pick the one with the smallest trim noise / most stable active region
                sub_df = sub_df.copy()
                sub_df["trim_noise"] = sub_df["trim_start_frames"] + sub_df["trim_end_frames"]
                sub_df = sub_df.sort_values(by="trim_noise")
                best_id = sub_df.iloc[0]["id"]
                
                # Retrieve the matching take dictionary
                for t in takes:
                    if t["id"] == best_id:
                        return t
                        
        # Default fallback to first take
        return takes[0]

    def generate(self, 
                 text: str, 
                 selection_mode: str = "best", 
                 out_dir: Path = config.GENERATED_DIR,
                 pose_only: bool = False,
                 skip_video: bool = False,
                 blend_frames: int = 8,
                 smoothing_window: int = 5,
                 pose_format: str = "576",
                 debug_segments: bool = False) -> dict:
        """
        Tokenizes the input text, retrieves clean assets, blends poses,
        concatenates them, and saves outputs. Can skip video generation for pose-only skeleton NPY output.
        """
        self.load_resources(pose_format=pose_format)
        
        # Determine whether to generate video
        generate_video = not (pose_only or skip_video)
        
        # 1. Parse sentence into token matching units
        matched_units = longest_match_first_tokenize(
            text, self.token_index, self.alias_map, self.semantic_matcher
        )
        
        matched_tokens = []
        missing_tokens = []
        video_paths_to_concat = []
        pose_paths_to_concat = []
        selected_takes = []
        
        # 2. Retrieve assets for matched units
        for unit in matched_units:
            token = unit["token"]
            phrase = unit["phrase"]
            
            if token is None:
                missing_tokens.append(phrase)
                continue
                
            # Retrieve take
            try:
                take = self.select_take(token, selection_mode)
            except Exception as e:
                logger.error(f"Failed to select take for {token}: {e}")
                missing_tokens.append(phrase)
                continue
                
            # Define cleaned video and pose paths
            video_name = Path(take["absolute_video_path"]).name
            pose_name = f"{take['id']}.npy"
            
            pose_dir = config.CLEANED_POSE_FULL_DIR if pose_format == "full" else config.CLEANED_POSE_DIR
            cleaned_video_path = config.CLEANED_TOKENS_DIR / token / video_name
            cleaned_pose_path = pose_dir / token / pose_name
            
            # Verify they exist (only check video if we plan to generate video)
            if generate_video and not cleaned_video_path.exists():
                logger.warning(f"Cleaned video file not found: {cleaned_video_path}")
                missing_tokens.append(phrase)
                continue
                
            if not cleaned_pose_path.exists():
                logger.warning(f"Cleaned pose file not found: {cleaned_pose_path}")
                missing_tokens.append(phrase)
                continue
                
            matched_tokens.append({
                "phrase": phrase,
                "token": token,
                "match_type": unit["match_type"],
                "score": unit["score"],
                "take_id": take["id"],
                "video_path": clean_windows_path(cleaned_video_path) if cleaned_video_path.exists() else "",
                "pose_path": clean_windows_path(cleaned_pose_path)
            })
            
            if generate_video:
                video_paths_to_concat.append(cleaned_video_path)
            pose_paths_to_concat.append(cleaned_pose_path)
            selected_takes.append(take)
            
        # 3. Concatenate and blend assets
        out_dir.mkdir(parents=True, exist_ok=True)
        final_video_path = out_dir / "generated_sentence.mp4"
        final_pose_path = out_dir / "generated_sentence.npy"
        debug_segments_dir = out_dir / "debug_segments" if debug_segments else None
        
        video_success = False
        pose_success = False
        skipped_poses = []
        original_lengths = []
        final_pose = None
        merge_metadata = {}
        
        # Concat video if requested
        if generate_video and video_paths_to_concat:
            video_success = concatenate_videos(video_paths_to_concat, final_video_path)
            
        # Concat and blend poses
        if pose_paths_to_concat:
            final_pose, skipped_poses, original_lengths, merge_metadata = concatenate_poses(
                pose_paths_to_concat,
                final_pose_path,
                blend_frames,
                smoothing_window,
                pose_format=pose_format,
                debug_segments_dir=debug_segments_dir,
            )
            pose_success = final_pose is not None
            
        # 4. Generate JSON Report
        report = {
            "original_text": text,
            "normalized_text": normalize_arabic_text(text),
            "matched_units": matched_units,
            "retrieved_tokens": matched_tokens,
            "missing_units": missing_tokens,
            "missing_tokens": missing_tokens,
            "selection_mode": selection_mode,
            "blend_frames": blend_frames,
            "smoothing_window": smoothing_window,
            "selected_pose_paths": [clean_windows_path(p) for p in pose_paths_to_concat],
            "original_segment_lengths": original_lengths,
            "transition_frames_used": merge_metadata.get("transition_frames_used", []),
            "trim_info": merge_metadata.get("trim_info", []),
            "smoothing_applied": merge_metadata.get("smoothing_applied", False),
            "smoothing_window": merge_metadata.get("smoothing_window", smoothing_window),
            "stabilization": merge_metadata.get("stabilization", {}),
            "debug_segments_dir": clean_windows_path(debug_segments_dir) if debug_segments_dir else None,
            "final_npy_shape": list(final_pose.shape) if final_pose is not None else None,
            "generated_assets": {
                "video": clean_windows_path(final_video_path) if video_success else None,
                "pose": clean_windows_path(final_pose_path) if pose_success else None,
            },
            "warnings": []
        }
        
        if missing_tokens:
            report["warnings"].append(f"Missing tokens: {missing_tokens}")
        if skipped_poses:
            report["warnings"].append(f"Skipped pose files due to errors: {skipped_poses}")
            
        report_path = out_dir / "generated_sentence_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Saved detailed generation report to: {report_path}")
        
        # Log summary prints as requested
        print("\n" + "=" * 80)
        print("SIGN GENERATION SUMMARY (SKELETON POSE MODIFIED)")
        print("=" * 80)
        print(f"Input text       : {text}")
        print(f"Matched tokens   : {', '.join([m['token'] for m in matched_tokens])}")
        print(f"Match sources    : {', '.join([m['match_type'] for m in matched_tokens])}")
        print(f"Missing tokens   : {', '.join(missing_tokens) if missing_tokens else 'None'}")
        if generate_video:
            print(f"Generated video  : {final_video_path if video_success else 'FAILED'}")
        else:
            print("Generated video  : SKIPPED (Pose-only / skip-video mode)")
        print(f"Generated pose   : {final_pose_path if pose_success else 'FAILED'}")
        if pose_success:
            print(f"  Pose shape     : {list(final_pose.shape)}")
            print(f"  Blend frames   : {blend_frames}")
            print(f"  Smooth window  : {smoothing_window}")
        print("=" * 80 + "\n")
        
        return report
