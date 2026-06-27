"""
RECALL MEMORY — STM + LTM
f = w + b with dynamic learning rate per tier.

STM: base_lr=0.4, λ=0.1 (hours)
LTM: base_lr=0.1, λ=0.01 (days)

Promotion: recall_count >= 3 → STM → LTM
Associative chaining: pillar tag overlap boosts score
"""

import time
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from memory.cache.cache_memory import get_active_slots, CacheSlot

RECALL_THRESHOLD    = 0.15
VOID_THRESHOLD      = 0.05
PROMOTION_THRESHOLD = 3
STM_MAX             = 100
LTM_MAX             = 500


@dataclass
class MemoryEntry:
    id:           str
    text:         str
    metadata:     Dict
    timestamp:    float = field(default_factory=time.time)
    strength:     float = 1.0
    recall_count: int   = 0
    tier:         str   = "stm"
    pillar_tags:  List[str] = field(default_factory=list)
    session_id:   str   = ""
    model:        str   = ""
    lr_used:      float = 0.4


_stm: List[MemoryEntry] = []
_ltm: List[MemoryEntry] = []
_index: Dict[str, MemoryEntry] = {}


def _cosine_sim(query: str, candidates: List[str]) -> List[float]:
    if not candidates:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as sk_cos
        vec    = TfidfVectorizer(min_df=1, stop_words="english")
        matrix = vec.fit_transform([query] + candidates)
        return sk_cos(matrix[0:1], matrix[1:]).flatten().tolist()
    except Exception:
        return [0.0] * len(candidates)


def store_memory(text: str, metadata: Optional[Dict] = None,
                 pillar_tags: Optional[List[str]] = None,
                 session_id: str = "", model: str = "",
                 session_count: int = 1) -> str:
    import uuid
    from memory.learning_rate import dynamic_lr

    lr    = dynamic_lr("stm", time.time(), session_count)
    entry = MemoryEntry(
        id=str(uuid.uuid4()), text=text,
        metadata=metadata or {},
        pillar_tags=pillar_tags or [],
        session_id=session_id, model=model,
        tier="stm", strength=lr, lr_used=lr,
    )
    _stm.insert(0, entry)
    _index[entry.id] = entry

    if len(_stm) > STM_MAX:
        demoted = _stm[STM_MAX:]
        del _stm[STM_MAX:]
        for d in demoted:
            d.tier = "ltm"
            _ltm.insert(0, d)
        if len(_ltm) > LTM_MAX:
            del _ltm[LTM_MAX:]
    return entry.id


def promote_to_ltm(entry: MemoryEntry, session_count: int = 1):
    from memory.learning_rate import dynamic_lr
    if entry in _stm:
        _stm.remove(entry)
    entry.tier   = "ltm"
    entry.lr_used = dynamic_lr("ltm", entry.timestamp, session_count)
    if entry not in _ltm:
        _ltm.insert(0, entry)


def demote_from_cache(voided_slots: List[CacheSlot], session_count: int = 1):
    for slot in voided_slots:
        store_memory(
            text=f"{slot.pillar}: {slot.value}",
            metadata={"source": "cache_decay", "key": slot.key, "ts": slot.timestamp},
            pillar_tags=[slot.core, slot.emotion, slot.functional],
            session_id=slot.session_id, model=slot.model,
            session_count=session_count,
        )


def recall(input_text: str, pillar_tags: Optional[List[str]] = None,
           top_k: int = 5, session_count: int = 1) -> List[dict]:
    """Find memories resonating above threshold. Uses f=w+b on recall."""
    from memory.learning_rate import update_memory

    all_entries = _stm + _ltm
    if not all_entries:
        return []

    texts  = [e.text for e in all_entries]
    scores = _cosine_sim(input_text, texts)

    results = []
    for entry, score in zip(all_entries, scores):
        # Associative chaining — pillar match boosts score
        if pillar_tags:
            overlap = len(set(pillar_tags) & set(entry.pillar_tags))
            score  += overlap * 0.1

        if score > RECALL_THRESHOLD:
            entry.recall_count += 1
            # f = w + b on recall — reinforces recalled memory
            entry.strength = update_memory(
                w=entry.strength,
                new_input_strength=float(score),
                tier=entry.tier,
                timestamp=entry.timestamp,
                session_count=session_count,
            )
            # Auto-promote frequently recalled STM → LTM
            if entry.tier == "stm" and entry.recall_count >= PROMOTION_THRESHOLD:
                promote_to_ltm(entry, session_count)

            results.append({
                "id":          entry.id,
                "text":        entry.text,
                "score":       round(float(score), 3),
                "tier":        entry.tier,
                "strength":    entry.strength,
                "recall_count": entry.recall_count,
                "lr_used":     entry.lr_used,
                "metadata":    entry.metadata,
                "pillar_tags": entry.pillar_tags,
            })

    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]


def build_memory_context(input_text: str,
                         pillar_tags: Optional[List[str]] = None,
                         session_count: int = 1) -> Optional[str]:
    recalled = recall(input_text, pillar_tags, session_count=session_count)
    if not recalled:
        return None
    return "\n".join(
        f"[{r['tier'].upper()} {round(r['score']*100)}% strength={r['strength']}] {r['text']}"
        for r in recalled
    )


def compress_to_recall(session_id: str = "", model: str = "",
                       session_count: int = 1):
    slots = get_active_slots(session_id=session_id)
    meaningful = [s for s in slots if s["strength"] > 0.3 and s["pillar"] != "RAW"]
    if not meaningful:
        return
    groups = {}
    for s in meaningful:
        groups.setdefault(s["pillar"], []).append(s["value"])
    for pillar, values in groups.items():
        text = f"{pillar}: {', '.join(set(values))}"
        store_memory(text,
                     metadata={"source": "cache_snapshot", "ts": time.time()},
                     pillar_tags=[pillar],
                     session_id=session_id, model=model,
                     session_count=session_count)


def apply_stm_decay(session_count: int = 1):
    from memory.learning_rate import dynamic_lr
    now    = time.time()
    voided = []
    for entry in _stm:
        hours   = (now - entry.timestamp) / 3600.0
        decayed = entry.strength * math.exp(-0.1 * hours)
        if decayed < VOID_THRESHOLD:
            voided.append(entry)
        else:
            entry.strength = decayed
    for entry in voided:
        entry.tier = "ltm"
        _stm.remove(entry)
        _ltm.insert(0, entry)


def apply_ltm_decay():
    now    = time.time()
    voided = []
    for entry in _ltm:
        days    = (now - entry.timestamp) / 86400.0
        decayed = entry.strength * math.exp(-0.01 * days)
        if decayed < VOID_THRESHOLD:
            voided.append(entry)
        else:
            entry.strength = decayed
    for entry in voided:
        _ltm.remove(entry)
        if entry.id in _index:
            del _index[entry.id]


def get_stm() -> List[dict]:
    return [{"id": e.id, "text": e.text, "strength": e.strength,
             "timestamp": e.timestamp, "recall_count": e.recall_count,
             "pillar_tags": e.pillar_tags, "tier": e.tier,
             "lr_used": e.lr_used} for e in _stm]


def get_ltm() -> List[dict]:
    return [{"id": e.id, "text": e.text, "strength": e.strength,
             "timestamp": e.timestamp, "recall_count": e.recall_count,
             "pillar_tags": e.pillar_tags, "tier": e.tier,
             "lr_used": e.lr_used} for e in _ltm]
