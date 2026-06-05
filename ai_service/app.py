import sys
import os
import shutil
import logging
from pathlib import Path
from typing import Optional, List

import numpy as np
import cv2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ------------------------------------------------------------
# 1. LOGGING SETUP
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ai_service")

# ------------------------------------------------------------
# 2. DYNAMIC PATH CONFIGURATION
# ------------------------------------------------------------
PROJECT_ROOT = Path(r"C:\Users\alaan\Desktop\SignData_Prepared\large_sentence_experiment")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
    logger.info(f"Added {PROJECT_ROOT} to sys.path")

try:
    from src.sign_retrieval.generator import SignGenerator
    from src.sign_retrieval import config
except ImportError as e:
    logger.error(f"Failed to import SignGenerator from {PROJECT_ROOT}. Verify the path exists and contains src/sign_retrieval.")
    raise e

# ------------------------------------------------------------
# 3. GLOBAL GENERATOR IMPLEMENTATION WITH CACHED RESOURCES
# ------------------------------------------------------------
class CachedSignGenerator(SignGenerator):
    """
    Subclass of SignGenerator that overrides resource loading 
    to cache files globally on startup instead of reloading on every request.
    """
    def __init__(self):
        super().__init__()
        self._loaded_metadata = {}
        self._index_loaded = False
        self._alias_loaded = False
        self._semantic_loaded = False

    def load_resources(self, pose_format: str = "576"):
        # Load index only once
        if not self._index_loaded:
            try:
                with open(config.TOKEN_INDEX_PATH, "r", encoding="utf-8") as f:
                    self.token_index = json.load(f)
                self._index_loaded = True
                logger.info("Token index successfully loaded and cached.")
            except Exception as e:
                # SignGenerator has json module imported, we handle fallback
                import json
                with open(config.TOKEN_INDEX_PATH, "r", encoding="utf-8") as f:
                    self.token_index = json.load(f)
                self._index_loaded = True
                logger.info("Token index successfully loaded and cached (fallback).")
        
        # Load aliases only once
        if not self._alias_loaded:
            from src.sign_retrieval.text_normalization import load_alias_map
            self.alias_map = load_alias_map()
            self._alias_loaded = True
            logger.info("Alias map successfully loaded and cached.")
            
        # Load semantic embeddings index only once
        if not self._semantic_loaded:
            self.semantic_matcher.load_cached_embeddings()
            self._semantic_loaded = True
            logger.info("Semantic matcher embeddings loaded and cached.")
            
        # Cache pose-format specific metadata to avoid disk-reads on every request
        if pose_format in self._loaded_metadata:
            self.pose_metadata_df = self._loaded_metadata[pose_format]
        else:
            metadata_path = config.TOKEN_POSE_FULL_METADATA_PATH if pose_format == "full" else config.TOKEN_POSE_METADATA_PATH
            if metadata_path.exists():
                import pandas as pd
                try:
                    self.pose_metadata_df = pd.read_csv(metadata_path)
                    self._loaded_metadata[pose_format] = self.pose_metadata_df
                    logger.info(f"Loaded and cached pose metadata for format '{pose_format}'.")
                except Exception as e:
                    logger.warning(f"Could not load pose metadata: {e}")
                    self.pose_metadata_df = None
            else:
                logger.warning(f"Pose metadata path not found: {metadata_path}")
                self.pose_metadata_df = None

# Initialize and pre-load resource caches globally
logger.info("Initializing and pre-loading SignGenerator...")
generator = CachedSignGenerator()
generator.load_resources(pose_format="full")
generator.load_resources(pose_format="576")
logger.info("SignGenerator is fully pre-loaded and ready.")

# ------------------------------------------------------------
# 4. SKELETON VIDEO RENDERING UTILITY
# ------------------------------------------------------------
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),      # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),      # Index
    (5, 9), (9, 10), (10, 11), (11, 12),  # Middle
    (9, 13), (13, 14), (14, 15), (15, 16), # Ring
    (13, 17), (17, 18), (18, 19), (19, 20), # Pinky
    (0, 17)
]

POSE_CONNECTIONS = [
    (11, 12),              # Shoulder to shoulder
    (11, 13), (13, 15),    # Left arm
    (12, 14), (14, 16),    # Right arm
    (11, 23), (12, 24),    # Shoulders to hips
    (23, 24)               # Hip to hip
]

