"""
CONTEXT BUILDER
Implements your Excel compression pyramid:

  Position 1-4   → Full verbatim messages
  Position 5-7   → Mix (partial content)
  Position 8-20  → Summary of group
  Position 21-35 → Heavier summary
  Position 35-50 → Light compressed summary
  50+            → LTM archive only

Session weighting:
  Sessions 1-5   → weight 1.0
  Sessions 6-10  → weight 0.8
  Sessions 11-14 → weight 0.6
  Sessions 15-29 → weight 0.2
  Sessions 20-30 → weight 0.1
"""

import os
from typing import List, Optional
from utils.models import ChatMessage
from utils.chat_store import get_session_messages


# ── Context windows (from your Excel) ─────────────────────────────────────────

VERBATIM_COUNT  = 4     # last N messages passed as-is
MIX_RANGE       = (5, 7)
SUMMARY_RANGE   = (8, 20)
HEAVY_RANGE     = (21, 35)
LIGHT_RANGE     = (36, 50)
# 50+ → LTM only


def _summarize_group(messages: List[ChatMessage], model: str) -> str:
    """Use Claude to summarize a group of messages."""
    if not messages:
        return ""

    # Build text to summarize
    text = "\n".join(
        f"{m.role.upper()}: {m.content}"
        for m in messages
        if not m.is_summary
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # use Haiku for summaries (fast + cheap)
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"Summarize this conversation concisely in 2-3 sentences, preserving key facts, decisions, and context:\n\n{text}"
            }]
        )
        return f"[SUMMARY of {len(messages)} messages]: {response.content[0].text}"
    except Exception as e:
        # Fallback: simple truncation
        words = text.split()
        return f"[SUMMARY]: {' '.join(words[:100])}..."


def build_context(session_id: str, model: str, memory_context: Optional[str] = None) -> List[dict]:
    """
    Build the message context to pass to the AI using the compression pyramid.
    Returns a list of {role, content} dicts ready for the API.
    """
    messages = get_session_messages(session_id)
    if not messages:
        return []

    # Filter out system messages, keep user/assistant only
    msgs = [m for m in messages if m.role in ("user", "assistant")]

    # Reverse to get newest first, then we'll process
    reversed_msgs = list(reversed(msgs))
    total = len(reversed_msgs)

    context_parts = []

    for i, msg in enumerate(reversed_msgs):
        position = i + 1  # 1-indexed, 1 = most recent

        if position <= VERBATIM_COUNT:
            # ── Last 4: full verbatim ──
            context_parts.append({
                "role":    msg.role,
                "content": msg.content,
                "_pos":    position,
                "_type":   "verbatim"
            })

        elif MIX_RANGE[0] <= position <= MIX_RANGE[1]:
            # ── 5-7: truncated to first 200 chars ──
            truncated = msg.content[:200] + ("..." if len(msg.content) > 200 else "")
            context_parts.append({
                "role":    msg.role,
                "content": truncated,
                "_pos":    position,
                "_type":   "mix"
            })

        elif SUMMARY_RANGE[0] <= position <= SUMMARY_RANGE[1]:
            # ── 8-20: summarize as a group (do once) ──
            if not any(p.get("_type") == "summary_8_20" for p in context_parts):
                group = reversed_msgs[SUMMARY_RANGE[0]-1:SUMMARY_RANGE[1]]
                summary = _summarize_group(
                    [m for m in reversed(group)], model
                )
                if summary:
                    context_parts.append({
                        "role":    "user",
                        "content": summary,
                        "_pos":    position,
                        "_type":   "summary_8_20"
                    })
            break  # stop after this group, rest goes to LTM

        elif HEAVY_RANGE[0] <= position <= HEAVY_RANGE[1]:
            if not any(p.get("_type") == "summary_21_35" for p in context_parts):
                group = reversed_msgs[HEAVY_RANGE[0]-1:HEAVY_RANGE[1]]
                summary = _summarize_group(
                    [m for m in reversed(group)], model
                )
                if summary:
                    context_parts.append({
                        "role":    "user",
                        "content": summary,
                        "_pos":    position,
                        "_type":   "summary_21_35"
                    })
            break

        elif LIGHT_RANGE[0] <= position <= LIGHT_RANGE[1]:
            if not any(p.get("_type") == "summary_36_50" for p in context_parts):
                group = reversed_msgs[LIGHT_RANGE[0]-1:LIGHT_RANGE[1]]
                summary = _summarize_group(
                    [m for m in reversed(group)], model
                )
                if summary:
                    context_parts.append({
                        "role":    "user",
                        "content": f"[DISTANT CONTEXT] {summary}",
                        "_pos":    position,
                        "_type":   "summary_36_50"
                    })
            break

        else:
            # 50+ → skip, handled by LTM recall
            break

    # Re-reverse to chronological order and strip internal fields
    context_parts.reverse()
    clean = [{"role": p["role"], "content": p["content"]} for p in context_parts]

    # Inject memory context at the top if available
    if memory_context:
        clean.insert(0, {
            "role":    "user",
            "content": f"[MEMORY CONTEXT]\n{memory_context}"
        })
        clean.insert(1, {
            "role":    "assistant",
            "content": "I have reviewed the memory context and will use it to inform my responses."
        })

    return clean
