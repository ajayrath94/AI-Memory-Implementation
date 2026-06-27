from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import threading
from engine.engine_router import process_input, end_session
from memory.user_memory_store import process_session_end

router = APIRouter()

class ChatRequest(BaseModel):
    text:       str
    model:      str = "claude-sonnet-4-20250514"
    session_id: Optional[str] = None
    user_id:    str = "default"

class EndSessionRequest(BaseModel):
    session_id: str
    user_id:    str = "default"

@router.post("/")
async def chat(req: ChatRequest):
    return await process_input(
        text=req.text,
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
