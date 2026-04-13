"""SoxAI Playground API Server.

Manages sandbox sessions, WebSocket terminals, and queue.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.session import router as session_router
from api.terminal import router as terminal_router

app = FastAPI(title="SoxAI Playground", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Will restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session_router)
app.include_router(terminal_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
