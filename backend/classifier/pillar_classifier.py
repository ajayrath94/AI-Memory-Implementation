"""
EMBEDDING CLASSIFIER v4
Single source of truth: classifier/pillars.xml
- All 27 pillars defined in XML
- Core/Emotion/Functional: embedding-based classification
- Modifiers: keyword-based classification
- Priority scoring: HIGH / MEDIUM / LOW per pillar
- 3x3 matrix enrichment: SUBJECT / ACTION / CONTEXT
"""

import os
import math
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from dotenv import load_dotenv

load_dotenv()

# ── XML loader ─────────────────────────────────────────────────────────────────

_XML_PATH = os.path.join(os.path.dirname(__file__), "pillars.xml")
_pillar_defs: Dict[str, dict] = {}


def _load_pillar_defs() -> Dict[str, dict]:
    """Parse pillars.xml into a dict keyed by pillar name."""
    global _pillar_defs
    if _pillar_defs:
        return _pillar_defs

    tree = ET.parse(_XML_PATH)
    root = tree.getroot()

    defs = {}
    for pillar in root.findall("pillar"):
        name = pillar.get("name")
        ptype = pillar.get("type")          # core | emotion | functional | modifier
        classification = pillar.get("classification")  # embedding | keyword

        threshold_el = pillar.find("priority_threshold")
        thresholds = {
            "high":   float(threshold_el.get("high",   "0.78")),
            "medium": float(threshold_el.get("medium", "0.63")),
            "low":    float(threshold_el.get("low",    "0.48")),
        } if threshold_el is not None else {"high": 0.78, "medium": 0.63, "low": 0.48}

        # 3x3 matrix
        matrix = {}
        for row in pillar.findall("matrix/row"):
            row_type = row.get("type")  # SUBJECT | ACTION | CONTEXT
            matrix[row_type] = {}
            for cell in row.findall("cell"):
                pos = cell.get("position")  # primary | secondary | modifier
                matrix[row_type][pos] = cell.text or ""

        # Examples (for embedding pillars)
        examples = [ex.text for ex in pillar.findall("examples/example") if ex.text]

        # Keywords (for modifier pillars)
        keywords = [kw.text.lower() for kw in pillar.findall("keywords/keyword") if kw.text]

        defs[name] = {
            "type":           ptype,
            "classification": classification,
            "thresholds":     thresholds,
            "matrix":         matrix,
            "examples":       examples,
            "keywords":       keywords,
            "description":    (pillar.find("description").text or "").strip(),
        }

    _pillar_defs = defs
    return defs


def get_pillar_defs() -> Dict[str, dict]:
    return _load_pillar_defs()


def pillars_by_type(ptype: str) -> List[str]:
    defs = _load_pillar_defs()
    return [name for name, d in defs.items() if d["type"] == ptype]


# Derived groupings loaded from XML
def _get_groups():
    return {
        "core":       pillars_by_type("core"),
        "emotion":    pillars_by_type("emotion"),
        "functional": pillars_by_type("functional"),
        "modifier":   pillars_by_type("modifier"),
    }


# Legacy constants for backward compatibility
CORE_PILLARS       = ["FINANCE", "ASPIRATIONS", "CAREER_GOAL", "HEALTH_WELLNESS", "ENTERTAINMENT", "GENERAL"]
EMOTION_PILLARS    = ["OPTIMISM", "JOY", "FEAR", "SADNESS", "ANGER", "STRESS", "LOVE"]
FUNCTIONAL_PILLARS = ["PLAN", "SEARCH", "ORDER", "TRACK", "NUDGE"]
MODIFIER_PILLARS   = ["QUANTITY", "SPECIFICITY", "FORMAT", "LOCATION", "EXCLUSION",
                       "URGENCY", "CONDITION", "PREFERENCE", "TEMPORAL", "COMPARISON"]
DIMENSION_ORDER    = CORE_PILLARS + EMOTION_PILLARS + FUNCTIONAL_PILLARS + MODIFIER_PILLARS


# ── Language detection ─────────────────────────────────────────────────────────

