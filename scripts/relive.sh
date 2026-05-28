#!/usr/bin/env bash
# Bring Poker Buddy back after a Mac sleep / restart — in ONE command, WITHOUT
# churning the agent.
#
# The trycloudflare tunnel URL changes every boot. Instead of re-running
# sync_agent.py (which deletes + recreates the agent → new id → frontend
# re-wire → orphans), this:
#   1. stops any stale backend + its tunnel
#   2. boots a fresh backend + tunnel (start.sh writes the new BACKEND_URL)
#   3. re-points the SAME agent's tools at the new URL, in place (update_agent.py)
#
# Result: same agent id, no frontend re-wire, no orphan agents. Just talk to it.
#
# Usage:  ./scripts/relive.sh
# Stop later:  pkill -f "uvicorn backend.main" ; pkill -f "cloudflared.*127.0.0.1:8765"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"
mkdir -p .run

PORT="$(grep -E '^BUDDY_PORT=' .env 2>/dev/null | cut -d= -f2- || true)"
PORT="${PORT:-8765}"

echo "→ stopping any running backend + its tunnel..."
pkill -f "uvicorn backend.main" 2>/dev/null || true
pkill -f "cloudflared tunnel --no-autoupdate --url http://127.0.0.1:${PORT}" 2>/dev/null || true
sleep 1

OLD_URL="$(grep -E '^BACKEND_URL=' .env 2>/dev/null | cut -d= -f2- || true)"

echo "→ booting fresh backend + tunnel (start.sh, backgrounded)..."
nohup ./scripts/start.sh > .run/relive-start.log 2>&1 &

echo "→ waiting for the new tunnel URL..."
NEW_URL=""
for _ in $(seq 1 80); do
  NEW_URL="$(grep -E '^BACKEND_URL=' .env 2>/dev/null | cut -d= -f2- || true)"
  [[ -n "$NEW_URL" && "$NEW_URL" != "$OLD_URL" ]] && break
  sleep 0.5
done
if [[ -z "$NEW_URL" || "$NEW_URL" == "$OLD_URL" ]]; then
  echo "❌ start.sh did not produce a new BACKEND_URL in time. See .run/relive-start.log"
  tail -n 20 .run/relive-start.log 2>/dev/null || true
  exit 1
fi
echo "✓ backend live at $NEW_URL"

echo "→ re-pointing the SAME agent in place (no recreate)..."
.venv/bin/python scripts/update_agent.py

cat <<EOF

✅ Poker Buddy is live again — same agent id, no re-wire, no orphans.
   Backend: $NEW_URL
   Test it in the ElevenLabs dashboard chat, or your PWA.
   Stop later:  pkill -f "uvicorn backend.main" ; pkill -f "cloudflared.*127.0.0.1:${PORT}"
EOF
