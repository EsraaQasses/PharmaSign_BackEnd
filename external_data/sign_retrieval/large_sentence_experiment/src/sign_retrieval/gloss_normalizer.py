import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.sign_retrieval import config
from src.sign_retrieval.text_normalization import normalize_arabic_text


DEFAULT_CANONICAL_ALIASES = {
    "الجلد": [
        "جلد",
        "البشره",
        "بشره",
        "البشرة",
        "بشرة",
    ],
    "بعد الاكل": [
        "بعد الطعام",
        "بعد الاكل",
        "بعد الأكل",
        "بعد الوجبه",
        "بعد الوجبة",
        "بعد تناول الطعام",
    ],
    "قبل الاكل": [
        "قبل الطعام",
        "قبل الاكل",
        "قبل الأكل",
        "قبل الوجبه",
        "قبل الوجبة",
        "قبل تناول الطعام",
    ],
    "مع الاكل": [
        "مع الطعام",
        "مع الاكل",
        "مع الأكل",
        "اثناء الطعام",
        "أثناء الطعام",
        "مع الوجبه",
        "مع الوجبة",
    ],
    "حبه": [
        "حبة",
        "حب",
        "حبوب",
        "قرص",
        "اقراص",
        "أقراص",
        "قرص دواء",
    ],
    "كبسوله": [
        "كبسولة",
        "كبسوله",
        "كبسولات",
    ],
    "شراب": [
        "سائل",
        "دواء سائل",
        "شربه",
    ],
    "مرهم": [
        "دهان",
        "مرهم جلدي",
    ],
    "كريم": [
        "دهون",
        "كريم جلدي",
    ],
    "الصباح": [
        "صباح",
        "الصبح",
        "صبح",
        "صباحا",
        "صباحاً",
    ],
    "الليل": [
        "ليل",
        "مساء",
        "المساء",
        "ليلا",
        "ليلاً",
    ],
    "ثلاث مرات": [
        "3 مرات",
        "ثلاث مرات",
        "ثلاثه مرات",
        "ثلاثة مرات",
    ],
    "مرتين": [
        "مرتان",
        "مرتين",
        "مرتين يوميا",
        "مرتين باليوم",
    ],
    "مره واحده": [
        "مرة واحدة",
        "مره واحده",
        "مرة",
        "مره",
    ],
    "نصف حبه": [
        "نصف حبة",
        "نص حبة",
        "نص حبه",
        "نصف قرص",
        "نص قرص",
    ],
    "ماء": [
        "الماء",
        "موية",
        "مويه",
    ],
    "اشرب": [
        "اشرب",
        "تناول مع ماء",
        "خذ مع ماء",
    ],
    "خذ": [
        "خذ",
        "تناول",
        "استعمل",
    ],
    "ضع": [
        "ضع",
        "ادهن",
        "طبّق",
        "طبق",
    ],
    "الاذن": [
        "اذن",
        "الأذن",
    ],
    "الانف": [
        "انف",
        "الأنف",
    ],
    "العين": [
        "عين",
    ],
    "الفم": [
        "فم",
    ],
    "طفح جلدي": [
        "طفح",
        "حساسية جلد",
        "حساسيه جلد",
    ],
    "حساسيه": [
        "حساسية",
        "تحسس",
    ],
    "حراره الغرفه": [
        "حرارة الغرفة",
        "درجة حرارة الغرفة",
        "حراره الغرفة",
    ],
    "بعيد عن الاطفال": [
        "بعيدا عن الاطفال",
        "بعيد عن الأطفال",
        "بعيدا عن الأطفال",
    ],
}


def _load_vocabulary(vocabulary_path: str | Path | None = None) -> list[str]:
    path = Path(vocabulary_path) if vocabulary_path else config.TOKEN_VOCAB_PATH
    if not path.exists():
        raise FileNotFoundError(f"Vocabulary file not found: {path}")
    tokens = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            token = normalize_arabic_text(line.strip())
            if token:
                tokens.append(token)
    return sorted(set(tokens))


def _add_alias(alias_map: dict[str, str], alias: str, canonical: str, vocabulary: set[str]):
    normalized_alias = normalize_arabic_text(alias)
    normalized_canonical = normalize_arabic_text(canonical)
    if normalized_alias and normalized_canonical in vocabulary:
        alias_map[normalized_alias] = normalized_canonical


