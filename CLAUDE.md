# CLAUDE.md

## Project: SoxAI Playground

Browser-based AI coding sandbox. Users run Claude Code / Codex CLI in Docker containers, build web projects, and preview them live via subdomain proxy.

## Commit Rules (MANDATORY)

- **NO `Co-Authored-By: Claude` in any commit message.** This is an open-source project. All commits must appear as human-authored.
- Commit messages follow conventional commits: `feat:`, `fix:`, `docs:`, `chore:`
- Keep messages concise and technical

## Architecture

```
Browser (xterm.js + WebSocket)
    ↓
API Server (FastAPI)
    ├── Session Manager (max 5 concurrent, queue overflow)
    ├── Docker API (create/destroy containers)
    └── Reverse Proxy Config (Nginx/Caddy)
        ↓
Docker Container (per user session)
    ├── Claude Code + Codex CLI pre-installed
    ├── Node.js 22 + Python 3.12
    ├── User's SoxAI API key as env var
    ├── /workspace (project files)
    └── Dev server on :3000 → proxied to {id}.play.soxai.io
```

## Key Constraints

- Max 5 concurrent sessions (single server)
- Users must have SoxAI account (provides API key + $5 credit)
- Web projects only (served via reverse proxy, no download needed)
- Session timeout: 30 min max, 10 min idle
- Preview via subdomain: `{session_id}.play.soxai.io`

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API Server | Python, FastAPI |
| WebSocket Terminal | xterm.js + WebSocket |
| Container Management | Docker SDK for Python |
| Queue | Redis |
| Reverse Proxy | Nginx (dynamic upstream) |
| Frontend | Next.js 15, shadcn/ui |
| Base Container Image | Custom Dockerfile with Claude Code + Codex CLI |

## Directory Structure

```
soxai-playground/
├── api/                  # FastAPI backend
│   ├── main.py
│   ├── session.py        # Session lifecycle management
│   ├── docker_manager.py # Container create/destroy
│   ├── terminal.py       # WebSocket terminal handler
│   ├── queue.py          # Queue management
│   └── proxy.py          # Dynamic reverse proxy config
├── sandbox/              # Docker sandbox image
│   ├── Dockerfile        # Base image with AI tools
│   └── entrypoint.sh     # Container startup script
├── web/                  # Next.js frontend
│   └── src/app/
│       ├── page.tsx      # Landing / queue page
│       └── session/
│           └── [id]/
│               └── page.tsx  # Terminal + preview split view
├── nginx/                # Reverse proxy config
│   └── playground.conf
├── docker-compose.yml    # Dev environment
├── CLAUDE.md
└── README.md
```

## Development

```bash
# Start infrastructure
docker compose up -d

# API server
cd api && pip install -e ".[dev]" && uvicorn main:app --port 8100

# Frontend
cd web && bun install && bun run dev --port 3020
```
