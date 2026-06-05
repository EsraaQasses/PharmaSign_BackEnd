import os
from pathlib import Path

# ============================================================
# PATHS AND DIRECTORIES
# ============================================================
PROJECT_ROOT = Path(
    os.getenv(
        "SIGN_RETRIEVAL_PROJECT_ROOT",
        str(Path(__file__).resolve().parents[2]),
    )
).resolve()
METADATA_CSV = Path(
    os.getenv(
        "SIGN_RETRIEVAL_METADATA_CSV",
        str(PROJECT_ROOT / "metadata" / "metadata_tokens_from_folders.csv"),
    )
).resolve()

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
ASSETS_DIR = PROJECT_ROOT / "assets"

CLEANED_TOKENS_DIR = ASSETS_DIR / "cleaned_tokens"
CLEANED_POSE_DIR = ASSETS_DIR / "cleaned_pose"
CLEANED_POSE_FULL_DIR = ASSETS_DIR / "cleaned_pose_full"
GENERATED_DIR = OUTPUTS_DIR / "generated"

# Ensure directories exist
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_POSE_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_POSE_FULL_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# Specific Files
TOKEN_INDEX_PATH = OUTPUTS_DIR / "token_index.json"
TOKEN_VOCAB_PATH = OUTPUTS_DIR / "token_vocabulary.txt"
TOKEN_ALIAS_MAP_PATH = OUTPUTS_DIR / "token_alias_map.json"
TOKEN_EMBEDDINGS_PATH = OUTPUTS_DIR / "token_embeddings.npy"
TOKEN_EMBEDDINGS_VOCAB_PATH = OUTPUTS_DIR / "token_embeddings_vocab.json"
TOKEN_POSE_METADATA_PATH = OUTPUTS_DIR / "token_pose_metadata.csv"
TOKEN_POSE_FULL_METADATA_PATH = OUTPUTS_DIR / "token_pose_full_metadata.csv"
EVALUATION_REPORT_PATH = OUTPUTS_DIR / "evaluation_report.csv"

# ============================================================
# VIDEO TRIMMING CONSTANTS
# ============================================================
MIN_KEEP_FRAMES = 12
PAD_FRAMES = 3
MIN_MOTION_FRAMES = 3
THRESH_STD_FACTOR = 0.35
MIN_THRESHOLD = 0.001

# ============================================================
# POSE EXTRACTION PARAMETERS (576 dimension Holistic pose)
# ============================================================
POSE_DIM = 576
POSE_DIM_FULL = 1629
MODEL_COMPLEXITY = 1
MIN_DETECTION_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5

# ============================================================
# SEMANTIC TRANSFORMER MATCHING
# ============================================================
TRANSFORMER_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SEMANTIC_THRESHOLD = 0.65  # Enforced confidence threshold for semantic match fallback
