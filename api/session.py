"""Session management — create, queue, destroy sandbox sessions."""

import asyncio
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

# Wait until the sandbox container's dev server actually answers HTTP on
# its mapped host port before we tell the caller the session is "active".
# Docker's port proxy accepts TCP connections the instant `docker run`
# returns, but the container's Vite process needs ~1-4s (npm → node →
# vite.listen) to actually bind port 3000. During that window, preview
# proxy requests land in docker-proxy's half-open connection, bubble up
# as httpx.RemoteProtocolError/ReadError (NOT ConnectError), and the
# FastAPI preview route returns 502. Blocking session creation until
# the port is hot eliminates the race at the source.
_DEV_SERVER_READY_TIMEOUT_SECONDS = 20.0
_DEV_SERVER_POLL_INTERVAL_SECONDS = 0.25


async def _wait_for_dev_server(port: int) -> bool:
    """Poll localhost:{port} with a minimal HTTP request until it answers."""
    deadline = asyncio.get_event_loop().time() + _DEV_SERVER_READY_TIMEOUT_SECONDS
    while asyncio.get_event_loop().time() < deadline:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("localhost", port), timeout=0.5
            )
            writer.write(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(16), timeout=1.0)
            if data.startswith(b"HTTP/"):
                return True
        except (ConnectionRefusedError, ConnectionResetError, asyncio.TimeoutError, OSError):
            pass
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
        await asyncio.sleep(_DEV_SERVER_POLL_INTERVAL_SECONDS)
    return False

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# In-memory session store (would use Redis in production)
_sessions: dict[str, dict] = {}
_queue: list[dict] = []
_next_port = 10000  # Starting port for preview


class CreateSessionRequest(BaseModel):
    api_key: str
    tool: str = "claude"  # claude or codex
    prompt: str = ""  # development prompt to auto-start the AI tool


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
    """Remove expired sessions. Queue dequeue now happens explicitly in
    create_session after cleanup, because _start_session is async."""
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


async def _drain_queue():
    """Pull queued sessions off the queue while slots are free. Awaits
    _start_session which blocks until the container's dev server is hot."""
    while _queue and _active_count() < settings.max_sessions:
        queued = _queue.pop(0)
        await _start_session(
            queued["session_id"],
            queued["api_key"],
            queued["port"],
            queued.get("tool", "claude"),
            queued.get("prompt", ""),
        )


async def _start_session(session_id: str, api_key: str, port: int, tool: str = "claude", prompt: str = ""):
    """Actually start the Docker container and wait for the dev server.

    Session transitions: pending/queued → starting → active (ready) OR
    error (docker failed). We intentionally block on dev-server readiness
    so the preview_url we return to the caller is guaranteed hot.
    """
    try:
        container_id = create_sandbox(session_id, api_key, port, tool=tool, prompt=prompt)
        _sessions[session_id].update({
            "status": "starting",
            "container_id": container_id,
            "preview_port": port,
            "created_at": time.time(),
            "last_activity": time.time(),
        })
    except Exception as e:
        _sessions[session_id]["status"] = "error"
        _sessions[session_id]["error"] = str(e)
        return

    # Block until Vite (or whatever dev server the sandbox image runs)
    # is actually responding. If it never comes up within the timeout we
    # still transition to "active" — the preview proxy's warming-up
    # splash will cover the residual tail.
    await _wait_for_dev_server(port)
    _sessions[session_id]["status"] = "active"


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
        "prompt": req.prompt,
        "status": "pending",
        "port": port,
        "created_at": time.time(),
        "last_activity": time.time(),
    }

    if _active_count() < settings.max_sessions:
        await _start_session(session_id, req.api_key, port, tool=req.tool, prompt=req.prompt)
        ws_scheme = "wss" if settings.public_url.startswith("https") else "ws"
        ws_host = settings.public_url.replace("https://", "").replace("http://", "")
        return SessionResponse(
            session_id=session_id,
            status="active",
            preview_url=f"{settings.public_url}/preview/{session_id}",
            terminal_ws=f"{ws_scheme}://{ws_host}/api/terminal/{session_id}",
        )
    else:
        _sessions[session_id]["status"] = "queued"
        _queue.append({"session_id": session_id, "api_key": req.api_key, "port": port, "tool": req.tool, "prompt": req.prompt})
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
        ws_scheme = "wss" if settings.public_url.startswith("https") else "ws"
        ws_host = settings.public_url.replace("https://", "").replace("http://", "")
        return SessionResponse(
            session_id=session_id,
            status="active",
            preview_url=f"{settings.public_url}/preview/{session_id}",
            terminal_ws=f"{ws_scheme}://{ws_host}/api/terminal/{session_id}",
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

    # Slot freed — reap any other expirations and pull from the queue.
    _cleanup_expired()
    await _drain_queue()

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
