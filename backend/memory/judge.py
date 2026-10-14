"""
JUDGE — one small yes/no question to the model, remembered.

The places that used to decide by word lists — is "Pastilla BP" a medicine,
is "hijo" family, is this video the song we offered — now ask instead, in
whatever language the words are in. Each distinct question is asked once
per process and the answer kept, so a label seen every scheduler pass costs
one call, not one per pass.

yes_no() raises when the model cannot be reached or does not answer. Every
caller decides what a missing answer means for it, because the safe default
differs: an unknown medicine should not get a chat check-in, an unchecked
song should be offered without its link.
"""
import time
from typing import Dict, Tuple

_CACHE: Dict[str, Tuple[bool, float]] = {}
_TTL = 24 * 3600
_MAX = 5000


def yes_no(question: str, key: str = "") -> bool:
    k = key or question
    hit = _CACHE.get(k)
    if hit and time.time() - hit[1] < _TTL:
        return hit[0]

    from llm import ask
    got = (ask(question.strip() + "\n\nAnswer with one word: YES or NO.",
               max_tokens=5) or "").strip().upper()
    if got.startswith("YES"):
        ans = True
    elif got.startswith("NO"):
        ans = False
    else:
        raise ValueError(f"no yes/no answer: {got[:40]!r}")

    if len(_CACHE) > _MAX:
        _CACHE.clear()
    _CACHE[k] = (ans, time.time())
    return ans
