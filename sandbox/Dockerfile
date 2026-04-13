# SoxAI Playground Sandbox Image
# Pre-installs Claude Code + Codex CLI + common dev tools.
# Each user session gets one container from this image.

FROM node:22-bookworm-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget python3 python3-pip python3-venv \
    build-essential ca-certificates jq \
    && rm -rf /var/lib/apt/lists/*

# Claude Code
RUN npm install -g @anthropic-ai/claude-code@latest 2>/dev/null || true

# Codex CLI
RUN npm install -g @openai/codex@latest 2>/dev/null || true

# Common dev tools
RUN npm install -g \
    serve \
    http-server \
    vite \
    create-vite \
    create-next-app \
    typescript \
    tsx

# Create workspace
RUN useradd -m -s /bin/bash sandbox
RUN mkdir -p /workspace && chown sandbox:sandbox /workspace

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER sandbox
WORKDIR /workspace

ENV HOME=/home/sandbox
ENV NODE_ENV=development

ENTRYPOINT ["/entrypoint.sh"]