# Supported languages
SUPPORTED_LANGUAGES = {
    # Indian languages
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "gu": "Gujarati",
    "bn": "Bengali",
    "pa": "Punjabi",
    "mr": "Marathi",
    "or": "Odia",
    # South Asian
    "ur": "Urdu",
    # Middle East / Gulf
    "ar": "Arabic",
    # European (via langdetect, no script range needed)
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "pt": "Portuguese",
    "it": "Italian",
    # East Asian
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    # Default
    "en": "English",
}

# Unicode script ranges for script-based detection
SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),  # Devanagari (Hindi)
    "mr": (0x0900, 0x097F),  # Devanagari (Marathi)
    "ta": (0x0B80, 0x0BFF),  # Tamil
    "te": (0x0C00, 0x0C7F),  # Telugu
    "kn": (0x0C80, 0x0CFF),  # Kannada
    "ml": (0x0D00, 0x0D7F),  # Malayalam
    "gu": (0x0A80, 0x0AFF),  # Gujarati
    "bn": (0x0980, 0x09FF),  # Bengali
    "pa": (0x0A00, 0x0A7F),  # Punjabi (Gurmukhi)
    "or": (0x0B00, 0x0B7F),  # Odia
    "ur": (0x0600, 0x06FF),  # Urdu (Arabic script)
    "ar": (0x0600, 0x06FF),  # Arabic (same script as Urdu)
    "zh": (0x4E00, 0x9FFF),  # Chinese (CJK)
    "ja": (0x3040, 0x30FF),  # Japanese (Hiragana + Katakana)
    "ko": (0xAC00, 0xD7AF),  # Korean (Hangul)
}

def _detect_language(text: str) -> str:
    """
    Detect language from text using Unicode script ranges.
    Supports all major Indian languages + English.
    Falls back to langdetect for romanized text.
    """
    # Script-based detection (most reliable)
    char_counts = {lang: 0 for lang in SCRIPT_RANGES}
    for char in text:
        cp = ord(char)
        for lang, (start, end) in SCRIPT_RANGES.items():
            if start <= cp <= end:
                char_counts[lang] += 1

    # Return language with most characters
    max_lang = max(char_counts, key=char_counts.get)
    if char_counts[max_lang] > 0:
        # Special case: Devanagari used by both Hindi and Marathi
        if max_lang == "hi":
            return "hi"  # Default to Hindi for Devanagari
        return max_lang

    # Romanized text — use langdetect
    try:
        from langdetect import detect
        lang = detect(text)
        return lang if lang in SUPPORTED_LANGUAGES else "en"
    except Exception:
        # Final fallback — basic Hinglish detection
        hinglish = ["hai", "hoon", "karo", "nahi", "aaj", "kal",
                    "mera", "meri", "aap", "tum", "main", "beta",
                    "enna", "nalla", "emi", "chala", "howdu", "chennagide",
                    "kem", "maja", "ki holo", "bhalo"]
        return "hi" if any(w in text.lower() for w in hinglish) else "en"


# ── Embedding (Google gemini-embedding-001) ────────────────────────────────────

def _embed_google(texts: List[str]) -> List[List[float]]:
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    results = []
    for text in texts:
        result = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text,
        )
        results.append(list(result.embeddings[0].values))
    return results


def embed_text(text: str) -> List[float]:
    try:
        return _embed_google([text])[0]
    except Exception as e:
        print(f"[Embed] Failed: {e}")
        return [0.0] * 3072


