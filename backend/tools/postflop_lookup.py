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

        # A flop read is suit-dependent (texture, flush draws). Compact/texture-only
        # notation (e.g. "T98tt", "K72r") can't be read cleanly — ask for the cards
        # rather than silently misreading them.
        if not _board_is_concrete(board):
            return {
                "data": None,
                "confidence": Confidence.YELLOW.value,
                "source": "postflop_lookup (HU)",
                "note": (
                    "Give me the exact flop cards (like 'T h 9 h 8 c') — the read "
                    "depends on the suits, so I can't pull it from shorthand."
                ),
            }

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

        # An impossible holding (a hole card duplicating a board card) means the
        # suits were assumed from range notation — decline, don't score a phantom.
        collision = _hu_card_collision(hand, board)
        if collision is not None:
            return collision

        is_ip = position in ("btn", "sb")  # In HU the BTN/SB is IP on the flop.
        result = hu_trainer.cbet_for_hand(
            hand, board, is_ip=is_ip, is_4bet_pot=is_4bet_pot
        )
        return _flag_suit_assumption(result, hand, board)
    except Exception as exc:
        return {
            "data": None,
            "confidence": Confidence.AMBER.value,
            "source": "postflop_lookup (HU)",
            "note": f"Lookup failed ({type(exc).__name__}: {exc}). Reason from theory.",
        }


_SUIT_CHARS = set("cdhs")
_RANKS = set("23456789TJQKA")


def _suits_explicit(hand: str) -> bool:
    """True only when the hand gives concrete suits (e.g. 'JhTh'), not range
    notation ('JTs') that the trainer would force onto assumed suits."""
    s = hand.strip().replace("10", "T").replace(" ", "")
    return len(s) == 4 and s[1].lower() in _SUIT_CHARS and s[3].lower() in _SUIT_CHARS


def _board_is_concrete(board: str) -> bool:
    """True when the board is rank+suit pairs (e.g. 'Kh7d2c'), not shorthand."""
    s = board.strip().replace("10", "T").replace(" ", "")
    if len(s) < 6 or len(s) % 2 != 0:
        return False
    return all(s[i].upper() in _RANKS and s[i + 1].lower() in _SUIT_CHARS
               for i in range(0, len(s), 2))


def _board_has_flush_texture(board: str) -> bool:
    """True when two or more board cards share a suit (a flush is possible)."""
    s = board.strip().replace("10", "T").replace(" ", "")
    suits = [s[i + 1].lower() for i in range(0, len(s), 2) if i + 1 < len(s)]
    return any(suits.count(x) >= 2 for x in set(suits))


def _hu_card_collision(hand: str, board: str) -> dict[str, Any] | None:
    """If the (possibly suit-assumed) hole cards overlap the board, the holding is
    physically impossible — return an honest decline instead of a phantom read."""
    try:
        c1, c2 = hu_trainer.cards_from_notation(hand)
        board_cards = set(hu_trainer.parse_board(board))
    except Exception:
        return None  # malformed/compact — let the outer handler degrade
    if {c1, c2} & board_cards:
        return {
            "data": None,
            "confidence": Confidence.AMBER.value,
            "source": "postflop_lookup (HU)",
            "note": (
                "Those exact cards overlap the board — looks like the suits got "
                "assumed from shorthand. Tell me your real suits and I'll read it cleanly."
            ),
        }
    return None


def _flag_suit_assumption(result: dict[str, Any], hand: str, board: str) -> dict[str, Any]:
    """When suits were assumed (range notation) AND the board can make a flush, the
    flush dimension of the read is a guess. A *draw* read is then probably for a
    flush the player doesn't hold — drop it to amber and ask for the suits. A made
    hand is still fine to state, but flag the assumption so the buddy can confirm."""
    if _suits_explicit(hand) or not _board_has_flush_texture(board):
        return result
    category = (result.get("data") or {}).get("hand_category")
    if category in ("strong_draw", "weak_draw"):
        return {
            "data": None,
            "confidence": Confidence.AMBER.value,
            "source": "postflop_lookup (HU)",
            "note": (
                "That draw read only holds if you've got two of the board's suit — "
                "from shorthand I'm guessing your suits, and on this board you'd flop "
                "that draw only about one in four times. What are your exact cards?"
            ),
        }
    result["assumption"] = (
        "Suits assumed from shorthand — the made-hand read holds, but confirm the "
        "exact cards if a flush matters here."
    )
    return result


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
    """Count cards across concrete ('Kh7d2c') and shorthand ('T98tt', 'K72r',
    'T98') notation. Texture markers (tt=two-tone, m=monotone, r=rainbow) are
    stripped first; compact rank-only boards count one char per card."""
    cleaned = board.strip().replace(" ", "").replace("10", "T")
    low = cleaned.lower()
    for suffix in ("tt", "m", "r"):  # texture markers, not card data
        if low.endswith(suffix) and (len(cleaned) - len(suffix)) in (3, 4, 5):
            cleaned = cleaned[: -len(suffix)]
            break
    if cleaned and all(c.upper() in _RANKS for c in cleaned):
        n_cards = len(cleaned)          # rank-only shorthand: one char per card
    else:
        n_cards = len(cleaned) // 2     # concrete: rank+suit pairs
    return {3: "flop", 4: "turn", 5: "river"}.get(n_cards, "unknown")


def _is_flop_cbet_spot(position: str, line: list[str]) -> bool:
    """True if the in-position player (BTN/SB) is the preflop raiser c-betting a
    single-raised pot.

    In HU at 100bb the BTN/SB raises ~80-100% preflop and essentially never limps,
    so absent an explicit 3-bet it IS the preflop raiser by default. A flop line of
    just "BB checks to me" (``bb_check``) or a single-raised ``bb_call`` both land
    in the c-bet branch — the player needn't restate the preflop open every turn.
    3-bet pots and donk-leads fall through to yellow.
    """
    if position not in ("btn", "sb"):
        return False
    if not line:
        return False
    no_3bet = not any("3bet" in a for a in line)
    bb_passive = any(a.startswith("bb_call") or a.startswith("bb_check") for a in line)
    return no_3bet and bb_passive
