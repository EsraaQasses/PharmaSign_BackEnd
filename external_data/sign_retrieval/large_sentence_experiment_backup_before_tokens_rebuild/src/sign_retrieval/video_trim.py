import cv2
import numpy as np
import shutil
from pathlib import Path
from src.sign_retrieval.utils import get_logger
from src.sign_retrieval import config

logger = get_logger("video_trim")

def detect_motion_boundaries(video_path: Path, 
                             min_keep_frames: int = config.MIN_KEEP_FRAMES, 
                             pad_frames: int = config.PAD_FRAMES, 
                             min_motion_frames: int = config.MIN_MOTION_FRAMES, 
                             thresh_std_factor: float = config.THRESH_STD_FACTOR, 
                             min_threshold: float = config.MIN_THRESHOLD) -> tuple[int, int, str, dict]:
    """
    Analyzes pixel-level motion in a video to find start and end indices of active signing.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
        
    frames_gray = []
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (15, 15), 0)
        frames_gray.append(gray)
        
    cap.release()
    
    T = len(frames_gray)
    if T == 0:
        raise RuntimeError(f"Video file has zero readable frames: {video_path}")
        
    if T <= min_keep_frames:
        return 0, T - 1, "too_short_keep_original", {"original_frames": T, "trimmed_frames": T}
        
    # Calculate motion between consecutive frames
    motion = []
    for i in range(1, T):
        diff = cv2.absdiff(frames_gray[i], frames_gray[i-1])
        motion.append(np.mean(diff))
    motion = np.array(motion, dtype=np.float32)
    
    if len(motion) == 0:
        return 0, T - 1, "no_motion_array_keep_original", {"original_frames": T, "trimmed_frames": T}
        
    mean_m = float(motion.mean())
    std_m = float(motion.std())
    max_m = float(motion.max())
    
    # Define dynamic threshold
    threshold = max(min_threshold, mean_m + thresh_std_factor * std_m)
    
    active = motion > threshold
    active_indices = np.where(active)[0]
    
    stats = {
        "motion_mean": mean_m,
        "motion_std": std_m,
        "motion_max": max_m,
        "threshold": threshold,
        "active_motion_count": int(active.sum()),
        "original_frames": T
    }
    
    if len(active_indices) < min_motion_frames:
        stats["trimmed_frames"] = T
        return 0, T - 1, "low_motion_keep_original", stats
        
    # active_indices[i] represents motion between frame i and i+1
    start = int(active_indices[0])
    end = int(active_indices[-1] + 1)
    
    # Add safety padding
    start = max(0, start - pad_frames)
    end = min(T - 1, end + pad_frames)
    
    # Enforce minimum keep length
    keep_len = end - start + 1
    if keep_len < min_keep_frames:
        center = (start + end) // 2
        half = min_keep_frames // 2
        start = max(0, center - half)
        end = min(T - 1, start + min_keep_frames - 1)
        start = max(0, end - min_keep_frames + 1)
        
    final_len = end - start + 1
    stats["trimmed_frames"] = final_len
    
    status = "trimmed" if final_len < T - 2 else "almost_no_trim"
    return start, end, status, stats

def trim_and_save_video(video_path: Path, 
                        out_path: Path, 
                        min_keep_frames: int = config.MIN_KEEP_FRAMES, 
                        pad_frames: int = config.PAD_FRAMES, 
                        min_motion_frames: int = config.MIN_MOTION_FRAMES, 
                        thresh_std_factor: float = config.THRESH_STD_FACTOR, 
                        min_threshold: float = config.MIN_THRESHOLD) -> tuple[int, int, str, dict]:
    """
    Runs motion detection, trims the video based on boundaries, and saves the cleaned video.
    Returns (start_idx, end_idx, status, stats).
    """
    video_path = Path(video_path)
    out_path = Path(out_path)
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video file to trim does not exist: {video_path}")
        
    start_idx, end_idx, status, stats = detect_motion_boundaries(
        video_path, min_keep_frames, pad_frames, min_motion_frames, thresh_std_factor, min_threshold
    )
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # If no trimming was performed or video is too short, copy original file directly
    if status in ["too_short_keep_original", "low_motion_keep_original", "almost_no_trim"]:
        shutil.copy(video_path, out_path)
        logger.info(f"Copying original video (no trim) to: {out_path.name}")
        return start_idx, end_idx, status, stats
        
    # Read original and write trimmed
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
    
    frame_idx = 0
    saved_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if start_idx <= frame_idx <= end_idx:
            writer.write(frame)
            saved_count += 1
        frame_idx += 1
        
    cap.release()
    writer.release()
    
    logger.info(f"Saved trimmed video ({saved_count} frames, range {start_idx}-{end_idx}) to: {out_path.name}")
    return start_idx, end_idx, status, stats
