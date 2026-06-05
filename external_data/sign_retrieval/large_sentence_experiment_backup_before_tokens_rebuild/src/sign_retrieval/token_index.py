import json
import pandas as pd
from pathlib import Path
from src.sign_retrieval.text_normalization import normalize_arabic_text
from src.sign_retrieval.utils import get_logger, clean_windows_path
from src.sign_retrieval.config import TOKEN_INDEX_PATH, TOKEN_VOCAB_PATH, METADATA_CSV

logger = get_logger("token_index")

def build_index(metadata_path: Path = METADATA_CSV) -> tuple[dict, list[str], dict]:
    """
    Reads the metadata, filters valid token rows, normalizes Arabic glosses,
    and constructs the token index mapping normalized tokens to their takes.
    """
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found at: {metadata_path}")
        
    df = pd.read_csv(metadata_path, encoding="utf-8-sig")
    
    total_rows = len(df)
    logger.info(f"Loaded {total_rows} rows from metadata.")
    
    # Filter where category == 'token' and video_exists is True
    # Handle video_exists as boolean or string
    if "video_exists" in df.columns:
        df["video_exists_bool"] = df["video_exists"].apply(
            lambda x: str(x).strip().lower() in ["true", "1", "yes"] if not isinstance(x, bool) else x
        )
    else:
        df["video_exists_bool"] = True
        logger.warning("video_exists column not found in metadata. Assuming all videos exist.")
        
    df_tokens = df[
        (df["category"].str.strip().str.lower() == "token") & 
        (df["video_exists_bool"] == True)
    ].copy()
    
    valid_token_rows = len(df_tokens)
    missing_video_rows = len(df[df["category"].str.strip().str.lower() == "token"]) - valid_token_rows
    logger.info(f"Filtered {valid_token_rows} token rows with existing videos. (Skipped {missing_video_rows} missing videos)")
    
    token_index = {}
    
    for _, row in df_tokens.iterrows():
        sample_id = str(row["id"]).strip()
        gloss_clean = str(row.get("gloss_clean", "")).strip()
        
        # Normalize the gloss clean
        normalized = normalize_arabic_text(gloss_clean)
        if not normalized:
            continue
            
        video_path = clean_windows_path(row["video_path"])
        abs_video_path = clean_windows_path(row["absolute_video_path"])
        
        take_info = {
            "id": sample_id,
            "video_path": video_path,
            "absolute_video_path": abs_video_path,
            "signer_id": str(row.get("signer_id", "unknown")).strip(),
            "take_id": str(row.get("take_id", "unknown")).strip(),
            "source_text": gloss_clean
        }
        
        if normalized not in token_index:
            token_index[normalized] = []
        token_index[normalized].append(take_info)
        
    vocabulary = sorted(list(token_index.keys()))
    
    stats = {
        "total_rows": total_rows,
        "valid_token_rows": valid_token_rows,
        "missing_video_rows": missing_video_rows,
        "unique_normalized_tokens": len(vocabulary)
    }
    
    return token_index, vocabulary, stats

def build_and_save_index(metadata_path: Path = METADATA_CSV, 
                         index_path: Path = TOKEN_INDEX_PATH, 
                         vocab_path: Path = TOKEN_VOCAB_PATH) -> dict:
    """Builds the token index and saves index JSON and vocab text file to disk."""
    token_index, vocabulary, stats = build_index(metadata_path)
    
    # Save index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(token_index, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved token index to: {index_path}")
    
    # Save vocabulary
    vocab_path.parent.mkdir(parents=True, exist_ok=True)
    with open(vocab_path, "w", encoding="utf-8") as f:
        for term in vocabulary:
            f.write(term + "\n")
    logger.info(f"Saved vocabulary ({len(vocabulary)} tokens) to: {vocab_path}")
    
    return stats

def load_token_index(index_path: Path = TOKEN_INDEX_PATH) -> dict:
    """Loads the token index from JSON."""
    if not index_path.exists():
        raise FileNotFoundError(f"Token index JSON not found. Build it first. Path: {index_path}")
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)
