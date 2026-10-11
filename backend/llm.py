"""
LLM — one client, so the provider is a setting rather than seventeen edits.

anthropic.Anthropic(api_key=...) appeared in seventeen files. When the direct
API ran out of credit mid-week every one of them broke — and Anthropic's
billing would not take an Indian card, so topping up was not an option either.

WHY GEMINI
Vertex was the obvious answer: the same model, billed through Google Cloud,
which already works. Authentication and permissions were sorted; the quota was
not. A project with no service history is refused Claude capacity outright —
"enter a new quota value between 0 and 0" — with sales as the only route, which
does not resolve in five days.

So Gemini, which is already paid for and already used for embeddings.

WHAT IT COSTS
Every prompt here was tuned against Haiku, and several are tight: "no question
at all" in the greeting, the two-step day confirmation, the three registers.
Those need checking rather than assuming.

THE SHAPE STAYS
Callers use client().messages.create(...) and read resp.content[0].text, so a
Gemini call is wrapped to look the same. If Anthropic billing is sorted, or a
Vertex quota is granted, this reverts to one environment variable.
"""
import json
import os
from typing import Optional, List

_client = None
_backend = None      # "anthropic" | "vertex" | "gemini"


# ── making Gemini look like Anthropic ─────────────────────────────────────────

class _Block:
    """So resp.content[0].text keeps working."""
    def __init__(self, text: str):
        self.text = text
        self.type = "text"


class _Response:
    def __init__(self, text: str):
        self.content = [_Block(text)]


class _Messages:
    """Only the shape this codebase uses: some user messages, an optional
    system prompt, text back. No tools, no streaming, no images."""

    def __init__(self, model_name: str):
        self._model = model_name

    def create(self, model: str = "", max_tokens: int = 500,
               messages: Optional[List[dict]] = None, system: str = "", **kw):
        from google import genai
        from google.genai import types

        parts = []
        for m in (messages or []):
            c = m.get("content")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                parts.extend(b.get("text", "") for b in c
                             if isinstance(b, dict) and b.get("type") == "text")
        prompt = "\n\n".join(p for p in parts if p)

        # A floor. This model spends budget on thinking before it emits text,
        # so max_tokens=10 — which several one-word classifiers here use
        # deliberately — returned an empty string with finish_reason STOP and
        # no error at all. Ten worked on Haiku; it does not here.
        # Which model, honestly. This used self._model whatever was passed, so
        # twenty-three call sites asking for the cheap tier — one-word
        # classifiers, yes/no judgements, a score — all ran on the full
        # thinking model. The code asked for haiku everywhere and never got it.
        use = model or self._model
        small = use != self._model

        if small:
            # A yes/no does not need to reason about itself first. Thinking
            # tokens are billed as output, so "done" was costing several
            # hundred tokens to produce one word.
            cfg = types.GenerateContentConfig(
                max_output_tokens=max(max_tokens * 2, 64),
                temperature=0.2,
                system_instruction=system or None,
                # No thinking_config. Flash-Lite does not think by default and
                # rejects the setting with a 400 — which, deployed, would have
                # broken every small call at once: the day chain, promotion,
                # the resolver.
            )
            gc = genai_client()
            r = gc.models.generate_content(model=use, contents=prompt, config=cfg)
            return _Response(getattr(r, "text", "") or "")

        cfg = types.GenerateContentConfig(
            # And Devanagari costs more tokens per character than English,
            # so limits sized against Haiku clip mid-word here.
            # Generous because this model thinks before it writes, and the
            # thinking comes out of the same budget — 200 doubled still clipped
            # a two-line greeting mid-word.
            max_output_tokens=max(max_tokens * 8, 1024),
            # These prompts are instructions to follow rather than creative
            # writing. A lower temperature follows them more closely, and the
            # tight ones took several attempts to hold even on Haiku.
            temperature=0.7,
            system_instruction=system or None,
        )
        # Held in a local rather than chained: the client was being collected
        # mid-call and the request failed with "client has been closed".
        gc = genai_client()
        r = gc.models.generate_content(
            model=use, contents=prompt, config=cfg)
        return _Response(getattr(r, "text", "") or "")


class _GeminiClient:
    def __init__(self, model_name: str):
        self.messages = _Messages(model_name)


# ── choosing a backend ────────────────────────────────────────────────────────

def _vertex_credentials():
    raw = os.getenv("GOOGLE_VERTEX_CREDENTIALS")
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_info(
            json.loads(raw),
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except Exception as e:
        print(f"[LLM] vertex credentials unusable: {e}")
        return None


def client():
    """LLM_BACKEND decides: gemini | vertex | anthropic. Defaults to whatever
    is configured, preferring Vertex over the direct API."""
    global _client, _backend
    if _client is not None:
        return _client

    want = (os.getenv("LLM_BACKEND") or "").strip().lower()

    if want == "gemini":
        _client = _GeminiClient(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
        _backend = "gemini"
        print("[LLM] Gemini")
        return _client

    project = os.getenv("VERTEX_PROJECT_ID")
    creds = _vertex_credentials() if project else None
    if want != "anthropic" and project and creds:
        try:
            from anthropic import AnthropicVertex
            _client = AnthropicVertex(
                project_id=project,
                region=os.getenv("VERTEX_REGION", "us-east5"),
                credentials=creds)
            _backend = "vertex"
            print(f"[LLM] Vertex — {project}")
            return _client
        except Exception as e:
            print(f"[LLM] Vertex unavailable: {e}")

    import anthropic
    _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    _backend = "anthropic"
    print("[LLM] direct Anthropic API")
    return _client


_genai = None


def genai_client():
    """One Gemini client for the process.

    Thirteen places were constructing their own, nine of them on the hot path
    — a new connection pool per call, none of them closed. That is what
    produced "Server disconnected without sending a response" and the read
    timeouts.

    Held in a module global rather than a local because of the other failure:
    a client built inside a function was collected mid-call and the request
    came back "client has been closed". A global is never collected.
    """
    global _genai
    if _genai is None:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        # A timeout on every request. Without one, a dropped connection
        # waited forever: the three-person run froze twice at different
        # points, and the scheduler, which walks every user in one pass,
        # would freeze the same way, so one stuck call meant nobody heard
        # anything until the process restarted. ask() already turns a
        # failure into "", and every caller already handles "".
        from google.genai import types as _t
        secs = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
        _genai = genai.Client(
            api_key=key,
            http_options=_t.HttpOptions(timeout=int(secs * 1000)))
    return _genai


HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-5-20250929"


def model(name: str = HAIKU) -> str:
    """The model string for whichever provider is in use.

    Gemini ignores it — the model is fixed on the client — but every caller
    passes one and none of them should break.
    """
    client()
    if _backend == "gemini":
        # The cheap tier for the small calls. Everything asking for haiku was
        # sized for a fast, cheap model and got the full one instead.
        if name == HAIKU or "haiku" in (name or ""):
            return os.getenv("GEMINI_LITE_MODEL", "gemini-flash-lite-latest")
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if _backend != "vertex":
        return name
    parts = name.rsplit("-", 1)
    return f"{parts[0]}@{parts[1]}" if len(parts) == 2 else name


def backend() -> str:
    client()
    return _backend or "unknown"


def ask(prompt: str, max_tokens: int = 200, model_name: str = HAIKU) -> str:
    """One prompt, one string back, empty on failure."""
    try:
        r = client().messages.create(
            model=model(model_name), max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        return (r.content[0].text or "").strip()
    except Exception as e:
        print(f"[LLM] call failed: {e}")
        return ""
