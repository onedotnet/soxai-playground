"""Preview reverse proxy — routes /preview/{session_id}/* to the container's dev server."""

import asyncio

import httpx
import websockets
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from api.session import _sessions

# Dev-server startup inside a fresh sandbox container takes a few seconds
# (npm copy + vite boot). Retry ConnectError a handful of times before
# showing the "warming up" splash, so the first preview load after session
# creation doesn't immediately 502.
_CONNECT_RETRIES = 5
_CONNECT_RETRY_DELAY_SECONDS = 0.6

router = APIRouter(prefix="/preview", tags=["preview"])

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


_DARK_STYLE = (
    "font-family:system-ui;display:flex;align-items:center;justify-content:center;"
    "height:100vh;margin:0;background:#0a0a0c;color:#e4e4e7"
)


def _allow_iframe(resp: Response) -> Response:
    """Ensure the response can be embedded in an iframe."""
    resp.headers["Content-Security-Policy"] = "frame-ancestors *"
    if "X-Frame-Options" in resp.headers:
        del resp.headers["X-Frame-Options"]
    return resp


@router.api_route("/{session_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
@router.api_route("/{session_id}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(request: Request, session_id: str, path: str = ""):
    """Reverse proxy to the sandbox container's dev server."""
    session = _sessions.get(session_id)

    if not session or session.get("status") != "active":
        return _allow_iframe(HTMLResponse(
            f"<body style='{_DARK_STYLE}'><div style='text-align:center'>"
            f"<h2>Session not found</h2>"
            f"<p>Session <code>{session_id}</code> may have expired.</p>"
            f"</div></body>",
            status_code=404,
        ))

    port = session.get("preview_port")
    target = f"http://localhost:{port}/{path}"
    if request.url.query:
        target += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    client = _get_client()
    body = await request.body()

    # Retry on any transport-level error: ConnectError (TCP refused),
    # ReadError / RemoteProtocolError (TCP accepted by docker-proxy but
    # container's server not yet bound — fires "Server disconnected"),
    # ReadTimeout, etc. This race is normal on a freshly booted sandbox.
    last_transport_error: httpx.TransportError | None = None
    for attempt in range(_CONNECT_RETRIES):
        try:
            resp = await client.request(
                method=request.method,
                url=target,
                headers=headers,
                content=body if body else None,
            )
            resp_headers = {
                k: v for k, v in resp.headers.items()
                if k.lower() not in ("transfer-encoding", "content-encoding", "x-frame-options")
            }
            resp_headers["Content-Security-Policy"] = "frame-ancestors *"

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
            )
        except httpx.TransportError as e:
            last_transport_error = e
            if attempt < _CONNECT_RETRIES - 1:
                await asyncio.sleep(_CONNECT_RETRY_DELAY_SECONDS)
                continue
            # Fall through to the warming-up splash.
            break
        except Exception as e:
            return _allow_iframe(PlainTextResponse(
                f"Preview proxy error: {type(e).__name__}",
                status_code=502,
            ))

    # All retries exhausted. Show a warming-up splash that auto-refreshes,
    # so the first preview load against a still-booting container turns
    # into a transparent wait instead of a hard 502.
    _ = last_transport_error  # keep reference for future debug logging
    return _allow_iframe(HTMLResponse(
        "<html><head><meta http-equiv='refresh' content='3'></head>"
        f"<body style='{_DARK_STYLE}'><div style='text-align:center'>"
        "<h2>Dev server warming up…</h2>"
        "<p>This usually takes a few seconds on a fresh session.</p>"
        "<p style='opacity:.6;font-size:.85em'>If this persists, start a dev server in the terminal:</p>"
        "<pre style='background:#1a1a2e;padding:16px;border-radius:8px;text-align:left;display:inline-block'>"
        "npx serve .        # static files\n"
        "npx vite           # Vite project\n"
        "npx next dev       # Next.js</pre></div></body></html>",
        status_code=503,
    ))


@router.websocket("/{session_id}/{path:path}")
async def proxy_ws(websocket: WebSocket, session_id: str, path: str):
    """Bridge preview WebSocket traffic (Vite HMR) to the sandbox container.

    Vite is configured via /workspace/vite.config.js to open its HMR
    WebSocket at wss://playground.soxai.io/preview/{SESSION_ID}/__hmr,
    and the dev server inside the container also listens at that path
    (server.hmr.path sets both sides). We accept the upgrade here,
    dial the container at ws://localhost:{preview_port}/preview/{sid}/__hmr,
    and bridge frames in both directions.
    """
    session = _sessions.get(session_id)
    if not session or session.get("status") not in ("active", "starting"):
        await websocket.close(code=4004, reason="Session not found")
        return

    port = session.get("preview_port")
    if not port:
        await websocket.close(code=4004, reason="Preview port unknown")
        return

    # Vite ships the HMR socket with subprotocol "vite-hmr". Echo back
    # whatever the client requested so the handshake succeeds.
    requested_subprotocols = websocket.scope.get("subprotocols") or []
    chosen_sub = requested_subprotocols[0] if requested_subprotocols else None

    # Reconstruct the full path the container's Vite server is listening
    # on. Since server.hmr.path uses the same /preview/{sid}/__hmr shape,
    # we forward the entire path verbatim.
    upstream_path = f"/preview/{session_id}/{path}"
    upstream_url = f"ws://localhost:{port}{upstream_path}"

    try:
        await websocket.accept(subprotocol=chosen_sub)
    except Exception:
        return

    try:
        async with websockets.connect(
            upstream_url,
            subprotocols=requested_subprotocols or None,
            open_timeout=5,
            close_timeout=2,
            max_size=None,
        ) as upstream:
            async def client_to_upstream():
                try:
                    while True:
                        msg = await websocket.receive()
                        mtype = msg.get("type")
                        if mtype == "websocket.disconnect":
                            return
                        if msg.get("bytes") is not None:
                            await upstream.send(msg["bytes"])
                        elif msg.get("text") is not None:
                            await upstream.send(msg["text"])
                except (WebSocketDisconnect, Exception):
                    return

            async def upstream_to_client():
                try:
                    async for data in upstream:
                        if isinstance(data, (bytes, bytearray)):
                            await websocket.send_bytes(bytes(data))
                        else:
                            await websocket.send_text(data)
                except Exception:
                    return

            await asyncio.wait(
                [
                    asyncio.create_task(client_to_upstream()),
                    asyncio.create_task(upstream_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
