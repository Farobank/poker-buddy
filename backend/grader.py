"""Transcript grader — flags system-prompt rule violations in ConvAI conversations.

The compounding leak-finder from NEXT.md. Above all it enforces the trust rule:
never state a GTO frequency / sizing / percentage without a backing solver
lookup. It also flags two voice-formatting slips: over-length turns and
digit-form numbers that should be spoken spelled-out.

`grade_transcript` is pure — it operates on normalized turns, each carrying a
`grounded` flag (did a preflop/postflop lookup return a real number this turn,
carried across consecutive agent turns since the last user message).
`normalize_transcript` maps the ElevenLabs ConvAI API shape into that contract.
The network fetch + CLI live in scripts/grade_transcripts.py.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# A percentage claim: digit-% / digit-percent, or the bare word "percent".
# Spelled-out frequencies ("sixty percent") are the sneaky case the prompt's
# spell-out rule actually encourages, so we key on the word itself.
_PERCENT = re.compile(r"\b\d{1,3}\s*%|\bpercent\b", re.I)

# Explicit pot-fraction sizings.
_SIZING = re.compile(
    r"\b(half[\s-]?pot|third[\s-]?pot|quarter[\s-]?pot|full[\s-]?pot|"
    r"two[\s-]thirds|three[\s-]quarters|over[\s-]?bet|pot[\s-]?sized?)\b",
    re.I,
)

# Digit-form percentage only — a voice-formatting violation regardless of
# grounding (the agent must SPEAK it spelled-out).
_DIGIT_PERCENT = re.compile(r"\b\d{1,3}\s*%|\b\d{1,3}\s*percent\b", re.I)

_MAX_WORDS = 60
_LOOKUP_TOOLS = {"preflop_lookup", "postflop_lookup"}


@dataclass
class Violation:
    turn_index: int
    rule: str        # fabricated_number | unspelled | over_length
    severity: str    # critical | minor
    text: str


def _has_number_claim(text: str) -> bool:
    return bool(_PERCENT.search(text) or _SIZING.search(text))


def grade_transcript(turns: list[dict]) -> list[Violation]:
    """Flag rule violations across normalized agent turns."""
    violations: list[Violation] = []
    for i, turn in enumerate(turns):
        if turn.get("role") != "agent":
            continue
        text = turn.get("text", "") or ""
        grounded = bool(turn.get("grounded"))

        if _has_number_claim(text) and not grounded:
            violations.append(Violation(i, "fabricated_number", "critical", text))

        if _DIGIT_PERCENT.search(text):
            violations.append(Violation(i, "unspelled", "minor", text))

        if len(text.split()) > _MAX_WORDS:
            violations.append(Violation(i, "over_length", "minor", text))

    return violations


def _parse_result(payload) -> tuple[str, object]:
    """Extract (confidence, data) from a tool-result payload (JSON string or dict)."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return "", None
    if isinstance(payload, dict):
        return str(payload.get("confidence", "")).lower(), payload.get("data")
    return "", None


def _lookup_returned_number(entry: dict) -> bool:
    """True only if a preflop/postflop lookup in this entry returned an actual
    number — green/yellow confidence AND non-null data. A yellow-but-dataless
    response (HU turn/river, HU flop non-c-bet) carries no frequency, so it must
    NOT ground a stated number — that's exactly where the buddy is prone to make
    a number up."""
    for r in entry.get("tool_results") or []:
        name = r.get("tool_name") or r.get("name") or ""
        if name not in _LOOKUP_TOOLS:
            continue
        conf, data = _parse_result(r.get("result_value", r.get("result", "")))
        if conf in ("green", "yellow") and data is not None:
            return True
    return False


def normalize_transcript(raw: dict) -> list[dict]:
    """Map the ElevenLabs ConvAI conversation shape into graded turns.

    Grounding is sticky across consecutive agent turns (the agent often calls
    the tool in one turn and reports the number in the next) and resets on each
    user turn (a new spot needs a fresh lookup).
    """
    turns: list[dict] = []
    carried_grounded = False
    for entry in raw.get("transcript", []) or []:
        role = entry.get("role", "")
        text = entry.get("message") or entry.get("text") or ""
        if role == "user":
            carried_grounded = False
            turns.append({"role": "user", "text": text, "grounded": False})
            continue
        carried_grounded = carried_grounded or _lookup_returned_number(entry)
        turns.append({"role": "agent", "text": text, "grounded": carried_grounded})
    return turns
