from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.chat import router as chat_router
from routes.memory import router as memory_router

app = FastAPI(title="AI Memory API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router,   prefix="/chat",   tags=["chat"])
app.include_router(memory_router, prefix="/memory", tags=["memory"])

@app.get("/")
def root():
    return {"status": "AI Memory API v2.0 running"}
