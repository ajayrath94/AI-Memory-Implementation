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
            script = result.get("script", "") or "Namaste! Kaise ho aap?"

            # Return the script AS THE REPLY. It used to be assigned to `text`
            # and passed to process_input, which treats it as the USER's
            # message — so the companion answered her own greeting ("aap mujhe
            # puch rahe ho aur main aapko puch raha tha") and every proactive
            # open wrote a fake user turn into the session for the summarizer
            # and extractor to read back as something the user had said.
            from supabase_store import get_or_create_session, save_message
            session = get_or_create_session(req.session_id, req.model, req.user_id)
            sid = session["id"]
            saved = save_message(sid, "assistant", script, req.model)

            return {
                "reply":      script,
                "session_id": sid,
                "message_id": (saved or {}).get("id"),
                "model":      req.model,
                "proactive":  True,
                "slot":       result.get("slot"),
                "priority":   result.get("priority"),
            }

        # should_nancy_open said no — stay quiet rather than inventing a turn.
        return {"reply": "", "session_id": req.session_id, "proactive": False}

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


class DeleteRequest(BaseModel):
    message_id: str
    reply_id:   Optional[str] = None
    user_id:    str = "default"


@router.post("/delete")
async def delete_message(req: DeleteRequest):
    """Soft-delete a message (and optionally its reply). The row is kept as a
    trace (content preserved, is_deleted=True) but excluded from all memory
    operations — recall, summarization, and context all filter is_deleted."""
    from supabase_store import get_client
    db = get_client()
    ids = [req.message_id] + ([req.reply_id] if req.reply_id else [])
    for mid in ids:
        try:
            db.table("messages").update({"is_deleted": True}).eq("id", mid).execute()
        except Exception as e:
            print(f"[Delete] Failed to soft-delete {mid}: {e}")
    return {"status": "deleted", "message_ids": ids}
