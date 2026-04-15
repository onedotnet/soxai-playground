# SoxAI Playground Sandbox Image
# Pre-installs Claude Code + Codex CLI + common dev tools.
# Each user session gets one container from this image.

FROM node:22-bookworm-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget python3 python3-pip python3-venv \
    build-essential ca-certificates jq procps \
    && rm -rf /var/lib/apt/lists/*

# Claude Code
RUN npm install -g @anthropic-ai/claude-code@latest

# Codex CLI
RUN npm install -g @openai/codex@latest

# Common dev tools
RUN npm install -g \
    serve \
    http-server \
    typescript \
    tsx

# Create user and workspace
RUN useradd -m -s /bin/bash sandbox
RUN mkdir -p /workspace && chown sandbox:sandbox /workspace

# Pre-build a minimal Vite starter project (for instant dev server)
USER sandbox
RUN mkdir -p /home/sandbox/starter && cd /home/sandbox/starter && \
    npm init -y > /dev/null 2>&1 && \
    npm install vite @vitejs/plugin-react react react-dom three > /dev/null 2>&1

# Starter files — "Building..." placeholder
COPY --chown=sandbox:sandbox starter/ /home/sandbox/starter/

# Entrypoint
USER root
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER sandbox
WORKDIR /workspace

ENV HOME=/home/sandbox
ENV NODE_ENV=development

ENTRYPOINT ["/entrypoint.sh"]
