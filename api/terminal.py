"""WebSocket terminal — connects browser xterm.js to Docker container shell."""

import asyncio

import docker
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["terminal"])

client = docker.from_env()


@router.websocket("/api/terminal/{session_id}")
async def terminal_ws(websocket: WebSocket, session_id: str):
    """WebSocket endpoint that bridges xterm.js to a Docker exec session."""
    await websocket.accept()

    try:
        container = client.containers.get(f"sandbox-{session_id}")
    except docker.errors.NotFound:
        await websocket.close(code=4004, reason="Container not found")
        return

    # Create an exec instance attached to the container
    exec_id = client.api.exec_create(
        container.id,
        cmd="/bin/bash",
        stdin=True,
        tty=True,
        stdout=True,
        stderr=True,
        workdir="/workspace",
    )

    sock = client.api.exec_start(exec_id["Id"], socket=True, tty=True)
    raw_sock = sock._sock  # Get the raw socket

    async def read_from_container():
        """Read output from container and send to browser."""
        loop = asyncio.get_event_loop()
        try:
            while True:
                data = await loop.run_in_executor(None, raw_sock.recv, 4096)
                if not data:
                    break
                await websocket.send_bytes(data)
        except (WebSocketDisconnect, Exception):
            pass

    async def write_to_container():
        """Read input from browser and send to container."""
        try:
            while True:
                data = await websocket.receive_bytes()
                raw_sock.sendall(data)
        except (WebSocketDisconnect, Exception):
            pass

    # Run both directions concurrently
    read_task = asyncio.create_task(read_from_container())
    write_task = asyncio.create_task(write_to_container())

    try:
        await asyncio.gather(read_task, write_task)
    except Exception:
        pass
    finally:
        read_task.cancel()
        write_task.cancel()
        raw_sock.close()