def embed_batch(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    try:
        return _embed_google(texts)
    except Exception as e:
        print(f"[Embed] Batch failed: {e}, trying one by one...")
        return [embed_text(t) for t in texts]


# ── Math helpers ───────────────────────────────────────────────────────────────

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot   = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a ** 2 for a in vec_a))
    mag_b = math.sqrt(sum(b ** 2 for b in vec_b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return round(dot / (mag_a * mag_b), 4)


def compute_centroid(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    valid = [v for v in vectors if any(x != 0 for x in v)]
    if not valid:
        return []
    n   = len(valid)
    dim = len(valid[0])
    return [round(sum(v[i] for v in valid) / n, 4) for i in range(dim)]


# ── Priority scoring ───────────────────────────────────────────────────────────

def _score_priority(pillar_name: str, score: float) -> str:
    """Return HIGH / MEDIUM / LOW based on pillar thresholds from XML."""
    defs = _load_pillar_defs()
    thresholds = defs.get(pillar_name, {}).get("thresholds", {"high": 0.78, "medium": 0.63, "low": 0.48})
    if score >= thresholds["high"]:
        return "HIGH"
    elif score >= thresholds["medium"]:
        return "MEDIUM"
    else:
        return "LOW"


# ── Matrix enrichment ──────────────────────────────────────────────────────────

def _get_matrix(pillar_name: str) -> Dict[str, Dict[str, str]]:
    """Return the 3x3 matrix definition for a pillar."""
    defs = _load_pillar_defs()
    return defs.get(pillar_name, {}).get("matrix", {})


# ── Centroid management ────────────────────────────────────────────────────────

_centroid_cache: Dict[str, List[float]] = {}
_api_trigger_cache: Dict[str, List[float]] = {}

API_TRIGGER_EXAMPLES = {
    "book_doctor": [
        "I need to see a doctor", "Book an appointment",
        "Doctor ke paas jaana hai", "Hospital appointment chahiye",
        "Specialist dikhana hai", "Checkup karwana hai",
        "OPD mein jaana hai", "Doctor se milna hai",
    ],
    "play_music": [
        "Play some music", "I want to listen to bhajan",
        "Koi gaana lagao", "Music sunna hai", "Bhajan chalao",
        "Old songs please", "Lata ji ka gaana", "Kishore kumar songs",
    ],
    "cricket_score": [
        "Cricket score kya hai", "India ka match kab hai",
        "IPL mein kaun jeeta", "Match chal raha hai kya",
        "Score kya hai abhi", "India jeet gaya kya", "Batting kaun kar raha",
    ],
    "medicine_reminder": [
        "Dawai yaad dilao", "Medicine reminder set karo",
        "BP ki dawai leni hai", "Remind me about pills",
        "Dawai lena bhool jaata hoon", "Daily medicine alert",
    ],
    "weather_check": [
        "Aaj barish hogi kya", "Weather kaisa hai", "Bahar kitni garmi hai",
        "Umbrella le jaaoon kya", "Temperature kya hai", "Mausam kaisa hai aaj",
    ],
    "emergency": [
        "I do not feel well", "Mujhe achha nahi lag raha",
        "Call someone please", "I need help immediately",
        "Chest mein dard hai", "Bahut dard ho raha", "Breathing problem",
        "Emergency hai", "Help chahiye abhi",
    ],
    "call_family": [
        "I want to call my son", "Beta se baat karni hai",
        "Beti ko call karo", "Family se baat karo",
        "Video call karo bacchon se", "Whatsapp call lagao",
    ],
}

API_THRESHOLDS = {
    "emergency":         0.82,
    "book_doctor":       0.75,
    "call_family":       0.72,
    "medicine_reminder": 0.70,
    "cricket_score":     0.68,
    "weather_check":     0.65,
    "play_music":        0.63,
}


def build_pillar_centroids(force_rebuild: bool = False) -> Dict[str, List[float]]:
    global _centroid_cache
    if _centroid_cache and not force_rebuild:
        return _centroid_cache

    # Try loading from Supabase first
    if not force_rebuild:
        try:
            from supabase_store import get_client
            db     = get_client()
            result = db.table("pillar_centroids").select("*").execute()
            embedding_pillars = [
                name for name, d in _load_pillar_defs().items()
                if d["classification"] == "embedding"
            ]
            if result.data and len(result.data) >= len(embedding_pillars):
                print(f"[Classifier] Loaded {len(result.data)} centroids from Supabase")
                _centroid_cache = {r["pillar"]: r["centroid"] for r in result.data}
                return _centroid_cache
        except Exception as e:
            print(f"[Classifier] Supabase load failed: {e}, rebuilding...")

    # Build from XML examples
    print("[Classifier] Building pillar centroids from pillars.xml...")
    defs      = _load_pillar_defs()
    centroids = {}

    for name, d in defs.items():
        if d["classification"] != "embedding":
            continue
        examples = d["examples"]
        if not examples:
            continue
        print(f"  Embedding {name} ({len(examples)} examples)...")
        try:
            vectors          = embed_batch(examples)
            centroids[name]  = compute_centroid(vectors)
            print(f"  OK {name} → {len(centroids[name])}-dim centroid")
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            centroids[name] = []

    # Save to Supabase
    try:
        from supabase_store import get_client
        db = get_client()
        for pillar, centroid in centroids.items():
            if centroid:
                db.table("pillar_centroids").upsert({
                    "pillar":     pillar,
                    "centroid":   centroid,
                    "updated_at": "now()",
                }, on_conflict="pillar").execute()
        saved = sum(1 for c in centroids.values() if c)
        print(f"[Classifier] Saved {saved}/{len(centroids)} centroids to Supabase")
    except Exception as e:
        print(f"[Classifier] Supabase save failed: {e}")

    _centroid_cache = centroids
    return centroids


def get_centroids() -> Dict[str, List[float]]:
    if not _centroid_cache:
        return build_pillar_centroids()
    return _centroid_cache


def get_api_trigger_centroids() -> Dict[str, List[float]]:
    global _api_trigger_cache
    if _api_trigger_cache:
        return _api_trigger_cache

    try:
        from supabase_store import get_client
        db     = get_client()
        result = db.table("api_trigger_centroids").select("*").execute()
        if result.data and len(result.data) >= 5:
            _api_trigger_cache = {r["trigger"]: r["centroid"] for r in result.data}
            return _api_trigger_cache
    except Exception:
        pass

    print("[Classifier] Building API trigger centroids...")
    centroids = {}
    for trigger, examples in API_TRIGGER_EXAMPLES.items():
        try:
            vectors            = embed_batch(examples)
            centroids[trigger] = compute_centroid(vectors)
            print(f"  OK {trigger}")
        except Exception as e:
            print(f"  FAIL {trigger}: {e}")

    try:
        from supabase_store import get_client
        db = get_client()
        for trigger, centroid in centroids.items():
            if centroid:
                db.table("api_trigger_centroids").upsert({
                    "trigger":    trigger,
                    "centroid":   centroid,
                    "updated_at": "now()",
                }, on_conflict="trigger").execute()
    except Exception:
        pass

    _api_trigger_cache = centroids
    return centroids


def check_api_triggers(embedding: List[float]) -> Dict[str, float]:
    triggers  = get_api_trigger_centroids()
    activated = {}
    for trigger, centroid in triggers.items():
        if not centroid:
            continue
        score     = cosine_similarity(embedding, centroid)
        threshold = API_THRESHOLDS.get(trigger, 0.70)
        if score >= threshold:
            activated[trigger] = round(score, 3)
    return dict(sorted(activated.items(), key=lambda x: x[1], reverse=True))


# ── Modifier detection (keyword-based from XML) ────────────────────────────────

def _detect_modifiers(text: str) -> List[str]:
    """Keyword-based modifier detection using keywords defined in pillars.xml."""
    defs  = _load_pillar_defs()
    lower = text.lower()
    found = []
    for name, d in defs.items():
        if d["classification"] == "keyword" and d["type"] == "modifier":
            if any(kw in lower for kw in d["keywords"]):
                found.append(name)
    return found


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class PillarResult:
    """Rich result for a single classified pillar."""
    name:     str
    score:    float
    priority: str           # HIGH | MEDIUM | LOW
    matrix:   Dict[str, Dict[str, str]] = field(default_factory=dict)


@dataclass
class ClassifiedInput:
    text:          str
    core:          str
    emotion:       str
    functional:    str
    modifiers:     List[str]

    # Scores
    core_score:    float = 0.0
    keyword_count: int   = 0

    # Priority per pillar type
    core_priority:       str = "LOW"
    emotion_priority:    str = "LOW"
    functional_priority: str = "LOW"

    # Rich matrix enrichment
    core_matrix:       Dict = field(default_factory=dict)
    emotion_matrix:    Dict = field(default_factory=dict)
    functional_matrix: Dict = field(default_factory=dict)

    # Vectors and scores
    pillar_vector: List[float] = field(default_factory=list)
    pillar_scores: Dict[str, float] = field(default_factory=dict)
    embedding:     List[float] = field(default_factory=list)
    language:      str   = "en"
    timestamp:     float = field(default_factory=time.time)
    api_triggers:  Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "core":               self.core,
            "core_priority":      self.core_priority,
            "core_matrix":        self.core_matrix,
            "emotion":            self.emotion,
            "emotion_priority":   self.emotion_priority,
            "emotion_matrix":     self.emotion_matrix,
            "functional":         self.functional,
            "functional_priority": self.functional_priority,
            "functional_matrix":  self.functional_matrix,
            "modifiers":          self.modifiers,
            "core_score":         self.core_score,
            "keyword_count":      self.keyword_count,
            "pillar_vector":      self.pillar_vector,
            "pillar_scores":      self.pillar_scores,
            "language":           self.language,
            "api_triggers":       self.api_triggers,
        }


# ── Main classifier ────────────────────────────────────────────────────────────

def classify_input(text: str) -> ClassifiedInput:
    """
    Full embedding-based classification using pillars.xml as source of truth.
    Returns enriched ClassifiedInput with priority and 3x3 matrix per pillar.
    """
    lang      = _detect_language(text)
    embedding = embed_text(text)
    centroids = get_centroids()

    # Score all embedding pillars
    scores = {}
    for pillar, centroid in centroids.items():
        if centroid and len(centroid) == len(embedding):
            scores[pillar] = cosine_similarity(embedding, centroid)

    if not scores:
        return ClassifiedInput(
            text=text, core="GENERAL", emotion="STRESS",
            functional="PLAN", modifiers=[],
            pillar_vector=[0.0] * len(DIMENSION_ORDER),
            embedding=embedding, language=lang,
        )

    # Pick best per group
    core_scores  = {p: scores.get(p, 0) for p in CORE_PILLARS}
    emo_scores   = {p: scores.get(p, 0) for p in EMOTION_PILLARS}
    func_scores  = {p: scores.get(p, 0) for p in FUNCTIONAL_PILLARS}

    core       = max(core_scores,  key=core_scores.get)
    emotion    = max(emo_scores,   key=emo_scores.get)
    functional = max(func_scores,  key=func_scores.get)

    # Priority scoring
    core_priority       = _score_priority(core,       core_scores[core])
    emotion_priority    = _score_priority(emotion,    emo_scores[emotion])
    functional_priority = _score_priority(functional, func_scores[functional])

    # 3x3 matrix enrichment
    core_matrix       = _get_matrix(core)
    emotion_matrix    = _get_matrix(emotion)
    functional_matrix = _get_matrix(functional)

    # Modifier detection (keyword-based)
    modifiers = _detect_modifiers(text)

    # Pillar vector (embedding pillars only, in DIMENSION_ORDER)
    pillar_vector = [round(scores.get(dim, 0.0), 4) for dim in DIMENSION_ORDER]

    # API triggers
    api_triggers = check_api_triggers(embedding)

    non_zero = {k: round(v, 4) for k, v in scores.items() if v > 0.05}

    return ClassifiedInput(
        text=text,
        core=core,
        emotion=emotion,
        functional=functional,
        modifiers=modifiers,
        core_score=core_scores[core],
        keyword_count=0,
        core_priority=core_priority,
        emotion_priority=emotion_priority,
        functional_priority=functional_priority,
        core_matrix=core_matrix,
        emotion_matrix=emotion_matrix,
        functional_matrix=functional_matrix,
        pillar_vector=pillar_vector,
        pillar_scores=non_zero,
        embedding=embedding,
        language=lang,
        api_triggers=api_triggers,
    )
