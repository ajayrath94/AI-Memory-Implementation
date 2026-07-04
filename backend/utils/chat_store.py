"""
CHAT STORE
Stores all messages and sessions in memory (phase 2: swap for Supabase).
Every message is uniquely identified by:
  - message.id       (UUID)
  - message.session_id
  - message.model    (which AI responded)
  - message.role     (user | assistant)
  - message.pillar   (classified pillar tags)
"""

import time
from typing import Dict, List, Optional
from utils.models import ChatMessage, Session

# In-memory stores (phase 2: replace with DB)
_messages: Dict[str, ChatMessage] = {}   # message_id → ChatMessage
_sessions: Dict[str, Session]    = {}    # session_id → Session


# ── Session management ─────────────────────────────────────────────────────────

def create_session(model: str) -> Session:
    session = Session(model=model)
    _sessions[session.id] = session
    return session


def get_session(session_id: str) -> Optional[Session]:
    return _sessions.get(session_id)


def get_or_create_session(session_id: Optional[str], model: str) -> Session:
    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        session.updated_at = time.time()
        session.model = model  # update model if switched
        return session
    return create_session(model)


def update_session_weight(session_id: str):
    """Decay session weight based on age per your Excel spec."""
    session = _sessions.get(session_id)
    if not session:
        return
    age_days = (time.time() - session.created_at) / 86400
    # Weight table from your Excel
    if age_days <= 1:
        session.weight = 1.0    # sessions 1-5: 50% → normalized to 1.0
    elif age_days <= 3:
        session.weight = 0.8    # sessions 6-10: 40%
    elif age_days <= 7:
        session.weight = 0.6    # sessions 11-14: 30%
    elif age_days <= 14:
        session.weight = 0.2    # sessions 15-29: 10%
    else:
        session.weight = 0.1    # sessions 20-30: 5%


# ── Message management ─────────────────────────────────────────────────────────

def save_message(msg: ChatMessage) -> ChatMessage:
    _messages[msg.id] = msg
    session = _sessions.get(msg.session_id)
    if session:
        session.message_ids.append(msg.id)
        session.updated_at = time.time()
    return msg


def get_message(message_id: str) -> Optional[ChatMessage]:
    return _messages.get(message_id)


def get_session_messages(session_id: str) -> List[ChatMessage]:
    """Get all messages for a session in chronological order."""
    session = _sessions.get(session_id)
    if not session:
        return []
    return [_messages[mid] for mid in session.message_ids if mid in _messages]


def get_all_sessions() -> List[Session]:
    return sorted(_sessions.values(), key=lambda s: s.updated_at, reverse=True)


def get_stats() -> dict:
    return {
        "total_messages": len(_messages),
        "total_sessions": len(_sessions),
        "sessions": [
            {
                "id":           s.id,
                "model":        s.model,
                "messages":     len(s.message_ids),
                "weight":       s.weight,
                "created_at":   s.created_at,
            }
            for s in get_all_sessions()
        ]
    }
