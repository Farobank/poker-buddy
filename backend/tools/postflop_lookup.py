"""postflop_lookup — routes flop c-bet questions to hu-poker-trainer for HU,
returns honest amber for 6-max and unsupported HU streets (turn/river).

Tool contract:

    {
        "format": "hu" | "6max",
        "hand": "JhTh",           # concrete cards preferred for postflop
        "board": "Kh7d2c",
        "position": "btn" | "bb", # who is acting
        "line": ["btn_open_2.5", "bb_call"],  # action so far across streets
        "stack_depth_bb": 100,
        "is_4bet_pot": false
    }
"""

from __future__ import annotations

from typing import Any

from backend.integrations import hu_trainer
from backend.tools.confidence import Confidence


def postflop_lookup(
    format: str,
    hand: str,
    board: str,
    position: str = "btn",
    line: list[str] | None = None,
    stack_depth_bb: float = 100.0,
    is_4bet_pot: bool = False,
) -> dict[str, Any]:
    fmt = format.lower().strip()
    pos = position.lower().strip()
    line_lower = [a.lower().strip() for a in (line or [])]

    if fmt == "hu":
        return _hu(hand, board, pos, line_lower, is_4bet_pot)
    if fmt in ("6max", "6-max", "six_max", "sixmax"):
        return _six_max_amber(hand, board, pos, line_lower)
    return {
        "data": None,
        "confidence": Confidence.AMBER.value,
        "source": "postflop_lookup",
        "note": f"Format {format!r} not supported. Pass 'hu' or '6max'.",
    }


def _hu(
    hand: str,
    board: str,
    position: str,
    line: list[str],
    is_4bet_pot: bool,
) -> dict[str, Any]:
    """v1 supports flop c-bet from the preflop raiser. Other streets get yellow."""
    try:
        street = _infer_street(board)
        if street != "flop":
            return _hu_turn_river_yellow(hand, board, street)

        # Determine if this is a c-bet spot (raiser bets flop) or a check-back / probe.
        is_cbet_spot = _is_flop_cbet_spot(position, line)
        if not is_cbet_spot:
            return {
                "data": None,
                "confidence": Confidence.YELLOW.value,
                "source": "postflop_lookup (HU)",
                "note": (
                    f"{position.upper()} on flop after {line}: not the v1 c-bet "
                    "branch. Reason from board texture + range. Use "
                    "board_classification for the flop's range advantage and "
                    "default sizings."
                ),
                "board_hint": _board_only(board, is_4bet_pot),
            }

        is_ip = position == "btn"  # In HU, BTN is IP on the flop.
        return hu_trainer.cbet_for_hand(
            hand, board, is_ip=is_ip, is_4bet_pot=is_4bet_pot
        )
    except Exception as exc:
        return {
            "data": None,
            "confidence": Confidence.AMBER.value,
            "source": "postflop_lookup (HU)",
            "note": f"Lookup failed ({type(exc).__name__}: {exc}). Reason from theory.",
        }


def _hu_turn_river_yellow(hand: str, board: str, street: str) -> dict[str, Any]:
    return {
        "data": None,
        "confidence": Confidence.YELLOW.value,
        "source": "postflop_lookup (HU)",
        "note": (
            f"{street.title()} play not in solver-verified set (v1). Reason from "
            "previous-street range, equity, and opponent line. Flag the limit aloud."
        ),
    }


def _six_max_amber(
    hand: str, board: str, position: str, line: list[str]
) -> dict[str, Any]:
    return {
        "data": None,
        "confidence": Confidence.AMBER.value,
        "source": "postflop_lookup (6max)",
        "note": (
            f"No solver-verified 6-max engine yet. For {position.upper()} with "
            f"{hand} on {board}, reason from published 6-max strategy and flag "
            "verbally that this isn't directly looked up."
        ),
    }


def _board_only(board: str, is_4bet_pot: bool) -> dict[str, Any]:
    """Helper: return just the board classification (always works)."""
    return hu_trainer.board_classification(board, is_4bet_pot=is_4bet_pot)


def _infer_street(board: str) -> str:
    """A 'r' suffix or compact 'K72r' notation works too — fall back to length count."""
    cleaned = board.strip().replace(" ", "")
    # Strip a trailing 'r' or 'tt' (texture marker like K72r — rainbow).
    if cleaned and cleaned[-1].lower() == "r" and len(cleaned) % 2 == 1:
        cleaned = cleaned[:-1]
    n_cards = len(cleaned) // 2
    return {3: "flop", 4: "turn", 5: "river"}.get(n_cards, "unknown")


def _is_flop_cbet_spot(position: str, line: list[str]) -> bool:
    """True if the position to act on the flop is the preflop raiser, facing a check.

    HU heuristic: BTN raised preflop. If BB just called, BTN c-bets IP. If BB
    checks to BTN on the flop, BTN c-bets too. We treat both as c-bet spots.
    Anything more exotic (3-bet pots, donk-leads) falls to yellow.
    """
    if position != "btn":
        return False
    if not line:
        return False
    raised_preflop = any(a.startswith("btn_open") or a.startswith("btn_raise") for a in line)
    no_3bet = not any("3bet" in a for a in line)
    bb_called = any(a.startswith("bb_call") for a in line)
    return raised_preflop and no_3bet and bb_called