def _load_aliases(alias_map_path: str | Path | None, vocabulary: set[str]) -> dict[str, str]:
    path = Path(alias_map_path) if alias_map_path else config.TOKEN_ALIAS_MAP_PATH
    alias_map: dict[str, str] = {}

    for canonical, aliases in DEFAULT_CANONICAL_ALIASES.items():
        _add_alias(alias_map, canonical, canonical, vocabulary)
        for alias in aliases:
            _add_alias(alias_map, alias, canonical, vocabulary)

    for token in vocabulary:
        _add_alias(alias_map, token, token, vocabulary)
        if token.startswith("ال") and len(token) > 2:
            _add_alias(alias_map, token[2:], token, vocabulary)

    if not path.exists():
        return alias_map

    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    for key, value in data.items():
        if isinstance(value, list):
            canonical = key
            _add_alias(alias_map, canonical, canonical, vocabulary)
            for alias in value:
                _add_alias(alias_map, alias, canonical, vocabulary)
        else:
            _add_alias(alias_map, key, value, vocabulary)

    return alias_map


def _strip_definite_article(text: str) -> str:
    return text[2:] if text.startswith("ال") and len(text) > 2 else text


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a2 = _strip_definite_article(a)
    b2 = _strip_definite_article(b)
    scores = [
        SequenceMatcher(None, a, b).ratio(),
        SequenceMatcher(None, a2, b2).ratio(),
    ]
    if a2 in b2 or b2 in a2:
        scores.append(min(len(a2), len(b2)) / max(len(a2), len(b2)))
    return max(scores)


def _semantic_fallback(phrase: str, vocabulary: list[str], threshold: float = 0.78) -> tuple[str | None, float]:
    normalized_phrase = normalize_arabic_text(phrase)
    best_token = None
    best_score = 0.0
    for token in vocabulary:
        score = _similarity(normalized_phrase, token)
        if score > best_score:
            best_token = token
            best_score = score
    if best_token is not None and best_score >= threshold:
        return best_token, best_score
    return None, best_score


def _phrase_variants(phrase: str) -> list[str]:
    variants = [phrase]
    words = phrase.split()
    if len(words) == 1:
        word = words[0]
        if word.startswith("لل") and len(word) > 3:
            variants.append("ال" + word[2:])
            variants.append(word[2:])
        if word.startswith("ل") and len(word) > 2:
            variants.append(word[1:])
            variants.append("ال" + word[1:])
        if word.startswith("بال") and len(word) > 4:
            variants.append("ال" + word[3:])
            variants.append(word[3:])
        if word.startswith("ب") and len(word) > 2:
            variants.append(word[1:])
            variants.append("ال" + word[1:])
    deduped = []
    for variant in variants:
        normalized = normalize_arabic_text(variant)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def normalize_gloss_to_vocabulary(
    text: str,
    vocabulary_path=None,
    alias_map_path=None,
    use_semantic: bool = True,
) -> dict:
    vocabulary = _load_vocabulary(vocabulary_path)
    vocabulary_set = set(vocabulary)
    alias_map = _load_aliases(alias_map_path, vocabulary_set)
    normalized_text = normalize_arabic_text(text)
    words = normalized_text.split()
    max_phrase_len = max((len(token.split()) for token in vocabulary), default=1)

    output_tokens: list[str] = []
    matched_units: list[dict] = []
    missing_tokens: list[str] = []
    i = 0

    while i < len(words):
        matched = None
        for length in range(min(max_phrase_len, len(words) - i), 0, -1):
            phrase = " ".join(words[i : i + length])
            for variant in _phrase_variants(phrase):
                if variant in vocabulary_set:
                    matched = {
                        "phrase": phrase,
                        "token": variant,
                        "match_type": "exact" if variant == phrase else "prefix_normalized",
                        "score": 1.0,
                        "words_count": length,
                    }
                    break
                if variant in alias_map:
                    matched = {
                        "phrase": phrase,
                        "token": alias_map[variant],
                        "match_type": "alias" if variant == phrase else "prefix_alias",
                        "score": 1.0,
                        "words_count": length,
                    }
                    break
                if use_semantic:
                    token, score = _semantic_fallback(variant, vocabulary)
                    if token:
                        matched = {
                            "phrase": phrase,
                            "token": token,
                            "match_type": "semantic",
                            "score": score,
                            "words_count": length,
                        }
                        break
            if matched:
                break

        if matched:
            output_tokens.append(matched["token"])
            matched_units.append(matched)
            i += matched["words_count"]
        else:
            missing_tokens.append(words[i])
            matched_units.append(
                {
                    "phrase": words[i],
                    "token": None,
                    "match_type": "missing",
                    "score": 0.0,
                    "words_count": 1,
                }
            )
            i += 1

    return {
        "success": bool(output_tokens),
        "original_text": text,
        "normalized_text": normalized_text,
        "normalized_gloss": " ".join(output_tokens),
        "tokens": output_tokens,
        "matched_units": matched_units,
        "missing_tokens": missing_tokens,
        "vocabulary_size": len(vocabulary),
    }
