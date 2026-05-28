#!/usr/bin/env bash
# Poker Buddy — local launcher.
#
# Boots the FastAPI backend on $BUDDY_PORT and a Cloudflare Quick Tunnel
# pointing at it. Prints the public URL you paste into agent-config.json
# (replace {BACKEND_URL}) before pasting into the ElevenLabs ConvAI dashboard.
#
# Usage:
#   ./scripts/start.sh
#
# Stop with Ctrl-C — both backend and tunnel are killed together.

set -euo pipefail

# --- locate project root regardless of where you call this from -------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# --- env --------------------------------------------------------------------
if [[ ! -f .env ]]; then
  echo "❌ .env missing. Run: cp .env.example .env  and fill it in."
  exit 1
fi
# shellcheck disable=SC1091
set -a; source .env; set +a

PORT="${BUDDY_PORT:-8765}"
LOG_DIR="$PROJECT_ROOT/.run"
mkdir -p "$LOG_DIR"
BACKEND_LOG="$LOG_DIR/backend.log"
TUNNEL_LOG="$LOG_DIR/tunnel.log"

# --- prereqs ----------------------------------------------------------------
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "❌ cloudflared not found. Install:  brew install cloudflared"
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "❌ uv not found. Install:  brew install uv"
  exit 1
fi

# --- cleanup on exit --------------------------------------------------------
BACKEND_PID=""
TUNNEL_PID=""
cleanup() {
  echo ""
  echo "→ shutting down..."
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$TUNNEL_PID"  ]] && kill "$TUNNEL_PID"  2>/dev/null || true
  wait 2>/dev/null || true
  echo "✓ done."
}
trap cleanup EXIT INT TERM

# --- boot backend -----------------------------------------------------------
echo "→ starting backend on http://127.0.0.1:$PORT"
: > "$BACKEND_LOG"
uv run uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" \
  >> "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

# wait for /health to respond (up to 20s)
for i in {1..40}; do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "✓ backend healthy"
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "❌ backend crashed. Last lines of $BACKEND_LOG:"
    tail -n 30 "$BACKEND_LOG"
    exit 1
  fi
  sleep 0.5
done

# --- boot tunnel ------------------------------------------------------------
echo "→ starting Cloudflare Quick Tunnel"
: > "$TUNNEL_LOG"
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" \
  >> "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

# parse the trycloudflare.com URL out of the tunnel log (up to 30s)
PUBLIC_URL=""
for i in {1..60}; do
  PUBLIC_URL=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -n1 || true)
  if [[ -n "$PUBLIC_URL" ]]; then break; fi
  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "❌ tunnel crashed. Last lines of $TUNNEL_LOG:"
    tail -n 30 "$TUNNEL_LOG"
    exit 1
  fi
  sleep 0.5
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "❌ tunnel did not produce a URL in 30s. See $TUNNEL_LOG."
  exit 1
fi

# --- ready ------------------------------------------------------------------
cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║  Poker Buddy is up.                                              ║
╠══════════════════════════════════════════════════════════════════╣
║  Backend:  http://127.0.0.1:$PORT
║  Public:   $PUBLIC_URL
╚══════════════════════════════════════════════════════════════════╝

Paste $PUBLIC_URL into agent-config.json everywhere it says {BACKEND_URL},
then paste agent-config.json into the ElevenLabs ConvAI dashboard.

Logs:
  $BACKEND_LOG
  $TUNNEL_LOG

Ctrl-C to stop.

EOF

# block until either child dies (Ctrl-C falls through the trap).
# Poll instead of `wait -n` because macOS ships bash 3.2 which doesn't have it.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$TUNNEL_PID" 2>/dev/null; do
  sleep 2
done
