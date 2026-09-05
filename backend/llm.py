"""
LLM — one client, so the provider is a setting rather than seventeen edits.

anthropic.Anthropic(api_key=...) appeared in seventeen files. When the direct
API ran out of credit mid-week, every one of them broke and switching to Vertex
meant editing all seventeen — which is the sort of thing you discover at the
worst moment.

WHY VERTEX
Anthropic's billing would not take an Indian card. Vertex bills through Google
Cloud, which already works, and the model is the same one. Cache reads in
us-east5 are twelve times cheaper than asia-east1 — INR 5.25 against INR 65.73
per million tokens — which is worth 200ms of extra latency.

IT FALLS BACK
If Vertex is not configured, the direct API is used. So this works before the
credentials exist and keeps working if the credit is topped up later, without
another round of edits.

MODEL NAMES DIFFER
Vertex uses claude-haiku-4-5@20251001 where the direct API uses
claude-haiku-4-5-20251001 — an @ rather than a hyphen. Handled here so no
caller has to know which provider it is talking to.
"""
import json
import os
from typing import Optional

_client = None
_is_vertex = False


def _vertex_credentials():
    """Credentials from an environment variable rather than a file path.

    A path does not survive a deploy — the JSON has to travel as configuration,
    and the container has nowhere to put a file.
    """
    raw = os.getenv("GOOGLE_VERTEX_CREDENTIALS")
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except Exception as e:
        print(f"[LLM] vertex credentials unusable: {e}")
        return None


def client():
    """The Claude client. Vertex when configured, the direct API otherwise."""
    global _client, _is_vertex
    if _client is not None:
        return _client

    project = os.getenv("VERTEX_PROJECT_ID")
    region = os.getenv("VERTEX_REGION", "us-east5")
    creds = _vertex_credentials() if project else None

    if project and creds:
        try:
            from anthropic import AnthropicVertex
            _client = AnthropicVertex(project_id=project, region=region,
                                      credentials=creds)
            _is_vertex = True
            print(f"[LLM] Vertex — {project} / {region}")
            return _client
        except Exception as e:
            print(f"[LLM] Vertex unavailable, falling back: {e}")

    import anthropic
    _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    _is_vertex = False
    print("[LLM] direct Anthropic API")
    return _client


# The names every caller uses. Kept here so a model change is one edit rather
# than a search across the codebase.
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-5-20250929"


def model(name: str = HAIKU) -> str:
    """The model string this provider expects.

    Vertex wants claude-haiku-4-5@20251001 where the direct API wants
    claude-haiku-4-5-20251001. Callers should not have to care.
    """
    client()          # so _is_vertex is set
    if not _is_vertex:
        return name
    # Last hyphen before the date becomes an @.
    parts = name.rsplit("-", 1)
    return f"{parts[0]}@{parts[1]}" if len(parts) == 2 else name


def ask(prompt: str, max_tokens: int = 200, model_name: str = HAIKU) -> str:
    """One prompt, one string back, empty on failure.

    Most calls in this codebase are exactly this shape, and each was
    constructing its own client and handling its own errors.
    """
    try:
        r = client().messages.create(
            model=model(model_name), max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        return (r.content[0].text or "").strip()
    except Exception as e:
        print(f"[LLM] call failed: {e}")
        return ""
