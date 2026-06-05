import pandas as pd
import json
from pathlib import Path
from src.sign_retrieval.text_normalization import normalize_arabic_text, load_alias_map
from src.sign_retrieval.generator import longest_match_first_tokenize
from src.sign_retrieval.semantic_matcher import SemanticMatcher
from src.sign_retrieval.token_index import load_token_index
from src.sign_retrieval.utils import get_logger
from src.sign_retrieval import config

logger = get_logger("evaluation")

TEST_SENTENCES = [
    "دواء حبة الصبح قبل الاكل",
    "علاج حبة صباحا قبل الفطور",
    "اشرب الدواء بعد الاكل",
    "استخدم العلاج اسبوع",
    "حبة كل يوم المسا"
]

def run_pipeline_evaluation() -> pd.DataFrame:
    """
    Evaluates vocabulary metrics, preprocessing statistics, and token/word coverage
    on a standard set of test sentences. Exports a detailed CSV report.
    """
    logger.info("Starting pipeline evaluation...")
    
    # 1. Load resources
    try:
        token_index = load_token_index()
    except Exception as e:
        logger.error(f"Cannot load token index: {e}")
        return pd.DataFrame()
        
    alias_map = load_alias_map()
    
    semantic_matcher = SemanticMatcher()
    semantic_matcher.load_cached_embeddings()
    
    pose_metadata = None
    if config.TOKEN_POSE_METADATA_PATH.exists():
        try:
            pose_metadata = pd.read_csv(config.TOKEN_POSE_METADATA_PATH)
        except Exception as e:
            logger.warning(f"Could not load pose metadata: {e}")
            
    # 2. General Dataset Stats
    vocab_size = len(token_index)
    
    takes_per_token = [len(takes) for takes in token_index.values()]
    avg_takes = sum(takes_per_token) / len(takes_per_token) if takes_per_token else 0
    max_takes = max(takes_per_token) if takes_per_token else 0
    min_takes = min(takes_per_token) if takes_per_token else 0
    
    trim_success_rate = 0.0
    pose_success_rate = 0.0
    total_preprocessed = 0
    
    if pose_metadata is not None:
        total_preprocessed = len(pose_metadata)
        if total_preprocessed > 0:
            trim_success_rate = (pose_metadata["success"] == True).mean() * 100
            # Since pose extraction is run on trimmed videos, success indicates both trimming and pose succeeded
            pose_success_rate = (pose_metadata["success"] == True).mean() * 100
            
    print("\n" + "=" * 80)
    print("DATASET & PREPROCESSING STATISTICS")
    print("=" * 80)
    print(f"Total Vocabulary Size (Unique tokens)   : {vocab_size}")
    print(f"Average Takes per Token                 : {avg_takes:.2f} (Range: {min_takes}-{max_takes})")
    print(f"Total Preprocessed Samples              : {total_preprocessed}")
    print(f"Video Trimming Success Rate             : {trim_success_rate:.2f}%")
    print(f"Pose Extraction Success Rate            : {pose_success_rate:.2f}%")
    print("=" * 80 + "\n")
    
    # 3. Evaluate Test Sentences
    eval_results = []
    
    print("=" * 80)
    print("TEST SENTENCE EVALUATION REPORT")
    print("=" * 80)
    
    for idx, sentence in enumerate(TEST_SENTENCES, 1):
        norm_sentence = normalize_arabic_text(sentence)
        words = norm_sentence.split()
        total_words = len(words)
        
        matched_units = longest_match_first_tokenize(
            sentence, token_index, alias_map, semantic_matcher
        )
        
        matched_words_count = 0
        matched_tokens = []
        missing_tokens = []
        match_types = []
        
        for unit in matched_units:
            phrase = unit["phrase"]
            token = unit["token"]
            match_type = unit["match_type"]
            words_in_unit = len(phrase.split())
            
            if token is not None:
                matched_words_count += words_in_unit
                matched_tokens.append(f"{phrase}->{token}({match_type})")
                match_types.append(match_type)
            else:
                missing_tokens.append(phrase)
                match_types.append("missing")
                
        coverage = (matched_words_count / total_words * 100) if total_words > 0 else 0.0
        
        # Display to stdout
        print(f"Sentence {idx}: '{sentence}'")
        print(f"  Normalized  : '{norm_sentence}'")
        print(f"  Matched     : {', '.join(matched_tokens) if matched_tokens else 'None'}")
        print(f"  Missing     : {', '.join(missing_tokens) if missing_tokens else 'None'}")
        print(f"  Coverage    : {coverage:.1f}% (Words matched: {matched_words_count}/{total_words})")
        print("-" * 50)
        
        eval_results.append({
            "sentence_id": f"SNT_{idx:03d}",
            "original_sentence": sentence,
            "normalized_sentence": norm_sentence,
            "total_words": total_words,
            "matched_words": matched_words_count,
            "coverage_percentage": round(coverage, 2),
            "matched_tokens_details": ", ".join(matched_tokens),
            "missing_tokens": ", ".join(missing_tokens),
            "match_types_used": ", ".join(set(match_types))
        })
        
    print("=" * 80 + "\n")
    
    # 4. Save CSV report
    df_eval = pd.DataFrame(eval_results)
    config.EVALUATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_eval.to_csv(config.EVALUATION_REPORT_PATH, index=False, encoding="utf-8-sig")
    logger.info(f"Saved evaluation report CSV to: {config.EVALUATION_REPORT_PATH}")
    
    return df_eval
