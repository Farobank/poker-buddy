#!/usr/bin/env python3
"""Sync Poker Buddy to ElevenLabs ConvAI via API.

One-shot: creates 6 webhook tools and the agent that references them.
Prints the agent_id and saves it back to .env. Re-runnable.

Defaults to creating fresh tools and a fresh agent on every run. Old tools
and agents are left behind in the dashboard — delete them manually if you
care. For v1 this is fine because the tunnel URL rotates anyway.

Usage:
    .venv/bin/python scripts/sync_agent.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
API_BASE = "https://api.elevenlabs.io/v1"

# DESIGN.md suggestion — chill male voice. Bill can swap in the dashboard later.
DEFAULT_VOICE_ID = "TX3LPaxmHKxFdv7VOQHJ"  # Liam
DEFAULT_TTS_MODEL = "eleven_flash_v2"  # English ConvAI agents only accept turbo/flash v2 (no v2.5)
LLM_MODEL = "claude-opus-4-7"


# ---------------------------------------------------------------------------
# Tool definitions — JSON-schema bodies, in the shape the API expects.
# Headers are flat dicts (string values). Pre-tool speech is "off" so the
# LLM's own "let me check the solver, one sec" line doesn't double up.
# ---------------------------------------------------------------------------

def make_tools(backend_url: str, secret: str) -> list[dict]:
    h = {"Content-Type": "application/json", "X-Buddy-Secret": secret}

    def webhook(name, description, body_schema):
        return {
            "type": "webhook",
            "name": name,
            "description": description,
            "pre_tool_speech": "off",
            "execution_mode": "immediate",
            "response_timeout_secs": 20,
            "api_schema": {
                "url": f"{backend_url}/tools/{name}",
                "method": "POST",
                "content_type": "application/json",
                "request_headers": h,
                "request_body_schema": body_schema,
            },
        }

    return [
        webhook(
            "preflop_lookup",
            "Look up a solver-verified preflop decision. HU spots return green/yellow confidence with action, frequency, sizing, principle. 6-max spots return amber + a note telling the agent to reason from theory rather than fabricate frequencies.",
            {
                "type": "object",
                "required": ["format", "position", "hand"],
                "description": "Preflop spot to look up.",
                "properties": {
                    "format": {"type": "string", "description": "Game format. 'hu' for heads-up, '6max' for six-max.", "enum": ["hu", "6max"]},
                    "position": {"type": "string", "description": "Position acting. One of: btn, bb, sb, co, mp, utg."},
                    "hand": {"type": "string", "description": "Hand. Range notation like 'JTs' or 'AKo'; concrete cards like 'JhTh'."},
                    "stack_depth_bb": {"type": "number", "description": "Stack depth in big blinds. Defaults to 100. Omit if unknown."},
                    "action_so_far": {"type": "array", "description": "Prior action this hand. Examples: ['btn_open_2.5'], ['btn_open_2.5', 'bb_3bet_9'].", "items": {"type": "string", "description": "An action token."}},
                },
            },
        ),
        webhook(
            "postflop_lookup",
            "Look up a solver-verified flop c-bet decision for HU. Returns hand category, should-bet, frequency, sizing, principle. Six-max and HU turn/river return yellow or amber with a note for the agent to reason from theory.",
            {
                "type": "object",
                "required": ["format", "hand", "board"],
                "description": "Postflop spot to look up.",
                "properties": {
                    "format": {"type": "string", "description": "Game format.", "enum": ["hu", "6max"]},
                    "hand": {"type": "string", "description": "Concrete cards strongly preferred (suits matter for flush draws). Examples: 'JhTh', 'KhQs'."},
                    "board": {"type": "string", "description": "Board cards concatenated. Flop: 'Kh7d2c'. Turn: 'Kh7d2c4s'."},
                    "position": {"type": "string", "description": "Who is acting on this street. Usually 'btn' or 'bb' in HU."},
                    "line": {"type": "array", "description": "Action across streets, e.g. ['btn_open_2.5', 'bb_call'].", "items": {"type": "string", "description": "An action token."}},
                    "stack_depth_bb": {"type": "number", "description": "Stack depth in big blinds. Defaults to 100."},
                    "is_4bet_pot": {"type": "boolean", "description": "True if this is a 4-bet pot. Defaults to false."},
                },
            },
        ),
        webhook(
            "theory_lookup",
            "BM25 search over the curated theory corpus (concepts, opponent types, board textures, HU vs six-max, stack-depth effects). Returns top-k chunks with titles, sources, and excerpts. Use when you need conceptual grounding rather than a specific frequency lookup.",
            {
                "type": "object",
                "required": ["query"],
                "description": "Theory search query.",
                "properties": {
                    "query": {"type": "string", "description": "Natural language query — concept, board type, opponent type, situation."},
                    "k": {"type": "integer", "description": "Number of results. Defaults to 3."},
                },
            },
        ),
        webhook(
            "memory_read",
            "Read Bill's persistent state, scoped by topic. Use at session start to learn stakes/goals; use during conversation to recall opponents, recent hands, or open leaks.",
            {
                "type": "object",
                "required": ["topic"],
                "description": "Memory read request.",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Which slice of memory to read.",
                        "enum": ["profile", "recent_leaks", "opponents", "recent_hands", "session"],
                    },
                },
            },
        ),
        webhook(
            "memory_write",
            "Persist a piece of state. Use sparingly — when Bill identifies a leak, reports a new opponent, updates his stakes/goals, or wraps a session. Not every utterance is worth journaling.",
            {
                "type": "object",
                "required": ["kind", "content"],
                "description": "Memory write payload.",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "What kind of memory to write.",
                        "enum": ["hand_discussed", "leak_identified", "opponent_observation", "session_note", "profile_update"],
                    },
                    "content": {
                        "type": "object",
                        "description": "Free-form payload whose shape depends on kind. hand_discussed: {format, hand, position, board, action, takeaway, confidence}. leak_identified: {description, severity}. profile_update: {stakes, variants, study_goals}. session_note: {summary, hands_discussed, update_latest}. opponent_observation: {label, observation}.",
                        "properties": {},
                    },
                },
            },
        ),
        webhook(
            "opponent_profile_update",
            "Upsert an opponent profile. Use whenever Bill names or describes a villain. The label is HIS nickname for them (never a real online ID).",
            {
                "type": "object",
                "required": ["label", "observation"],
                "description": "Opponent profile update.",
                "properties": {
                    "label": {"type": "string", "description": "Bill's own nickname for this opponent. Never a real online ID."},
                    "observation": {"type": "string", "description": "Free-text observation. LAG/station/nit/etc. get auto-tagged by the backend."},
                },
            },
        ),
    ]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _post(api_key: str, path: str, body: dict) -> dict:
    r = requests.post(
        f"{API_BASE}{path}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    if not r.ok:
        sys.exit(f"❌ POST {path} failed: {r.status_code}\n{r.text}")
    return r.json()


def _delete(api_key: str, path: str) -> None:
    r = requests.delete(
        f"{API_BASE}{path}",
        headers={"xi-api-key": api_key},
        timeout=30,
    )
    if not r.ok and r.status_code != 404:
        print(f"⚠️  DELETE {path} returned {r.status_code} {r.text[:200]}")


def _update_env(key: str, value: str) -> None:
    """Idempotently set KEY=VALUE in .env."""
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    lines = text.split("\n")
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv(ENV_FILE)
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    secret = os.environ.get("BUDDY_SHARED_SECRET", "").strip()
    backend_url = os.environ.get("BACKEND_URL", "").strip() or \
        "https://incorporated-ceiling-launch-brochure.trycloudflare.com"

    if not api_key:
        sys.exit("❌ ELEVENLABS_API_KEY missing in .env. Get one at https://elevenlabs.io/app/settings/api-keys → Create a new key (with ConvAI Create+Edit permissions).")
    if not secret:
        sys.exit("❌ BUDDY_SHARED_SECRET missing in .env.")

    prompt_text = (PROJECT_ROOT / "system-prompt.md").read_text().strip()
    if not prompt_text:
        sys.exit("❌ system-prompt.md is empty.")

    print(f"→ Backend URL: {backend_url}")
    print(f"→ System prompt: {len(prompt_text)} chars")

    # Optional: clean up the previous run's tools if we have IDs saved.
    prev_tool_ids = os.environ.get("ELEVENLABS_TOOL_IDS", "").strip()
    if prev_tool_ids:
        print(f"→ Deleting {len(prev_tool_ids.split(','))} previously-created tools...")
        for tid in prev_tool_ids.split(","):
            tid = tid.strip()
            if tid:
                _delete(api_key, f"/convai/tools/{tid}")

    prev_agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "").strip()
    if prev_agent_id:
        print(f"→ Deleting previous agent {prev_agent_id}...")
        _delete(api_key, f"/convai/agents/{prev_agent_id}")

    # Create tools — persist IDs progressively so a failure mid-stream still
    # leaves a clean cleanup state in .env.
    tool_configs = make_tools(backend_url, secret)
    tool_ids: list[str] = []
    print(f"→ Creating {len(tool_configs)} tools...")
    for tc in tool_configs:
        resp = _post(api_key, "/convai/tools", {"tool_config": tc})
        tid = resp.get("id") or resp.get("tool_id")
        if not tid:
            _update_env("ELEVENLABS_TOOL_IDS", ",".join(tool_ids))
            sys.exit(f"❌ tool response had no id: {resp}")
        print(f"   ✓ {tc['name']} → {tid}")
        tool_ids.append(tid)
        _update_env("ELEVENLABS_TOOL_IDS", ",".join(tool_ids))

    # Create agent
    print(f"→ Creating agent...")
    agent_body = {
        "name": "Poker Buddy",
        "conversation_config": {
            "agent": {
                "first_message": "What spot you got for me?",
                "language": "en",
                "prompt": {
                    "prompt": prompt_text,
                    "llm": LLM_MODEL,
                    "tool_ids": tool_ids,
                    "reasoning_effort": "low",
                    "max_tokens": 250,
                },
            },
            "tts": {
                "voice_id": DEFAULT_VOICE_ID,
                "model_id": DEFAULT_TTS_MODEL,
            },
        },
    }
    resp = _post(api_key, "/convai/agents/create", agent_body)
    agent_id = resp.get("agent_id") or resp.get("id")
    if not agent_id:
        sys.exit(f"❌ agent response had no agent_id: {resp}")

    print(f"\n✅ Agent created: {agent_id}")

    _update_env("ELEVENLABS_AGENT_ID", agent_id)
    _update_env("ELEVENLABS_TOOL_IDS", ",".join(tool_ids))
    print(f"→ Saved ELEVENLABS_AGENT_ID + ELEVENLABS_TOOL_IDS to .env\n")

    print("Next steps:")
    print(f"  1.  ./scripts/wire-agent.sh {agent_id}")
    print(f"  2.  Open https://healing-accepted-quickly-profits.trycloudflare.com on your phone")
    print(f"  3.  Share → Add to Home Screen → tap → grant mic → talk")


if __name__ == "__main__":
    main()
