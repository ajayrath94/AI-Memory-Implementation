from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import threading
from engine.engine_router import process_input, end_session
from memory.user_memory_store import process_session_end

router = APIRouter()

class ProactiveContext(BaseModel):
    last_seen_hours: float = 0.0
    opened_app:      bool  = True
    hour:            Optional[int] = None

class ChatRequest(BaseModel):
    text:       str
    model:      str = "claude-haiku-4-5"
    session_id: Optional[str] = None
    user_id:    str = "default"
    context:    Optional[ProactiveContext] = None

class EndSessionRequest(BaseModel):
    session_id: str
    user_id:    str = "default"

@router.post("/")
async def chat(req: ChatRequest):
    text = req.text

    # If text is empty + context provided → Nancy opens proactively
    if not text.strip() and req.context:
        from memory.schedule_engine import generate_proactive_script, should_nancy_open
        opens = should_nancy_open(
            req.user_id,
            req.context.last_seen_hours,
            req.context.opened_app,
        )
        if opens:
            result = generate_proactive_script(
                req.user_id,
                hour = req.context.hour,
            )
            text = result.get("script", "")
            if not text:
                text = "Namaste! Kaise ho aap?"

    return await process_input(
        text=text,
        model=req.model,
        session_id=req.session_id,
        user_id=req.user_id,
    )

@router.post("/end-session")
async def end_session_route(req: EndSessionRequest):
    """
    Trigger session summarization in BACKGROUND.
    Returns immediately — summarization happens async.
    """
    def _summarize():
        try:
            process_session_end(req.session_id, req.user_id)
            print(f"[Background] Session summarized: {req.session_id[:8]}")
        except Exception as e:
            print(f"[Background] Summarization failed: {e}")

    # Fire and forget — don't wait
    thread = threading.Thread(target=_summarize, daemon=True)
    thread.start()

    return {"status": "summarizing", "session_id": req.session_id}


class EditRequest(BaseModel):
    old_message_id:  str
    old_reply_id:    Optional[str] = None
    new_text:        str
    model:           str = "claude-haiku-4-5"
    session_id:      Optional[str] = None
    user_id:         str = "default"

@router.post("/edit")
async def edit_message(req: EditRequest):
    """
    Handle message edit & resend:
    1. Soft-delete old user message + Nancy reply
    2. Process new message normally
    """
    from supabase_store import get_client
    db = get_client()

    # Soft delete old user message
    try:
        db.table("messages").update({
            "is_deleted": True,
        }).eq("id", req.old_message_id).execute()
    except Exception as e:
        print(f"[Edit] Failed to soft-delete user message: {e}")

    # Soft delete old Nancy reply if provided
    if req.old_reply_id:
        try:
            db.table("messages").update({
                "is_deleted": True,
            }).eq("id", req.old_reply_id).execute()
        except Exception as e:
            print(f"[Edit] Failed to soft-delete reply: {e}")

    # Process new message normally
    return await process_input(
        text       = req.new_text,
        model      = req.model,
        session_id = req.session_id,
        user_id    = req.user_id,
    )
