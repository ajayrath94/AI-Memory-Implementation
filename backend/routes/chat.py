from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from engine.engine_router import process_input, end_session

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
    Call this when user closes the app or starts a new chat.
    Triggers recursive summarization of the session.
    """
    return await end_session(req.session_id, req.user_id)
