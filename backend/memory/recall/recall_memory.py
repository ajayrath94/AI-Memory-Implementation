"""
RECALL MEMORY — STUB

This module previously held an in-process STM/LTM system (Python lists).
It has been retired because:

  1. engine_router._retrieve_memory() only reads from Supabase
     (stm_clusters + ltm_patterns tables) — this in-process store
     was never injected into AI prompts.

  2. The global _stm/_ltm lists were lost on every server restart,
     making them unreliable for a persistent memory system.

  3. All real STM/LTM is now handled by Supabase via supabase_store.py:
       - save_stm_cluster()    → stm_clusters table
       - get_stm_clusters()    → retrieved by cosine similarity
       - promote_stm_to_ltm() → ltm_patterns table
       - get_ltm_patterns()    → retrieved by cosine similarity

Stub functions are kept here so decay_memory.py imports don't break.
"""


def apply_stm_decay(*args, **kwargs):
    """No-op. Real STM lives in Supabase stm_clusters."""
    pass


def apply_ltm_decay(*args, **kwargs):
    """No-op. Real LTM lives in Supabase ltm_patterns."""
    pass


def demote_from_cache(*args, **kwargs):
    """No-op. Cache voiding is handled by _compress_cache_to_stm in engine_router."""
    pass


def get_stm(*args, **kwargs) -> list:
    """Returns empty list. Real STM is in Supabase."""
    return []


def get_ltm(*args, **kwargs) -> list:
    """Returns empty list. Real LTM is in Supabase."""
    return []


def store_memory(*args, **kwargs) -> str:
    """No-op stub."""
    return ""


def recall(*args, **kwargs) -> list:
    """No-op stub. Use engine_router._retrieve_memory() instead."""
    return []


def compress_to_recall(*args, **kwargs):
    """No-op stub. Use engine_router._compress_cache_to_stm() instead."""
    pass
