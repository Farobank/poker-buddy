"""preflop_lookup tool — routes to hu-poker-trainer for HU, returns honest
amber for 6-max so the agent reasons from theory instead of fabricating.

Tool contract (mirrors the JSON the ConvAI webhook receives):

    {
        "format": "hu" | "6max",
        "position": "btn" | "bb" | "co" | "mp" | "utg" | "sb",
        "hand": "JTs" | "JhTh" | ...,
        "stack_depth_bb": 100,
        "action_so_far": ["btn_open_2.5"]   # optional, list of strings
    }

Returns a dict the LLM can phrase into voice:

    {
        "data": {...} | None,
        "confidence": "green" | "yellow" | "amber",
        "source": "...",
        "note": "..."  (only present on misses / amber)
    }
"""

from __future__ import annotations

from typing import Any

from backend.engines import six_max_preflop
from backend.integrations import hu_trainer
from backend.tools.confidence import Confidence


def preflop_lookup(
    format: str,
    position: str,
    hand: str,
    stack_depth_bb: float = 100.0,
    action_so_far: list[str] | None = None,
) -> dict[str, Any]:
    """Dispatch a preflop strategy lookup."""
    fmt = format.lower().strip()
    pos = position.lower().strip()
    actions = [a.lower().strip() for a in (action_so_far or [])]

    if fmt == "hu":
        return _hu(pos, hand, stack_depth_bb, actions)
    if fmt in ("6max", "6-max", "six_max", "sixmax"):
        return _six_max(pos, hand, actions)
    return {
        "data": None,
        "confidence": Confidence.AMBER.value,
        "source": "preflop_lookup",
        "note": f"Format {format!r} not supported. Pass 'hu' or '6max'.",
    }


def _hu(
    position: str, hand: str, stack_depth_bb: float, actions: list[str]
) -> dict[str, Any]:
    """Route to the right hu-poker-trainer engine based on action_so_far + position."""
    try:
        if not actions:
            # No prior action.
            # BTN acts first preflop in HU; BB only acts after an open.
            if position in ("btn", "sb"):  # HU: the SB posts the button and acts first preflop
                return hu_trainer.preflop_btn_open(hand, stack_depth_bb)
            return {
                "data": None,
                "confidence": Confidence.AMBER.value,
                "source": "preflop_lookup (HU)",
                "note": (
                    f"In HU, BB doesn't act preflop until BTN opens. Pass "
                    f"action_so_far=['btn_open_<size>'] if BTN opened."
                ),
            }

        last = actions[-1]
        # BB facing a BTN/SB open. The agent phrases an open many ways (open /
        # raise / rfi) and in HU the SB *is* the button — accept all of them so a
        # grounded spot doesn't get mislabeled "not in my solver-verified set".
        if _is_btn_open(last) and position == "bb":
            open_size = _parse_size_from_action(last, default=2.5)
            return hu_trainer.preflop_bb_vs_open(hand, open_size, stack_depth_bb)

        # BTN/SB facing a BB 3-bet (4-bet / call / fold).
        if _is_bb_3bet(last) and position in ("btn", "sb"):
            three_bet_size = _parse_size_from_action(last, default=8.0)
            return hu_trainer.preflop_btn_vs_3bet(hand, three_bet_size, stack_depth_bb)

        # No other HU preflop branches solver-verified in v1.
        return {
            "data": None,
            "confidence": Confidence.YELLOW.value,
            "source": "preflop_lookup (HU)",
            "note": (
                f"HU spot not in solver-verified set: {position} after {actions}. "
                "Reason from BTN/BB ranges + opponent profile."
            ),
        }
    except Exception as exc:
        return {
            "data": None,
            "confidence": Confidence.AMBER.value,
            "source": "preflop_lookup (HU)",
            "note": f"Lookup failed ({type(exc).__name__}: {exc}). Reason from theory.",
        }


def _six_max(position: str, hand: str, actions: list[str]) -> dict[str, Any]:
    """Route a 6-max preflop spot to the grounded ranges engine.

    Covered (green/yellow with data): open / vs-open (call·3bet) / vs-3bet
    (4bet·call·fold) / blind defense at 100bb, from published ranges (see
    backend/engines/SIX_MAX_NOTES.md). Spots outside that set (4-bet+ wars,
    limped/multiway) decline with amber + a note rather than fabricating a line.
    """
    try:
        return six_max_preflop.lookup(position, hand, actions)
    except Exception as exc:  # never crash the webhook — degrade to honest amber
        return {
            "data": None,
            "confidence": Confidence.AMBER.value,
            "source": "preflop_lookup (6max)",
            "note": f"Lookup failed ({type(exc).__name__}: {exc}). Reason from theory.",
        }


def _parse_size_from_action(action: str, default: float) -> float:
    """'btn_open_2.5' → 2.5. Defensive parsing — fall back to default on weird input."""
    parts = action.split("_")
    if len(parts) >= 3:
        try:
            return float(parts[-1])
        except ValueError:
            pass
    return default


# Verb synonyms (exact-token match on the action's second field), mirroring
# six_max_preflop._parse_action so HU and 6-max accept the same phrasings.
_OPEN_VERBS = ("open", "opens", "raise", "raises", "rfi", "or")
_THREE_BET_VERBS = ("3bet", "3bets", "reraise", "rr")


def _is_btn_open(action: str) -> bool:
    """True for a button/SB open in any common phrasing (HU: SB == BTN)."""
    parts = action.split("_")
    return len(parts) >= 2 and parts[0] in ("btn", "sb") and parts[1] in _OPEN_VERBS


def _is_bb_3bet(action: str) -> bool:
    """True for a big-blind 3-bet in any common phrasing."""
    parts = action.split("_")
    return len(parts) >= 2 and parts[0] == "bb" and parts[1] in _THREE_BET_VERBS
