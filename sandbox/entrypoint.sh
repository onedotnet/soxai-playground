#!/bin/bash
# Sandbox container entrypoint.
# Sets up AI tool authentication using SoxAI gateway,
# then keeps the container alive for terminal access.

set -e

# Configure Claude Code to use SoxAI gateway
if [ -n "$SOXAI_API_KEY" ]; then
  export ANTHROPIC_API_KEY="$SOXAI_API_KEY"
  export ANTHROPIC_BASE_URL="${SOXAI_BASE_URL:-https://api.soxai.io}"

  # Codex CLI uses OpenAI env vars
  export OPENAI_API_KEY="$SOXAI_API_KEY"
  export OPENAI_BASE_URL="${SOXAI_BASE_URL:-https://api.soxai.io/v1}"
fi

echo "╔══════════════════════════════════════════════════╗"
echo "║  SoxAI Playground                                ║"
echo "║                                                  ║"
echo "║  Available tools:                                ║"
echo "║    claude    — Claude Code (AI coding agent)     ║"
echo "║    codex     — Codex CLI (OpenAI coding agent)   ║"
echo "║                                                  ║"
echo "║  Quick start:                                    ║"
echo "║    claude \"build a landing page\"                 ║"
echo "║                                                  ║"
echo "║  Your project will be at:                        ║"
echo "║    /workspace                                    ║"
echo "║                                                  ║"
echo "║  Preview: auto-detected when you run dev server  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Keep container alive — the terminal WebSocket attaches to this shell
exec /bin/bash