def render_pose_video(input_path: Path, output_path: Path, pose_format: str, width: int = 900, height: int = 900, fps: int = 25):
    """
    Renders 2D skeleton video from a pose NPY file.
    Replicates the drawing logic of scripts/06_render_pose_video.py.
    """
    logger.info(f"Rendering skeleton video from {input_path} to {output_path} (Format: {pose_format})")
    pose = np.load(input_path)
    T, D = pose.shape
    
    if pose_format == "full":
        expected_pose_dim = 1629
        num_landmarks = 543
        num_coords = 3
        POSE_OFFSET = 0
        FACE_OFFSET = 33
        LEFT_HAND_OFFSET = 501
        RIGHT_HAND_OFFSET = 522
    else:
        expected_pose_dim = 576
        num_landmarks = 144
        num_coords = 4
        POSE_OFFSET = 0
        LEFT_HAND_OFFSET = 33
        RIGHT_HAND_OFFSET = 54
        FACE_OFFSET = 75
        
    if D != expected_pose_dim:
        raise ValueError(f"Expected pose dimension {expected_pose_dim} for format '{pose_format}', got {D}.")
        
    landmarks = pose.reshape(T, num_landmarks, num_coords)
    
    # Global normalization for scaling and centering
    all_x = []
    all_y = []
    for t in range(T):
        for lm_idx in range(num_landmarks):
            x = landmarks[t, lm_idx, 0]
            y = landmarks[t, lm_idx, 1]
            if x != 0.0 or y != 0.0:
                all_x.append(x)
                all_y.append(y)
                
    if not all_x or not all_y:
        raise ValueError("Pose file contains only zeros.")
        
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    
    cx_pose = (min_x + max_x) / 2.0
    cy_pose = (min_y + max_y) / 2.0
    
    span_x = max(max_x - min_x, 1e-5)
    span_y = max(max_y - min_y, 1e-5)
    
    target_span_x = width * 0.85
    target_span_y = height * 0.85
    
    scale = min(target_span_x / span_x, target_span_y / span_y)
    cx_screen = width / 2.0
    cy_screen = height / 2.0
    
    def to_screen(x, y):
        screen_x = int(cx_screen + (x - cx_pose) * scale)
        screen_y = int(cy_screen + (y - cy_pose) * scale)
        return screen_x, screen_y

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    
    try:
        for t in range(T):
            frame_img = np.zeros((height, width, 3), dtype=np.uint8)
            points = {}
            for lm_idx in range(num_landmarks):
                x = landmarks[t, lm_idx, 0]
                y = landmarks[t, lm_idx, 1]
                v = 1.0 if num_coords < 4 else landmarks[t, lm_idx, 3]
                
                if x != 0.0 or y != 0.0:
                    px, py = to_screen(x, y)
                    points[lm_idx] = (px, py, v)
            
            # Draw Connections
            for (a, b) in POSE_CONNECTIONS:
                if a in points and b in points:
                    cv2.line(frame_img, points[a][:2], points[b][:2], (100, 255, 100), 2)
                    
            for (a, b) in HAND_CONNECTIONS:
                la = LEFT_HAND_OFFSET + a
                lb = LEFT_HAND_OFFSET + b
                if la in points and lb in points:
                    cv2.line(frame_img, points[la][:2], points[lb][:2], (255, 0, 180), 2)
                    
            for (a, b) in HAND_CONNECTIONS:
                ra = RIGHT_HAND_OFFSET + a
                rb = RIGHT_HAND_OFFSET + b
                if ra in points and rb in points:
                    cv2.line(frame_img, points[ra][:2], points[rb][:2], (0, 255, 255), 2)
                    
            # Draw joints / circles
            face_end = FACE_OFFSET + 468 if pose_format == "full" else 144
            for lm_idx in range(FACE_OFFSET, face_end):
                if lm_idx in points:
                    cv2.circle(frame_img, points[lm_idx][:2], 1, (200, 200, 200), -1)
                    
            for lm_idx in range(POSE_OFFSET, POSE_OFFSET + 33):
                if lm_idx in points:
                    cv2.circle(frame_img, points[lm_idx][:2], 4, (255, 150, 0), -1)
                    
            hand_end = RIGHT_HAND_OFFSET + 21 if pose_format == "full" else FACE_OFFSET
            for lm_idx in range(LEFT_HAND_OFFSET, hand_end):
                if lm_idx in points:
                    cv2.circle(frame_img, points[lm_idx][:2], 3, (0, 100, 255), -1)
                    
            writer.write(frame_img)
    finally:
        writer.release()
    logger.info(f"Skeleton video rendering finished successfully: {output_path}")

