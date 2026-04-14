"""Docker container lifecycle management for sandbox sessions."""

import docker
from docker.types import Resources

from api.config import settings

client = docker.from_env()


def _build_env(api_key: str, session_id: str, tool: str, prompt: str) -> dict[str, str]:
    """Build environment variables for the sandbox container.

    Sets the correct auth vars directly so they're available to all
    processes (entrypoint, docker exec, etc.), not just PID 1.
    """
    gateway = settings.soxai_base_url
    public_host = getattr(settings, "public_host", None) or "playground.soxai.io"
    env = {
        "SESSION_ID": session_id,
        "TOOL_TYPE": tool,
        "USER_PROMPT": prompt,
        "SOXAI_API_KEY": api_key,
        "SOXAI_BASE_URL": gateway,
        # Consumed by /workspace/vite.config.js to wire HMR to the public
        # WebSocket endpoint and to configure the /soxai reverse-proxy
        # target. Changing this requires rebuilding the sandbox image
        # (vite.config.js is read at vite server boot).
        "PLAYGROUND_PUBLIC_HOST": public_host,
    }
    # DELIBERATELY NOT EXPOSED TO BROWSER: we used to set
    # VITE_SOXAI_API_KEY / VITE_SOXAI_BASE_URL here so the chat-app
    # template could call the API directly via import.meta.env. That
    # is a real user-owned API token (created by the console via POST
    # /api/tokens and only best-effort revoked on session end) and
    # putting it in import.meta.env means it lands in browser JS,
    # visible in DevTools and exfiltrable by any XSS Claude might
    # introduce. Instead, vite.config.js exposes a /soxai reverse
    # proxy that injects Authorization server-side, so the browser
    # never sees the key.

    # Always set both — Claude Code needs ANTHROPIC_*, user apps may need OPENAI_*
    env["ANTHROPIC_BASE_URL"] = gateway
    env["ANTHROPIC_AUTH_TOKEN"] = api_key
    env["ANTHROPIC_API_KEY"] = ""  # Must be empty when using AUTH_TOKEN
    env["OPENAI_API_KEY"] = api_key
    env["OPENAI_BASE_URL"] = f"{gateway}/v1"

    return env


def create_sandbox(
    session_id: str,
    api_key: str,
    preview_port: int,
    tool: str = "claude",
    prompt: str = "",
) -> str:
    """Create and start a sandbox container.

    Returns the container ID.
    """
    container = client.containers.run(
        image=settings.sandbox_image,
        name=f"sandbox-{session_id}",
        detach=True,
        stdin_open=True,
        tty=True,
        environment=_build_env(api_key, session_id, tool, prompt),
        ports={
            "3000/tcp": preview_port,  # Dev server preview
            "5173/tcp": preview_port + 1,  # Vite default
            "8080/tcp": preview_port + 2,  # Generic
        },
        mem_limit=settings.sandbox_mem_limit,
        cpu_period=100000,
        cpu_quota=int(settings.sandbox_cpu_limit * 100000),
        network_mode="bridge",
        working_dir="/workspace",
        remove=False,  # We clean up manually
    )
    return container.id


def destroy_sandbox(session_id: str):
    """Stop and remove a sandbox container."""
    try:
        container = client.containers.get(f"sandbox-{session_id}")
        container.stop(timeout=5)
        container.remove(force=True)
    except docker.errors.NotFound:
        pass


def exec_in_sandbox(session_id: str, command: str) -> str:
    """Execute a command in a running sandbox."""
    try:
        container = client.containers.get(f"sandbox-{session_id}")
        result = container.exec_run(command, demux=True)
        stdout = result.output[0].decode() if result.output[0] else ""
        return stdout
    except docker.errors.NotFound:
        return ""


def get_sandbox_status(session_id: str) -> str:
    """Get container status: running, exited, or not_found."""
    try:
        container = client.containers.get(f"sandbox-{session_id}")
        return container.status
    except docker.errors.NotFound:
        return "not_found"


def list_active_sandboxes() -> list[dict]:
    """List all running sandbox containers."""
    containers = client.containers.list(filters={"name": "sandbox-"})
    return [
        {
            "id": c.short_id,
            "name": c.name,
            "status": c.status,
            "session_id": c.name.replace("sandbox-", ""),
        }
        for c in containers
    ]
