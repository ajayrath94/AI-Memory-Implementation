from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.chat import router as chat_router
from routes.memory import router as memory_router
from routes.voice import router as voice_router

app = FastAPI(title="AI Memory API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router,   prefix="/chat",   tags=["chat"])
app.include_router(memory_router, prefix="/memory", tags=["memory"])
app.include_router(voice_router,  prefix="/voice",  tags=["voice"])

@app.get("/")
def root():
    return {"status": "AI Memory API v3.0 running — chat + memory + voice"}
