"""Session management — create, queue, destroy sandbox sessions."""

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.config import settings
from api.docker_manager import (
    create_sandbox,
    destroy_sandbox,
    get_sandbox_status,
    list_active_sandboxes,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# In-memory session store (would use Redis in production)
_sessions: dict[str, dict] = {}
_queue: list[dict] = []
_next_port = 10000  # Starting port for preview


class CreateSessionRequest(BaseModel):
    api_key: str
    tool: str = "claude"  # claude or codex


class SessionResponse(BaseModel):
    session_id: str
    status: str  # active, queued, expired
    queue_position: int | None = None
    estimated_wait: int | None = None  # seconds
    preview_url: str | None = None
    terminal_ws: str | None = None


def _allocate_port() -> int:
    global _next_port
    port = _next_port
    _next_port += 3  # 3 ports per session (3000, 5173, 8080)
    if _next_port > 10100:
        _next_port = 10000
    return port


def _active_count() -> int:
    return len([s for s in _sessions.values() if s["status"] == "active"])


def _cleanup_expired():
    """Remove expired sessions."""
    now = time.time()
    expired = []
    for sid, session in _sessions.items():
        if session["status"] != "active":
            continue
        elapsed = now - session["last_activity"]
        max_age = settings.session_timeout_minutes * 60
        idle_max = settings.idle_timeout_minutes * 60
        if elapsed > idle_max or (now - session["created_at"]) > max_age:
            expired.append(sid)

    for sid in expired:
        destroy_sandbox(sid)
        _sessions[sid]["status"] = "expired"

    # Process queue
    while _queue and _active_count() < settings.max_sessions:
        queued = _queue.pop(0)
        _start_session(queued["session_id"], queued["api_key"], queued["port"])


def _start_session(session_id: str, api_key: str, port: int):
    """Actually start the Docker container."""
    try:
        container_id = create_sandbox(session_id, api_key, port)
        _sessions[session_id].update({
            "status": "active",
            "container_id": container_id,
            "preview_port": port,
            "created_at": time.time(),
            "last_activity": time.time(),
        })
    except Exception as e:
        _sessions[session_id]["status"] = "error"
        _sessions[session_id]["error"] = str(e)


@router.post("", response_model=SessionResponse)
async def create_session(req: CreateSessionRequest):
    """Request a new sandbox session."""
    _cleanup_expired()

    session_id = uuid.uuid4().hex[:10]
    port = _allocate_port()

    _sessions[session_id] = {
        "session_id": session_id,
        "api_key": req.api_key,
        "tool": req.tool,
        "status": "pending",
        "port": port,
        "created_at": time.time(),
        "last_activity": time.time(),
    }

    if _active_count() < settings.max_sessions:
        _start_session(session_id, req.api_key, port)
        return SessionResponse(
            session_id=session_id,
            status="active",
            preview_url=f"https://{session_id}.{settings.preview_domain}",
            terminal_ws=f"ws://localhost:8100/api/terminal/{session_id}",
        )
    else:
        _sessions[session_id]["status"] = "queued"
        _queue.append({"session_id": session_id, "api_key": req.api_key, "port": port})
        position = len(_queue)
        avg_session = 15 * 60  # 15 min average
        wait = (position * avg_session) // settings.max_sessions

        return SessionResponse(
            session_id=session_id,
            status="queued",
            queue_position=position,
            estimated_wait=wait,
        )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session status."""
    _cleanup_expired()

    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["status"] == "active":
        return SessionResponse(
            session_id=session_id,
            status="active",
            preview_url=f"https://{session_id}.{settings.preview_domain}",
            terminal_ws=f"ws://localhost:8100/api/terminal/{session_id}",
        )
    elif session["status"] == "queued":
        position = next((i + 1 for i, q in enumerate(_queue) if q["session_id"] == session_id), 0)
        return SessionResponse(
            session_id=session_id,
            status="queued",
            queue_position=position,
            estimated_wait=(position * 15 * 60) // settings.max_sessions,
        )
    else:
        return SessionResponse(session_id=session_id, status=session["status"])


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """End a session and free the slot."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    destroy_sandbox(session_id)
    _sessions[session_id]["status"] = "ended"

    # Process queue
    _cleanup_expired()

    return {"status": "ended"}


@router.post("/{session_id}/heartbeat")
async def heartbeat(session_id: str):
    """Keep session alive (reset idle timer)."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["last_activity"] = time.time()
    return {"status": "ok"}


@router.get("")
async def list_sessions():
    """List all sessions (admin)."""
    _cleanup_expired()
    return {
        "active": _active_count(),
        "max": settings.max_sessions,
        "queue_length": len(_queue),
        "sessions": [
            {
                "session_id": s["session_id"],
                "status": s["status"],
                "tool": s.get("tool"),
                "age_seconds": int(time.time() - s["created_at"]),
            }
            for s in _sessions.values()
            if s["status"] in ("active", "queued")
        ],
    }
