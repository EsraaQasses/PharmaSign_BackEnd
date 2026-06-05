import cv2
import numpy as np
from pathlib import Path
from src.sign_retrieval.utils import get_logger
from src.sign_retrieval import config

logger = get_logger("pose_extraction")

try:
    import mediapipe as mp
except ImportError:
    logger.error("mediapipe is not installed in the current environment.")
    raise ImportError("mediapipe is required for pose extraction. Install it with: pip install mediapipe")

# ============================================================
# LANDMARK CONFIG (Consistent with scripts/03_extract_pose_large_selected.py)
# ============================================================
SELECTED_FACE_IDXS = sorted(set([
    # face oval / contour - 25
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323,
    361, 288, 397, 365, 379, 378, 400, 377, 152,
    148, 176, 149, 150, 136, 172,

    # eyebrows - 10
    70, 63, 105, 66, 107,
    336, 296, 334, 293, 300,

    # eyes - 16
    33, 133, 159, 145, 153, 154, 155, 246,
    362, 263, 386, 374, 380, 381, 382, 466,

    # nose - 5
    1, 2, 98, 327, 168,

    # mouth - 13
    61, 291, 13, 14, 17, 0, 37, 267,
    78, 308, 82, 312, 87
]))

POSE_COUNT = 33
HAND_COUNT = 21
FACE_COUNT = 69
POSE_DIM = 576  # (33 + 21 + 21 + 69) * 4

def landmark_to_xyzw(lm) -> list[float]:
    """Helper to convert landmark attributes to a list [x, y, z, visibility]."""
    x = float(getattr(lm, "x", 0.0))
    y = float(getattr(lm, "y", 0.0))
    z = float(getattr(lm, "z", 0.0))
    v = float(getattr(lm, "visibility", 1.0))
    return [x, y, z, v]

def landmark_to_xyz(lm) -> list[float]:
    """Helper to convert landmark attributes to a list [x, y, z] for full holistic mode."""
    x = float(getattr(lm, "x", 0.0))
    y = float(getattr(lm, "y", 0.0))
    z = float(getattr(lm, "z", 0.0))
    return [x, y, z]

def extract_frame_features(results, full_holistic: bool = False) -> np.ndarray:
    """
    Combines landmarks into a 1D feature array.
    If full_holistic is True, returns (33 pose + 468 face + 21 left hand + 21 right hand) * 3 = 1629 features.
    Otherwise, returns the standard 576 features.
    """
    features = []

    if full_holistic:
        # 1. Pose landmarks (33 x 3)
        if results.pose_landmarks is not None:
            pose_lms = results.pose_landmarks.landmark
            for i in range(POSE_COUNT):
                features.extend(landmark_to_xyz(pose_lms[i]))
        else:
            features.extend([0.0] * POSE_COUNT * 3)

        # 2. Face landmarks (468 x 3)
        if results.face_landmarks is not None:
            face_lms = results.face_landmarks.landmark
            for i in range(468):
                features.extend(landmark_to_xyz(face_lms[i]))
        else:
            features.extend([0.0] * 468 * 3)

        # 3. Left hand landmarks (21 x 3)
        if results.left_hand_landmarks is not None:
            hand_lms = results.left_hand_landmarks.landmark
            for i in range(HAND_COUNT):
                features.extend(landmark_to_xyz(hand_lms[i]))
        else:
            features.extend([0.0] * HAND_COUNT * 3)

        # 4. Right hand landmarks (21 x 3)
        if results.right_hand_landmarks is not None:
            hand_lms = results.right_hand_landmarks.landmark
            for i in range(HAND_COUNT):
                features.extend(landmark_to_xyz(hand_lms[i]))
        else:
            features.extend([0.0] * HAND_COUNT * 3)

        expected_dim = 1629
    else:
        # 1. Pose landmarks (33 x 4)
        if results.pose_landmarks is not None:
            pose_lms = results.pose_landmarks.landmark
            for i in range(POSE_COUNT):
                features.extend(landmark_to_xyzw(pose_lms[i]))
        else:
            features.extend([0.0] * POSE_COUNT * 4)

        # 2. Left hand landmarks (21 x 4)
        if results.left_hand_landmarks is not None:
            hand_lms = results.left_hand_landmarks.landmark
            for i in range(HAND_COUNT):
                features.extend(landmark_to_xyzw(hand_lms[i]))
        else:
            features.extend([0.0] * HAND_COUNT * 4)

        # 3. Right hand landmarks (21 x 4)
        if results.right_hand_landmarks is not None:
            hand_lms = results.right_hand_landmarks.landmark
            for i in range(HAND_COUNT):
                features.extend(landmark_to_xyzw(hand_lms[i]))
        else:
            features.extend([0.0] * HAND_COUNT * 4)

        # 4. Face landmarks (69 x 4)
        if results.face_landmarks is not None:
            face_lms = results.face_landmarks.landmark
            for idx in SELECTED_FACE_IDXS:
                features.extend(landmark_to_xyzw(face_lms[idx]))
        else:
            features.extend([0.0] * FACE_COUNT * 4)

        expected_dim = POSE_DIM

    arr = np.asarray(features, dtype=np.float32)
    if arr.shape[0] != expected_dim:
        raise RuntimeError(f"Feature dim mismatch: {arr.shape[0]} != {expected_dim}")
        
    return arr

def extract_pose_from_video(video_path: Path, full_holistic: bool = False) -> np.ndarray:
    """
    Initializes MediaPipe Holistic, processes the video frame-by-frame,
    and returns a 2D numpy array of shape [num_frames, 576] or [num_frames, 1629].
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
        
    mp_holistic = mp.solutions.holistic
    frames = []
    
    with mp_holistic.Holistic(
        static_image_mode=False,
        model_complexity=config.MODEL_COMPLEXITY,
        smooth_landmarks=True,
        enable_segmentation=False,
        refine_face_landmarks=True,
        min_detection_confidence=config.MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence=config.MIN_TRACKING_CONFIDENCE
    ) as holistic:
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = holistic.process(rgb)
            
            feat = extract_frame_features(results, full_holistic=full_holistic)
            frames.append(feat)
            
    cap.release()
    
    if not frames:
        raise RuntimeError(f"No frames could be extracted from video: {video_path}")
        
    pose = np.stack(frames, axis=0).astype(np.float32)
    
    # Check NaN and Inf
    if np.isnan(pose).any() or np.isinf(pose).any():
        logger.warning(f"Extracted pose for {video_path.name} contains NaN or Inf. Interpolating zeros.")
        pose = np.nan_to_num(pose)
        
    return pose
