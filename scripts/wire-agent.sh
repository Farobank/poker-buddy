#!/usr/bin/env bash
# Patch frontend/index.html with the real ElevenLabs Agent ID.
#
# Usage:
#   ./scripts/wire-agent.sh agent_4001ksqf5h84ffprxtdat1swdrt1
#
# Idempotent — if you re-run with a different ID, it swaps it again.

set -euo pipefail

if [[ $# -lt 1 || -z "$1" ]]; then
  echo "Usage: $0 <agent_id>"
  echo "Get the agent ID from the ElevenLabs ConvAI dashboard URL or agent settings."
  exit 1
fi

AGENT_ID="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INDEX="$PROJECT_ROOT/frontend/index.html"

if [[ ! -f "$INDEX" ]]; then
  echo "❌ frontend/index.html not found at $INDEX"
  exit 1
fi

# Sanity-check the ID looks like an ElevenLabs agent ID (alphanumeric + underscore).
if ! [[ "$AGENT_ID" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "❌ Agent ID has weird characters: $AGENT_ID"
  echo "   Expected alphanumeric + underscores + dashes only."
  exit 1
fi

# Use python for cross-platform safe replace (macOS sed -i syntax is fiddly).
python3 - <<PY
from pathlib import Path
p = Path("$INDEX")
src = p.read_text()

old_placeholder = 'agent-id="REPLACE_WITH_YOUR_AGENT_ID"'
new = 'agent-id="$AGENT_ID"'

if old_placeholder in src:
    out = src.replace(old_placeholder, new)
    p.write_text(out)
    print(f"✓ Replaced placeholder → {new}")
else:
    # Already wired with some agent ID — swap it.
    import re
    pattern = r'agent-id="[^"]*"'
    if re.search(pattern, src):
        out = re.sub(pattern, new, src, count=1)
        p.write_text(out)
        print(f"✓ Swapped existing agent-id → {new}")
    else:
        raise SystemExit(f"❌ Could not find agent-id attribute in {p}")
PY

echo ""
echo "Done. Reload the PWA on your phone (or refresh in Safari) to pick up the new ID."
