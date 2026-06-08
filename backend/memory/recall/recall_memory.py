"""
RECALL MEMORY — STM + LTM Store
Implements vector resonance retrieval from the paper.

Trigger:     cos(I(t), M_c) > θ → expand and reactivate
Blend:       M'(x,t) = (1-α)·E(M_c) + α·I(x,t)
λ_stm = 0.1 (hours)
λ_ltm = 0.01 (days)

Promotion logic (from paper):
  - High recall_count + high strength → promote STM → LTM
  - Voided cache slots → demoted to STM
  - Expired STM → demoted to LTM

Associative chaining:
  - One recall triggers related pillars
"""

import time
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from memory.cache.cache_memory import get_active_slots, CacheSlot

RECALL_THRESHOLD     = 0.15   # θ
ALPHA                = 0.4
LAMBDA_STM           = 0.1    # per hour
LAMBDA_LTM           = 0.01   # per day
VOID_THRESHOLD       = 0.05
STM_MAX              = 100
LTM_MAX              = 500
PROMOTION_THRESHOLD  = 3      # recall_count before STM → LTM promotion


@dataclass
class MemoryEntry:
    id:           str
    text:         str
    metadata:     Dict
    timestamp:    float = field(default_factory=time.time)
    strength:     float = 1.0
    recall_count: int   = 0
    tier:         str   = "stm"   # "stm" | "ltm"
    pillar_tags:  List[str] = field(default_factory=list)
    session_id:   str   = ""
    model:        str   = ""


_stm: List[MemoryEntry] = []
_ltm: List[MemoryEntry] = []
_entry_index: Dict[str, MemoryEntry] = {}  # id → entry for fast lookup


# ── Cosine similarity (TF-IDF) ────────────────────────────────────────────────

def _cosine_sim(query: str, candidates: List[str]) -> List[float]:
    if not candidates:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as sk_cos
        vec    = TfidfVectorizer(min_df=1, stop_words="english")
        matrix = vec.fit_transform([query] + candidates)
        sims   = sk_cos(matrix[0:1], matrix[1:]).flatten()
        return sims.tolist()
    except Exception:
        return [0.0] * len(candidates)


# ── Store ──────────────────────────────────────────────────────────────────────

def store_memory(text: str, metadata: Optional[Dict] = None,
                 pillar_tags: Optional[List[str]] = None,
                 session_id: str = "", model: str = "") -> str:
    import uuid
    entry = MemoryEntry(
        id=str(uuid.uuid4()), text=text,
        metadata=metadata or {},
        pillar_tags=pillar_tags or [],
        session_id=session_id, model=model,
        tier="stm",
    )
    _stm.insert(0, entry)
    _entry_index[entry.id] = entry

    # Overflow STM → LTM
    if len(_stm) > STM_MAX:
        demoted = _stm[STM_MAX:]
        del _stm[STM_MAX:]
        for d in demoted:
            d.tier = "ltm"
            _ltm.insert(0, d)
        if len(_ltm) > LTM_MAX:
            del _ltm[LTM_MAX:]
    return entry.id


def promote_to_ltm(entry: MemoryEntry):
    """Explicitly promote a high-value STM entry to LTM."""
    if entry in _stm:
        _stm.remove(entry)
    entry.tier = "ltm"
    if entry not in _ltm:
        _ltm.insert(0, entry)


def demote_from_cache(voided_slots: List[CacheSlot]):
    """Accept voided cache slots and store in STM."""
    for slot in voided_slots:
        store_memory(
            text=f"{slot.pillar}: {slot.value}",
            metadata={"source": "cache_decay", "key": slot.key, "ts": slot.timestamp},
            pillar_tags=[slot.core, slot.emotion, slot.functional],
            session_id=slot.session_id, model=slot.model,
        )


# ── Recall ────────────────────────────────────────────────────────────────────

