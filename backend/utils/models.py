"""
SHARED DATA MODELS
All dataclasses used across the memory pipeline.
"""

import uuid
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class PillarTag:
    core:       str
    emotion:    str
    functional: str
    modifiers:  List[str]
    matrix:     Dict[str, Any]


@dataclass
class ChatMessage:
    """A single message in a conversation."""
    id:          str = field(default_factory=new_id)
    session_id:  str = ""
    model:       str = ""
    role:        str = ""           # "user" | "assistant"
    content:     str = ""
    timestamp:   float = field(default_factory=time.time)
    pillar:      Optional[PillarTag] = None
    memory_tier: str = "cache"      # "cache" | "stm" | "ltm"
    is_summary:  bool = False
    summary_of:  List[str] = field(default_factory=list)  # IDs summarized


@dataclass
class Session:
    """A conversation session."""
    id:          str = field(default_factory=new_id)
    model:       str = ""
    created_at:  float = field(default_factory=time.time)
    updated_at:  float = field(default_factory=time.time)
    message_ids: List[str] = field(default_factory=list)
    weight:      float = 1.0   # decays with age per your Excel
