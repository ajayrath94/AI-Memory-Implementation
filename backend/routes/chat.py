from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from engine.engine_router import process_input

router = APIRouter()

class ChatRequest(BaseModel):
    text:       str
    model:      str = "claude-sonnet-4-20250514"
    session_id: Optional[str] = None

@router.post("/")
async def chat(req: ChatRequest):
    return await process_input(
        text=req.text,
        model=req.model,
        session_id=req.session_id,
    )
