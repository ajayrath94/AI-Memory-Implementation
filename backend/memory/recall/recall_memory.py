"""
RECALL MEMORY  —  cos(I(t), M_c) > θ  →  expand and reactivate
STM: minutes→hours  |  LTM: days→weeks
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from memory.cache.cache_memory import get_active_slots

RECALL_THRESHOLD = 0.2
STM_MAX          = 50
LTM_MAX          = 200


@dataclass
class MemoryEntry:
    text:         str
    metadata:     Dict
    timestamp:    float = field(default_factory=time.time)
    strength:     float = 1.0
    recall_count: int   = 0


_stm_store: List[MemoryEntry] = []
_ltm_store: List[MemoryEntry] = []


def _cosine_sim(query: str, candidates: List[str]) -> List[float]:
    if not candidates:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vec    = TfidfVectorizer(min_df=1, stop_words="english")
        matrix = vec.fit_transform([query] + candidates)
        sims   = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
        return sims.tolist()
    except Exception:
        return [0.0] * len(candidates)


def store_memory(text: str, metadata: Optional[Dict] = None):
    entry = MemoryEntry(text=text, metadata=metadata or {})
    _stm_store.insert(0, entry)
    if len(_stm_store) > STM_MAX:
        promoted = _stm_store[STM_MAX:]
        del _stm_store[STM_MAX:]
        _ltm_store[:0] = promoted
        if len(_ltm_store) > LTM_MAX:
            del _ltm_store[LTM_MAX:]


def recall(input_text: str, top_k: int = 3) -> List[dict]:
    all_entries = _stm_store + _ltm_store
    if not all_entries:
        return []
    texts  = [e.text for e in all_entries]
    scores = _cosine_sim(input_text, texts)
    results = []
    for entry, score in zip(all_entries, scores):
        if score > RECALL_THRESHOLD:
            entry.recall_count += 1
            entry.strength = min(1.0, entry.strength + 0.1)
            results.append({"text": entry.text, "score": float(score),
                            "metadata": entry.metadata})
    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]


def build_memory_context(input_text: str) -> Optional[str]:
    recalled = recall(input_text)
    if not recalled:
        return None
    return "\n".join(
        f"[memory: {round(r['score'] * 100)}% match] {r['text']}"
        for r in recalled
    )


def compress_to_recall():
    slots = get_active_slots()
    if not slots:
        return
    summary = ", ".join(
        f"{s['key']}: {s['value']}"
        for s in slots if s["strength"] > 0.3
    )
    if summary:
        store_memory(summary, {"source": "cache_compression", "ts": time.time()})


def get_stm() -> List[dict]:
    return [{"text": e.text, "strength": e.strength,
             "timestamp": e.timestamp, "recall_count": e.recall_count}
            for e in _stm_store]


def get_ltm() -> List[dict]:
    return [{"text": e.text, "strength": e.strength,
             "timestamp": e.timestamp, "recall_count": e.recall_count}
            for e in _ltm_store]
