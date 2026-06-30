from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from routes.chat import router as chat_router
from routes.memory import router as memory_router
from routes.voice import router as voice_router
from routes.schedule import router as schedule_router
from routes.alerts import router as alerts_router
from routes.memory_state import router as memory_state_router
from utils.auth import require_api_key
import os

app = FastAPI(title="AI Memory API", version="3.0.0")

# CORS — restrict to your app's origin in production
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# All routes protected by API key
app.include_router(chat_router,     prefix="/chat",     tags=["chat"],     dependencies=[Depends(require_api_key)])
app.include_router(memory_router,   prefix="/memory",   tags=["memory"],   dependencies=[Depends(require_api_key)])
app.include_router(voice_router,    prefix="/voice",    tags=["voice"],    dependencies=[Depends(require_api_key)])
app.include_router(schedule_router, prefix="/schedule", tags=["schedule"], dependencies=[Depends(require_api_key)])
app.include_router(alerts_router,   prefix="/alerts",   tags=["alerts"],   dependencies=[Depends(require_api_key)])
app.include_router(memory_state_router, prefix="/memory", tags=["memory-state"], dependencies=[Depends(require_api_key)])

@app.get("/")
def root():
    return {"status": "AI Memory API v3.0 running"}

@app.get("/health")
def health():
    """Public health check — no auth required."""
    return {"status": "ok"}
