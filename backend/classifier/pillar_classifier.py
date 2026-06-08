"""
PILLAR CLASSIFIER
Classifies input into Core / Emotion / Functional pillars + Modifiers.
Builds a 3x3 matrix per the paper spec:
  y = m * x^n
  m = cosine similarity (pillar match strength)
  x = matrix vector
  n = keyword count
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

CORE_PILLARS = {
    "FINANCE":         ["money","budget","invest","expense","salary","savings","debt","cost","price","bank","income","spend"],
    "ASPIRATIONS":     ["dream","goal","future","ambition","hope","vision","aspire","achieve","want to be","purpose"],
    "CAREER_GOAL":     ["job","career","work","promotion","skill","resume","interview","project","startup","business","role"],
    "HEALTH_WELLNESS": ["health","exercise","diet","sleep","stress","mental","fitness","workout","eat","weight","tired","energy"],
    "ENTERTAINMENT":   ["movie","music","game","book","show","watch","read","play","fun","enjoy","hobby"],
    "GENERAL":         [],
}

EMOTION_PILLARS = {
    "OPTIMISM": ["excited","hopeful","confident","positive","great","awesome","motivated","looking forward"],
    "JOY":      ["happy","joy","love","wonderful","amazing","fantastic","glad","thrilled","grateful"],
    "FEAR":     ["scared","afraid","worried","nervous","anxious","fear","uncertain","unsure","panic"],
    "SADNESS":  ["sad","depressed","unhappy","down","lonely","miss","lost","disappointed","grief"],
    "ANGER":    ["angry","frustrated","annoyed","mad","upset","hate","irritated","furious"],
    "STRESS":   ["stress","overwhelmed","tired","exhausted","pressure","busy","burnout","swamped"],
    "NEUTRAL":  [],
}

FUNCTIONAL_PILLARS = {
    "PLAN":   ["plan","schedule","organize","prepare","strategy","roadmap","layout","arrange"],
    "SEARCH": ["find","search","look for","where","what is","who is","recommend","suggest","discover"],
    "ORDER":  ["order","buy","get","purchase","book","reserve","acquire"],
    "TRACK":  ["track","monitor","follow","check","status","progress","update","measure"],
    "NUDGE":  ["remind","nudge","notify","alert","make sure","don't forget","follow up"],
    "CHAT":   [],
}

MODIFIERS = {
    "QUANTITY":    ["how many","how much","number","count","total","amount","quantity"],
    "SPECIFICITY": ["specific","exactly","particular","precise","detail","specific"],
    "FORMAT":      ["list","table","summary","brief","detailed","explain","format","breakdown"],
    "LOCATION":    ["where","location","place","near","city","country","region"],
    "EXCLUSION":   ["not","except","without","avoid","exclude","skip"],
    "URGENCY":     ["urgent","asap","now","immediately","today","quick","fast","rush"],
    "CONDITION":   ["if","when","unless","only if","depends","in case","assuming"],
    "PREFERENCE":  ["prefer","like","want","would rather","favorite","best","ideal"],
    "TEMPORAL":    ["yesterday","today","tomorrow","week","month","year","soon","later","ago","recently"],
    "COMPARISON":  ["vs","versus","compare","better","worse","difference","or","alternative"],
}


@dataclass
class MatrixCell:
    primary:   str
    secondary: str
    modifier:  Optional[str] = None
    weight:    float = 1.0


@dataclass
class PillarMatrix:
    """
    3x3 matrix per paper:
                PRIMARY    SECONDARY    MODIFIER
    SUBJECT  →  [1,1]      [1,2]        [1,3]
    ACTION   →  [2,1]      [2,2]        [2,3]
    CONTEXT  →  [3,1]      [3,2]        [3,3]
    """
    subject: MatrixCell
    action:  MatrixCell
    context: MatrixCell

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": {"primary": self.subject.primary, "secondary": self.subject.secondary,
                        "modifier": self.subject.modifier, "weight": self.subject.weight},
            "action":  {"primary": self.action.primary,  "secondary": self.action.secondary,
                        "modifier": self.action.modifier,  "weight": self.action.weight},
            "context": {"primary": self.context.primary, "secondary": self.context.secondary,
                        "modifier": self.context.modifier, "weight": self.context.weight},
        }


@dataclass
class ClassifiedInput:
    text:         str
    core:         str
    emotion:      str
    functional:   str
    modifiers:    List[str]
    matrix:       PillarMatrix
    core_score:   float = 0.0   # m in y = m * x^n
    keyword_count: int  = 0     # n in y = m * x^n
    timestamp:    float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "core":          self.core,
            "emotion":       self.emotion,
            "functional":    self.functional,
            "modifiers":     self.modifiers,
            "matrix":        self.matrix.to_dict(),
            "core_score":    self.core_score,
            "keyword_count": self.keyword_count,
        }


def _score(text: str, keyword_map: dict, fallback: str):
    lower = text.lower()
    scores = {}
    for pillar, keywords in keyword_map.items():
        if not keywords:
            continue
        matches = [kw for kw in keywords if kw in lower]
        scores[pillar] = len(matches)

    if not scores or max(scores.values()) == 0:
        return fallback, 0.0, 0

    best_pillar  = max(scores, key=scores.get)
    best_count   = scores[best_pillar]
    total_kw     = len(keyword_map[best_pillar])
    # m = keyword_match / total_keywords (normalized similarity)
    m_score      = best_count / max(total_kw, 1)
    return best_pillar, m_score, best_count


def _detect_modifiers(text: str) -> List[str]:
    lower = text.lower()
    return [mod for mod, kws in MODIFIERS.items() if any(kw in lower for kw in kws)]


def _build_matrix(text: str, core: str, emotion: str, functional: str,
                  modifiers: List[str], core_score: float) -> PillarMatrix:
    words        = text.split()
    subject_text = " ".join(words[:4]) if words else text[:30]
    mod0         = modifiers[0] if modifiers else None
    mod1         = modifiers[1] if len(modifiers) > 1 else None
    mod2         = modifiers[2] if len(modifiers) > 2 else None

    return PillarMatrix(
        subject=MatrixCell(primary=subject_text,  secondary=core,       modifier=mod0, weight=core_score),
        action= MatrixCell(primary=functional,    secondary=functional,  modifier=mod1, weight=0.8),
        context=MatrixCell(primary=emotion,       secondary=emotion,     modifier=mod2, weight=0.6),
    )


def classify_input(text: str) -> ClassifiedInput:
    core,       core_score,  core_n  = _score(text, CORE_PILLARS,       "GENERAL")
    emotion,    _,           _       = _score(text, EMOTION_PILLARS,    "NEUTRAL")
    functional, _,           _       = _score(text, FUNCTIONAL_PILLARS, "CHAT")
    modifiers                        = _detect_modifiers(text)
    matrix                           = _build_matrix(text, core, emotion, functional, modifiers, core_score)

    return ClassifiedInput(
        text=text, core=core, emotion=emotion, functional=functional,
        modifiers=modifiers, matrix=matrix,
        core_score=core_score, keyword_count=core_n,
    )
