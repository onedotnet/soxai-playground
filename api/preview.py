"""Preview reverse proxy — routes /preview/{session_id}/* to the container's dev server."""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from api.session import _sessions

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
    try:
        body = await request.body()
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
    except httpx.ConnectError:
        return _allow_iframe(HTMLResponse(
            f"<body style='{_DARK_STYLE}'><div style='text-align:center'>"
            f"<h2>No dev server running</h2>"
            f"<p>Start a dev server in your sandbox terminal:</p>"
            f"<pre style='background:#1a1a2e;padding:16px;border-radius:8px;text-align:left'>"
            f"npx serve .        # static files\n"
            f"npx vite           # Vite project\n"
            f"npx next dev       # Next.js</pre></div></body>",
            status_code=502,
        ))
    except Exception:
        return _allow_iframe(PlainTextResponse("Preview proxy error", status_code=502))
