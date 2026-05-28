#!/usr/bin/env python3
"""Update the existing Poker Buddy agent IN PLACE — no delete/recreate.

Refreshes the system prompt and re-points the agent's tools at the current
BACKEND_URL, keeping the SAME agent id. That means the frontend never needs
re-wiring and no orphan agents pile up — unlike sync_agent.py, which deletes
and recreates. scripts/relive.sh calls this after a restart so an ephemeral
tunnel URL stops churning the agent.

Reads ELEVENLABS_API_KEY / ELEVENLABS_AGENT_ID / BACKEND_URL /
BUDDY_SHARED_SECRET from .env and system-prompt.md from disk.

Every PATCH is verified with a GET afterward — if a change doesn't land
(e.g. it went to a draft/branch that isn't live), the script fails loudly
rather than silently leaving the agent stale.

Usage:
    .venv/bin/python scripts/update_agent.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
API_BASE = "https://api.elevenlabs.io/v1"


def _headers(api_key: str) -> dict:
    return {"xi-api-key": api_key, "Content-Type": "application/json"}


def _get(api_key: str, path: str) -> dict:
    r = requests.get(f"{API_BASE}{path}", headers=_headers(api_key), timeout=30)
    if not r.ok:
        sys.exit(f"❌ GET {path} -> {r.status_code}\n{r.text[:300]}")
    return r.json()


def _patch(api_key: str, path: str, body: dict) -> dict:
    r = requests.patch(f"{API_BASE}{path}", headers=_headers(api_key), json=body, timeout=30)
    if not r.ok:
        sys.exit(f"❌ PATCH {path} -> {r.status_code}\n{r.text[:300]}")
    return r.json()


def tool_url(backend_url: str, tool_name: str) -> str:
    """The webhook URL for a tool = BACKEND_URL + /tools/<name>."""
    return f"{backend_url.rstrip('/')}/tools/{tool_name}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing.")
    args = ap.parse_args()

    load_dotenv(ENV_FILE)
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "").strip()
    backend_url = os.environ.get("BACKEND_URL", "").strip().rstrip("/")
    secret = os.environ.get("BUDDY_SHARED_SECRET", "").strip()
    for name, val in [("ELEVENLABS_API_KEY", api_key), ("ELEVENLABS_AGENT_ID", agent_id),
                      ("BACKEND_URL", backend_url), ("BUDDY_SHARED_SECRET", secret)]:
        if not val:
            sys.exit(f"❌ {name} missing in .env. Run ./scripts/start.sh (sets BACKEND_URL) and check .env.")
    prompt_text = (PROJECT_ROOT / "system-prompt.md").read_text().strip()
    if not prompt_text:
        sys.exit("❌ system-prompt.md is empty.")

    agent = _get(api_key, f"/convai/agents/{agent_id}")
    tool_ids = agent["conversation_config"]["agent"]["prompt"].get("tool_ids") or []
    print(f"→ Agent {agent_id} ({agent.get('name')}) — {len(tool_ids)} tools")
    print(f"→ Backend: {backend_url}")
    print(f"→ Prompt:  {len(prompt_text)} chars")

    if args.dry_run:
        for tid in tool_ids:
            tc = _get(api_key, f"/convai/tools/{tid}")["tool_config"]
            print(f"   would set {tc['name']:<24} -> {tool_url(backend_url, tc['name'])}")
        print("DRY RUN — no writes made.")
        return

    # 1. Re-point each tool's URL + refresh the shared secret.
    for tid in tool_ids:
        tc = _get(api_key, f"/convai/tools/{tid}")["tool_config"]
        name = tc["name"]
        want = tool_url(backend_url, name)
        tc["api_schema"]["url"] = want
        tc["api_schema"].setdefault("request_headers", {})["X-Buddy-Secret"] = secret
        _patch(api_key, f"/convai/tools/{tid}", {"tool_config": tc})
        got = _get(api_key, f"/convai/tools/{tid}")["tool_config"]["api_schema"]["url"]
        print(f"   {'✓' if got == want else '✗'} {name:<24} -> {got}")
        if got != want:
            sys.exit(f"❌ tool {name} URL did not update (got {got}). Aborting.")

    # 2. Refresh the system prompt (partial PATCH — relies on deep merge).
    _patch(api_key, f"/convai/agents/{agent_id}",
           {"conversation_config": {"agent": {"prompt": {"prompt": prompt_text}}}})

    # 3. Verify the agent change landed AND nothing else was clobbered.
    after = _get(api_key, f"/convai/agents/{agent_id}")
    cc = after["conversation_config"]
    apr = cc["agent"]["prompt"]
    voice = (cc.get("tts") or {}).get("voice_id")
    prompt_ok = apr.get("prompt", "").strip() == prompt_text
    tools_ok = len(apr.get("tool_ids") or []) == len(tool_ids)
    print(f"   {'✓' if prompt_ok else '✗'} prompt updated ({len(apr.get('prompt', ''))} chars)")
    print(f"   {'✓' if tools_ok else '✗'} tools preserved ({len(apr.get('tool_ids') or [])}) · voice {voice}")
    if not (prompt_ok and tools_ok):
        sys.exit("❌ Agent PATCH did not land cleanly (draft/branch model?). "
                 "Falling back to sync_agent.py is safe. Investigate before relying on update_agent.py.")

    print(f"\n✅ Updated agent {agent_id} in place — same id, no re-wire, no orphans.")


if __name__ == "__main__":
    main()
