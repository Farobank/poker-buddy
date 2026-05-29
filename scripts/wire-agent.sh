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
import re
from pathlib import Path
p = Path("$INDEX")
src = p.read_text()

# The frontend holds the agent id in a JS constant: const AGENT_ID = "agent_...";
pattern = r'const AGENT_ID = "[^"]*";'
new = 'const AGENT_ID = "$AGENT_ID";'

if re.search(pattern, src):
    out = re.sub(pattern, new, src, count=1)
    p.write_text(out)
    print(f"✓ Set AGENT_ID → $AGENT_ID")
else:
    raise SystemExit(f"❌ Could not find 'const AGENT_ID = \"...\";' in {p}")
PY

echo ""
echo "Done. Reload the PWA on your phone (or refresh in Safari) to pick up the new ID."
