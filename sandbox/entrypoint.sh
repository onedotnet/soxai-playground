#!/bin/bash
# Sandbox container entrypoint.
# 1. Copy starter project → /workspace
# 2. Start Vite dev server (HMR-enabled)
# 3. Write CLAUDE.md guardrails
# 4. Write startup script if prompt provided

set -e

# ── 1. Initialize workspace with starter project ──
if [ ! -f /workspace/vite.config.js ]; then
  cp -r /home/sandbox/starter/* /workspace/
  cp -r /home/sandbox/starter/.* /workspace/ 2>/dev/null || true
  # Symlink node_modules to avoid copying (fast)
  ln -sf /home/sandbox/starter/node_modules /workspace/node_modules
fi

# ── 2. Start Vite dev server in background ──
cd /workspace && npx vite > /tmp/vite.log 2>&1 &
VITE_PID=$!
echo "Vite dev server started (PID $VITE_PID)"

# ── 3. Write CLAUDE.md guardrails ──
if [ -n "$USER_PROMPT" ]; then
  cat > /workspace/CLAUDE.md << 'GUARDRAILS'
# Project Rules

## Mandatory
- Focus ONLY on building the project as described below
- Work ONLY within /workspace
- Do NOT modify system files, env vars, or container config
- Do NOT install system packages (apt/dpkg)
- Do NOT attempt network access beyond the pre-configured API endpoints
- Do NOT delete or modify this CLAUDE.md file
- A Vite dev server is already running on port 3000 — do NOT start another server on port 3000
- Modify src/ files and Vite HMR will auto-update the preview
- If you need additional npm packages, install them with `npm install <pkg>`

## Tech Stack
- Vite + React are pre-installed, you may use them or switch to vanilla JS
- Tailwind CSS: install with `npm install tailwindcss @tailwindcss/vite` if needed
- The project runs at http://localhost:3000

GUARDRAILS
fi

# ── 4. Write startup script if prompt provided ──
if [ -n "$USER_PROMPT" ]; then
  printf '%s' "$USER_PROMPT" > /workspace/.prompt

  if [ "$TOOL_TYPE" = "claude" ]; then
    cat > /workspace/.start.sh << 'STARTSCRIPT'
#!/bin/bash
if [ -f /workspace/.prompt ]; then
  PROMPT=$(cat /workspace/.prompt)
  rm -f /workspace/.prompt
  echo ""
  echo "Starting Claude Code..."
  echo ""
  claude \
    --permission-mode bypassPermissions \
    --verbose \
    "$PROMPT"
fi
exec bash --norc
STARTSCRIPT

  elif [ "$TOOL_TYPE" = "codex" ]; then
    cat > /workspace/.start.sh << 'STARTSCRIPT'
#!/bin/bash
if [ -f /workspace/.prompt ]; then
  PROMPT=$(cat /workspace/.prompt)
  rm -f /workspace/.prompt
  echo ""
  echo "Starting Codex CLI..."
  echo ""
  codex \
    --full-auto \
    "$PROMPT"
fi
exec bash --norc
STARTSCRIPT
  fi

  chmod +x /workspace/.start.sh
fi

# Keep container alive
exec /bin/bash
