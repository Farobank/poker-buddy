#!/usr/bin/env python3
"""Grade recent ConvAI conversations against the system-prompt's hard rules.

Pulls the agent's recent conversations from the ElevenLabs API, runs each
transcript through backend.grader, and prints a report — critical
(fabricated-number) violations first. This is the compounding leak-finder
NEXT.md asks for: instead of eyeballing one bad turn at a time, sweep the
week and see every spot where the buddy stated a number it didn't look up.

Usage:
    .venv/bin/python scripts/grade_transcripts.py [--limit N]
    .venv/bin/python scripts/grade_transcripts.py --conversation <id>

Exit code is 1 if any critical violation is found (usable as a gate).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.grader import grade_transcript, normalize_transcript  # noqa: E402

API_BASE = "https://api.elevenlabs.io/v1"


def _headers(api_key: str) -> dict:
    return {"xi-api-key": api_key}


def fetch_recent_conversation_ids(api_key: str, agent_id: str, limit: int) -> list[str]:
    r = requests.get(
        f"{API_BASE}/convai/conversations",
        headers=_headers(api_key),
        params={"agent_id": agent_id, "page_size": limit},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    convos = data.get("conversations") or data.get("data") or []
    ids = [c.get("conversation_id") or c.get("id") for c in convos]
    return [c for c in ids if c][:limit]


def fetch_conversation(api_key: str, conversation_id: str) -> dict:
    r = requests.get(
        f"{API_BASE}/convai/conversations/{conversation_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="How many recent conversations to grade")
    parser.add_argument("--conversation", default=None, help="Grade a single conversation by ID")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "").strip()
    if not api_key:
        sys.exit("❌ ELEVENLABS_API_KEY missing in .env")

    if args.conversation:
        ids = [args.conversation]
    elif agent_id:
        ids = fetch_recent_conversation_ids(api_key, agent_id, args.limit)
    else:
        sys.exit("❌ ELEVENLABS_AGENT_ID missing in .env (or pass --conversation <id>)")

    if not ids:
        print("No conversations found for this agent yet. Talk to the buddy, then re-run.")
        return

    total_critical = total_minor = 0
    for cid in ids:
        turns = normalize_transcript(fetch_conversation(api_key, cid))
        violations = grade_transcript(turns)
        crit = [v for v in violations if v.severity == "critical"]
        minor = [v for v in violations if v.severity == "minor"]
        total_critical += len(crit)
        total_minor += len(minor)
        status = "[FAIL]" if crit else ("[warn]" if minor else "[ok]")
        print(f"\n{status} {cid} — {len(turns)} turns, {len(crit)} critical, {len(minor)} minor")
        for v in sorted(violations, key=lambda x: (x.severity != "critical", x.turn_index)):
            snippet = v.text.strip().replace("\n", " ")
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            print(f'   [{v.severity}] turn {v.turn_index} {v.rule}: "{snippet}"')

    print(f"\n=== {len(ids)} conversations graded — {total_critical} critical, {total_minor} minor ===")
    if total_critical:
        print("Critical = a number stated without a backing solver lookup. Tighten the prompt or check the spot.")
    sys.exit(1 if total_critical else 0)


if __name__ == "__main__":
    main()