# ------------------------------------------------------------
# 5. FASTAPI APP SETUP
# ------------------------------------------------------------
app = FastAPI(title="PharmaSign AI Retrieval Pose Service", version="1.0.0")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory configurations
OUTPUT_DIR = Path("outputs/generated")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GENERATED_OUTPUTS_DIR = Path("generated_outputs")
GENERATED_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Mount Static Files to serve generated output media
app.mount("/media/generated", StaticFiles(directory=str(OUTPUT_DIR)), name="generated")

# ------------------------------------------------------------
# 6. PYDANTIC REQUEST SCHEMAS
# ------------------------------------------------------------
class GenerateRequest(BaseModel):
    text: Optional[str] = None
    gloss: Optional[str] = None
    pose_format: Optional[str] = None
    return_format: Optional[str] = None
    return_video: Optional[bool] = True

# ------------------------------------------------------------
# 7. ENDPOINTS
# ------------------------------------------------------------
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "PharmaSign AI Retrieval Pose Service",
        "generator_loaded": True
    }

@app.post("/generate-pose")
@app.post("/generate-sign")
def generate_pose_endpoint(request: GenerateRequest):
    input_text = request.text or request.gloss
    if not input_text or not input_text.strip():
        logger.error("Request failed: text or gloss field is missing or empty.")
        raise HTTPException(status_code=400, detail="Missing parameter: 'text' or 'gloss' must be provided.")
        
    p_format = request.pose_format or request.return_format or "full"
    if p_format not in ["576", "full"]:
        logger.error(f"Request failed: invalid pose_format '{p_format}'.")
        raise HTTPException(status_code=400, detail=f"Invalid pose_format '{p_format}'. Must be '576' or 'full'.")
        
    input_text = input_text.strip()
    logger.info(f"Processing request: text='{input_text}', format='{p_format}', return_video={request.return_video}")
    
    try:
        # Run the retrieval generator (generating only the pose-only NPY file)
        report = generator.generate(
            text=input_text,
            selection_mode="best",
            out_dir=OUTPUT_DIR,
            pose_only=True,
            skip_video=True,
            blend_frames=8,
            smoothing_window=5,
            pose_format=p_format
        )
        
        # Verify if generator succeeded in creating pose file
        npy_filename = "generated_sentence.npy"
        local_npy_path = OUTPUT_DIR / npy_filename
        
        if not local_npy_path.exists():
            logger.error("Generator completed but NPY output file was not found.")
            return {
                "success": False,
                "error": "Generator failed to write the pose output file.",
                "text": input_text,
                "gloss": input_text,
                "missing_tokens": report.get("missing_tokens", [])
            }
            
        # Copy generated NPY to alternate 'generated_outputs' folder
        shutil.copy(local_npy_path, GENERATED_OUTPUTS_DIR / npy_filename)
        logger.info(f"Saved generated pose to {local_npy_path} and {GENERATED_OUTPUTS_DIR / npy_filename}")
        
        pose_shape = report.get("final_npy_shape")
        missing_tokens = report.get("missing_tokens", [])
        
        # Video rendering stage
        video_url = None
        local_video_path = None
        video_filename = f"generated_sentence_skeleton_{p_format}.mp4"
        
        if request.return_video:
            local_video_path = OUTPUT_DIR / video_filename
            try:
                render_pose_video(
                    input_path=local_npy_path,
                    output_path=local_video_path,
                    pose_format=p_format
                )
                
                # Copy to generated_outputs
                shutil.copy(local_video_path, GENERATED_OUTPUTS_DIR / video_filename)
                
                video_url = f"/media/generated/{video_filename}"
            except Exception as render_err:
                logger.error(f"Error rendering skeleton video: {render_err}", exc_info=True)
                # We still return the NPY since it was generated successfully
                
        return {
            "success": True,
            "text": input_text,
            "gloss": input_text,
            "pose_shape": pose_shape,
            "pose_file": f"/media/generated/{npy_filename}",
            "npy_path": f"/media/generated/{npy_filename}",
            "video_file": video_url,
            "video_path": video_url,
            "missing_tokens": missing_tokens
        }
        
    except Exception as e:
        logger.error(f"Unhandled exception during request processing: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "text": input_text,
            "gloss": input_text,
            "missing_tokens": []
        }

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
