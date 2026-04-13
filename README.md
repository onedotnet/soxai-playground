# SoxAI Playground

Build web apps with AI coding tools in your browser. No install required.

![License](https://img.shields.io/badge/license-MIT-blue)

## What is this?

A browser-based sandbox where you can use **Claude Code** and **Codex CLI** to build web applications — without installing anything on your computer. Just open a browser, start talking to the AI, and watch it build your project in real time.

When your project is ready, it's instantly live at a preview URL you can share.

## How it works

1. **Login** with your [SoxAI](https://console.soxai.io) account
2. **Choose** your AI tool (Claude Code or Codex CLI)
3. **Build** — tell the AI what you want in plain English
4. **Preview** — your project is live at `{session}.play.soxai.io`

Each session runs in an isolated Docker container with:
- Claude Code + Codex CLI pre-installed
- Node.js 22 + Python 3.12
- Your SoxAI API key auto-configured
- 30-minute session with live preview

## Architecture

```
Browser (xterm.js)    Preview (iframe)
       ↓ WebSocket         ↓ HTTPS
   API Server ←→ Docker Container
       ↓                  ├── Claude Code / Codex CLI
   Queue (Redis)          ├── /workspace
                          └── Dev server → {id}.play.soxai.io
```

## Self-hosting

### Prerequisites

- Docker + Docker Compose
- Node.js 22+
- Python 3.12+
- Redis

### Quick start

```bash
# Build the sandbox image
docker build -t soxai-playground-sandbox sandbox/

# Start infrastructure
docker compose up -d

# Install API deps
cd api && pip install -e ".[dev]"

# Start API
uvicorn api.main:app --port 8100

# Start frontend (separate terminal)
cd web && bun install && bun run dev --port 3020
```

### Configuration

Copy `.env.example` to `.env` and configure:

```env
PLAYGROUND_MAX_SESSIONS=5
PLAYGROUND_SESSION_TIMEOUT_MINUTES=30
PLAYGROUND_IDLE_TIMEOUT_MINUTES=10
PLAYGROUND_PREVIEW_DOMAIN=play.soxai.io
PLAYGROUND_SOXAI_BASE_URL=https://api.soxai.io
```

### Preview domain setup

For the `{id}.play.soxai.io` subdomain preview to work:

1. Add a wildcard DNS record: `*.play.soxai.io → your server IP`
2. Get a wildcard SSL cert (Cloudflare provides this free)
3. Configure Nginx to proxy `*.play.soxai.io` to the correct container port

See `nginx/playground.conf` for the Nginx config.

## Limits

| Resource | Limit |
|----------|-------|
| Concurrent sessions | 5 (configurable) |
| Session duration | 30 minutes |
| Idle timeout | 10 minutes |
| CPU per session | 1 core |
| RAM per session | 1 GB |

## Contributing

Contributions welcome! Please open an issue first to discuss what you'd like to change.

## License

MIT