def recall(input_text: str, pillar_tags: Optional[List[str]] = None,
           top_k: int = 5) -> List[dict]:
    """
    Find memories resonating with input_text above threshold θ.
    Associative chaining: pillar match boosts score.
    """
    all_entries = _stm + _ltm
    if not all_entries:
        return []

    texts  = [e.text for e in all_entries]
    scores = _cosine_sim(input_text, texts)

    results = []
    for entry, score in zip(all_entries, scores):
        # Associative chaining: boost if pillar tags match
        if pillar_tags:
            overlap = len(set(pillar_tags) & set(entry.pillar_tags))
            score  += overlap * 0.1

        if score > RECALL_THRESHOLD:
            entry.recall_count += 1
            # α-blend strength reinforcement
            entry.strength = min(1.0, (1 - ALPHA) * entry.strength + ALPHA * 1.0)

            # Auto-promote to LTM if frequently recalled
            if entry.tier == "stm" and entry.recall_count >= PROMOTION_THRESHOLD:
                promote_to_ltm(entry)

            results.append({
                "id":       entry.id,
                "text":     entry.text,
                "score":    round(float(score), 3),
                "tier":     entry.tier,
                "metadata": entry.metadata,
                "pillar_tags": entry.pillar_tags,
            })

    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]


def build_memory_context(input_text: str,
                         pillar_tags: Optional[List[str]] = None) -> Optional[str]:
    recalled = recall(input_text, pillar_tags)
    if not recalled:
        return None
    return "\n".join(
        f"[{r['tier'].upper()} memory {round(r['score']*100)}% match] {r['text']}"
        for r in recalled
    )


# ── Compress cache snapshot → recall ─────────────────────────────────────────

def compress_to_recall(session_id: str = "", model: str = ""):
    """
    Snapshot active cache slots into recall store.
    Only stores meaningful entities (strength > 0.3).
    """
    slots = get_active_slots()
    meaningful = [s for s in slots if s["strength"] > 0.3 and s["pillar"] != "RAW"]
    if not meaningful:
        return

    # Group by pillar type for semantic storage
    pillar_groups = {}
    for s in meaningful:
        pillar_groups.setdefault(s["pillar"], []).append(s["value"])

    for pillar, values in pillar_groups.items():
        text = f"{pillar}: {', '.join(set(values))}"
        store_memory(text,
                     metadata={"source": "cache_snapshot", "ts": time.time()},
                     pillar_tags=[pillar],
                     session_id=session_id, model=model)


# ── Decay ──────────────────────────────────────────────────────────────────────

def apply_stm_decay():
    now = time.time()
    voided = []
    for entry in _stm:
        hours   = (now - entry.timestamp) / 3600.0
        decayed = entry.strength * math.exp(-LAMBDA_STM * hours)
        if decayed < VOID_THRESHOLD:
            voided.append(entry)
        else:
            entry.strength = decayed
    for entry in voided:
        entry.tier = "ltm"
        _stm.remove(entry)
        _ltm.insert(0, entry)


def apply_ltm_decay():
    now = time.time()
    voided = []
    for entry in _ltm:
        days    = (now - entry.timestamp) / 86400.0
        decayed = entry.strength * math.exp(-LAMBDA_LTM * days)
        if decayed < VOID_THRESHOLD:
            voided.append(entry)
        else:
            entry.strength = decayed
    for entry in voided:
        _ltm.remove(entry)
        if entry.id in _entry_index:
            del _entry_index[entry.id]


# ── Getters ───────────────────────────────────────────────────────────────────

def get_stm() -> List[dict]:
    return [{"id": e.id, "text": e.text, "strength": e.strength,
             "timestamp": e.timestamp, "recall_count": e.recall_count,
             "pillar_tags": e.pillar_tags, "tier": e.tier}
            for e in _stm]


def get_ltm() -> List[dict]:
    return [{"id": e.id, "text": e.text, "strength": e.strength,
             "timestamp": e.timestamp, "recall_count": e.recall_count,
             "pillar_tags": e.pillar_tags, "tier": e.tier}
            for e in _ltm]
