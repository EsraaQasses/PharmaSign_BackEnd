import re
import json
from pathlib import Path
from src.sign_retrieval.config import TOKEN_ALIAS_MAP_PATH
from src.sign_retrieval.utils import get_logger

logger = get_logger("text_normalization")

def normalize_arabic_text(text: str) -> str:
    """
    Standardizes Arabic text for retrieval:
    1. Removes Arabic diacritics (harakat).
    2. Removes tatweel (elongation).
    3. Normalizes Alef variants (أ, إ, آ -> ا).
    4. Normalizes Yaa (ى -> ي).
    5. Normalizes Teh Marbuta (ة -> ه).
    6. Normalizes Hamza variants (ؤ -> و, ئ -> ي).
    7. Standardizes Indic/Arabic digits (٠-٩ -> 0-9).
    8. Lowercases non-Arabic letters.
    9. Removes extra spaces and punctuation.
    """
    if not isinstance(text, str):
        return ""

    text = text.strip()
    
    # 1. Lowercase English/non-Arabic characters
    text = text.lower()
    
    # 2. Normalize Indic/Arabic numbers to standard English digits
    indic_to_eng = {
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"
    }
    for old, new in indic_to_eng.items():
        text = text.replace(old, new)
        
    # 3. Replacements for Arabic letter normalization
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "", # tatweel
        "ً": "", # diacritics (fathatan)
        "ٌ": "", # dammatan
        "ٍ": "", # kasratan
        "َ": "", # fatha
        "ُ": "", # damma
        "ِ": "", # kasra
        "ّ": "", # shadda
        "ْ": "", # sukun
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
        
    # 4. Clean punctuation and replace with space
    text = re.sub(r"[^\w\s\d]", " ", text)
    
    # 5. Clean extra spaces
    text = " ".join(text.split())
    
    return text

def generate_starter_alias_map() -> dict:
    """Generates a default starter alias map dictionary with common Arabic medical variants."""
    starter_map = {
        "علاج": "دواء",
        "ادويه": "دواء",
        "الدواء": "دواء",
        "العلاج": "دواء",
        "الشراب": "شراب",
        "قبل الفطور": "قبل الاكل",
        "بعد الفطور": "بعد الاكل",
        "صباحا": "الصباح",
        "مساء": "الليل",
        "مكان بارد": "ممكان بارد",
        "اسبوع": "اسبوع",
    }
    
    # Normalize both keys and values of the starter map to ensure consistency
    normalized_map = {}
    for key, val in starter_map.items():
        norm_key = normalize_arabic_text(key)
        norm_val = normalize_arabic_text(val)
        normalized_map[norm_key] = norm_val
        
    return normalized_map

def load_alias_map() -> dict:
    """Loads the alias map from JSON or generates a starter version if missing."""
    if TOKEN_ALIAS_MAP_PATH.exists():
        try:
            with open(TOKEN_ALIAS_MAP_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure loaded data keys and values are normalized
            normalized_map = {}
            for k, v in data.items():
                normalized_key = normalize_arabic_text(k)
                if isinstance(v, list):
                    normalized_map[normalized_key] = normalized_key
                    for alias in v:
                        normalized_alias = normalize_arabic_text(alias)
                        if normalized_alias:
                            normalized_map[normalized_alias] = normalized_key
                else:
                    normalized_map[normalized_key] = normalize_arabic_text(v)
            return normalized_map
        except Exception as e:
            logger.warning(f"Failed to read alias map file. Generating starter instead. Error: {e}")
            
    # File doesn't exist, create it
    logger.info(f"Alias map file not found. Generating starter alias map at: {TOKEN_ALIAS_MAP_PATH}")
    starter = generate_starter_alias_map()
    try:
        with open(TOKEN_ALIAS_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(starter, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to write starter alias map: {e}")
    return starter

def resolve_aliases(text: str, alias_map: dict) -> str:
    """
    Checks if the normalized input text has a matching alias/synonym.
    If so, returns the resolved synonym. Otherwise returns the input.
    """
    normalized_text = normalize_arabic_text(text)
    return alias_map.get(normalized_text, normalized_text)
