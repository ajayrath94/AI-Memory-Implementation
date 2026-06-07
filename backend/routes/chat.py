from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from engine.engine_router import process_input

router = APIRouter()

class Message(BaseModel):
    role:    str
    content: str

class ChatRequest(BaseModel):
    text:    str
    model:   str = "claude-sonnet-4-20250514"
    history: List[Message] = []

@router.post("/")
async def chat(req: ChatRequest):
    return await process_input(
        text=req.text,
        model=req.model,
        history=[m.dict() for m in req.history],
    )
