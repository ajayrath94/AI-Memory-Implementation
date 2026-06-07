"""
PILLAR CLASSIFIER
Classifies any input text into Core, Emotion, Functional pillars
and Modifiers, then builds a 3x3 matrix per the paper spec.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time

CORE_PILLARS = {
    "FINANCE":         ["money", "budget", "invest", "expense", "salary", "savings", "debt", "cost", "price", "bank"],
    "ASPIRATIONS":     ["dream", "goal", "future", "ambition", "hope", "vision", "aspire", "achieve", "want to be"],
    "CAREER_GOAL":     ["job", "career", "work", "promotion", "skill", "resume", "interview", "project", "startup", "business"],
    "HEALTH_WELLNESS": ["health", "exercise", "diet", "sleep", "stress", "mental", "fitness", "workout", "eat", "weight"],
    "ENTERTAINMENT":   ["movie", "music", "game", "book", "show", "watch", "read", "play", "fun", "enjoy"],
    "GENERAL":         [],
}

EMOTION_PILLARS = {
    "OPTIMISM": ["excited", "hopeful", "confident", "positive", "great", "awesome", "motivated"],
    "JOY":      ["happy", "joy", "love", "wonderful", "amazing", "fantastic", "glad", "thrilled"],
    "FEAR":     ["scared", "afraid", "worried", "nervous", "anxious", "fear", "uncertain"],
    "SADNESS":  ["sad", "depressed", "unhappy", "down", "lonely", "miss", "lost", "disappointed"],
    "ANGER":    ["angry", "frustrated", "annoyed", "mad", "upset", "hate", "irritated"],
    "STRESS":   ["stress", "overwhelmed", "tired", "exhausted", "pressure", "busy", "burnout"],
    "NEUTRAL":  [],
}

FUNCTIONAL_PILLARS = {
    "PLAN":   ["plan", "schedule", "organize", "prepare", "strategy", "roadmap"],
    "SEARCH": ["find", "search", "look for", "where", "what is", "who is", "recommend"],
    "ORDER":  ["order", "buy", "get", "purchase", "book", "reserve"],
    "TRACK":  ["track", "monitor", "follow", "check", "status", "progress", "update"],
    "NUDGE":  ["remind", "nudge", "notify", "alert", "make sure"],
    "CHAT":   [],
}

MODIFIERS = {
    "QUANTITY":    ["how many", "how much", "number", "count", "total"],
    "SPECIFICITY": ["specific", "exactly", "particular", "precise", "detail"],
    "FORMAT":      ["list", "table", "summary", "brief", "detailed", "explain"],
    "LOCATION":    ["where", "location", "place", "near"],
    "EXCLUSION":   ["not", "except", "without", "avoid", "exclude"],
    "URGENCY":     ["urgent", "asap", "now", "immediately", "today", "quick"],
    "CONDITION":   ["if", "when", "unless", "only if", "depends"],
    "PREFERENCE":  ["prefer", "like", "want", "would rather", "favorite", "best"],
    "TEMPORAL":    ["yesterday", "today", "tomorrow", "week", "month", "year", "soon", "later"],
    "COMPARISON":  ["vs", "versus", "compare", "better", "worse", "difference"],
}


@dataclass
class MatrixCell:
    primary:   str
    secondary: str
    modifier:  Optional[str] = None


@dataclass
class PillarMatrix:
    subject: MatrixCell
    action:  MatrixCell
    context: MatrixCell


@dataclass
class ClassifiedInput:
    text:       str
    core:       str
    emotion:    str
    functional: str
    modifiers:  List[str]
    matrix:     PillarMatrix
    timestamp:  float = field(default_factory=time.time)


def _score_keywords(text: str, keyword_map: dict, fallback: str) -> str:
    lower = text.lower()
    scores = {
        pillar: sum(1 for kw in keywords if kw in lower)
        for pillar, keywords in keyword_map.items()
        if keywords
    }
    if not scores or max(scores.values()) == 0:
        return fallback
    return max(scores, key=scores.get)


def _detect_modifiers(text: str) -> List[str]:
    lower = text.lower()
    return [
        mod for mod, keywords in MODIFIERS.items()
        if any(kw in lower for kw in keywords)
    ]


def _build_matrix(text: str, core: str, emotion: str, functional: str, modifiers: List[str]) -> PillarMatrix:
    subject_words = " ".join(text.split()[:3])
    return PillarMatrix(
        subject=MatrixCell(primary=subject_words, secondary=core,       modifier=modifiers[0] if modifiers else None),
        action= MatrixCell(primary=functional,    secondary=functional,  modifier=modifiers[1] if len(modifiers) > 1 else None),
        context=MatrixCell(primary=emotion,       secondary=emotion,     modifier=modifiers[2] if len(modifiers) > 2 else None),
    )


def classify_input(text: str) -> ClassifiedInput:
    core       = _score_keywords(text, CORE_PILLARS,       "GENERAL")
    emotion    = _score_keywords(text, EMOTION_PILLARS,    "NEUTRAL")
    functional = _score_keywords(text, FUNCTIONAL_PILLARS, "CHAT")
    modifiers  = _detect_modifiers(text)
    matrix     = _build_matrix(text, core, emotion, functional, modifiers)
    return ClassifiedInput(text=text, core=core, emotion=emotion,
                           functional=functional, modifiers=modifiers, matrix=matrix)
