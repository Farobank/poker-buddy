"""Shim around ~/hu-poker-trainer.

We import the trainer's engines as a library at module load. The trainer
exposes preflop / postflop / board engines that have been solver-verified
against GTO Wizard, Upswing, and 20+ sources (see
~/hu-poker-trainer/STRATEGY_NOTES.md). We trust them for HU spots.

Return shape is normalized — every helper returns a dict with `data`,
`confidence` (mapped to our Confidence enum), and `source`.

Path handling: we read HU_TRAINER_PATH from env (default ~/hu-poker-trainer)
and sys.path-insert it lazily. This avoids polluting site-packages with
the trainer's "src" package name.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from backend.tools.confidence import Confidence

_HU_TRAINER_PATH = os.environ.get(
    "HU_TRAINER_PATH",
    str(Path.home() / "hu-poker-trainer"),
)


def _ensure_path() -> None:
    if _HU_TRAINER_PATH not in sys.path:
        sys.path.insert(0, _HU_TRAINER_PATH)


_ensure_path()

# Imports happen after sys.path adjustment.
# These will raise ImportError if HU_TRAINER_PATH is wrong — surface early.
from src import preflop as _preflop  # noqa: E402
from src import postflop as _postflop  # noqa: E402
from src import board as _board  # noqa: E402
from src.cards import Card, Rank, Suit, parse_board  # noqa: E402


_CANONICAL_SUITS = (Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS)


def _confidence_from_emoji(tag: str) -> Confidence:
    """The trainer uses emoji strings; we use our enum.

    🟢 Verified            → GREEN
    🟡 Likely correct      → YELLOW
    🟠 Estimated           → AMBER
    Anything else          → AMBER (the safe default — flag it).
    """
    if not tag:
        return Confidence.AMBER
    if tag.startswith("🟢"):
        return Confidence.GREEN
    if tag.startswith("🟡"):
        return Confidence.YELLOW
    return Confidence.AMBER


def _rank_from_char(ch: str) -> Rank:
    """'A' → ACE, 'K' → KING, 'T' → TEN, '2' → DEUCE, …"""
    mapping = {
        "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
        "9": 9, "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
    }
    return Rank(mapping[ch.upper()])


_SUIT_CHARS = {"c", "d", "h", "s"}


def cards_from_notation(notation: str) -> tuple[Card, Card]:
    """Resolve a hand string to two concrete Cards.

    Accepts both:
      Range notation:  'AA', 'JTs', 'AKo'  (suits chosen canonically)
      Concrete cards:  'AhAs', 'JhTh', 'AhKs' (suits exact)

    For range notation suits are canonical (heart-spade or heart-heart) since
    HU preflop ranges are suit-invariant. For postflop calls the buddy MUST
    pass concrete cards — flush-draw classification depends on suit.
    """
    s = notation.strip().replace("10", "T").replace(" ", "")

    # Concrete cards: 4 chars and char[1], char[3] are suit chars.
    if len(s) == 4 and s[1].lower() in _SUIT_CHARS and s[3].lower() in _SUIT_CHARS:
        return Card.parse(s[:2]), Card.parse(s[2:])

    # Pocket pair (e.g. "AA"): same rank, no suit char.
    if len(s) == 2 and s[0].upper() == s[1].upper():
        r = _rank_from_char(s[0])
        return Card(r, Suit.HEARTS), Card(r, Suit.SPADES)

    if len(s) < 3:
        raise ValueError(f"Hand notation must be like 'JTs', 'AKo', or 'JhTh': got {notation!r}")

    r1 = _rank_from_char(s[0])
    r2 = _rank_from_char(s[1])
    suited = s[2].lower() == "s"
    if suited:
        return Card(r1, Suit.HEARTS), Card(r2, Suit.HEARTS)
    return Card(r1, Suit.HEARTS), Card(r2, Suit.SPADES)


def preflop_btn_open(notation: str, stack_depth_bb: float = 100.0) -> dict[str, Any]:
    """HU BTN open decision for the given hand notation."""
    c1, c2 = cards_from_notation(notation)
    decision = _preflop.button_open_decision(c1, c2, stack_depth_bb)
    return _serialize_preflop(decision)


def preflop_bb_vs_open(
    notation: str, open_size_bb: float = 2.5, stack_depth_bb: float = 100.0
) -> dict[str, Any]:
    """HU BB defense vs an open."""
    c1, c2 = cards_from_notation(notation)
    decision = _preflop.bb_vs_open_decision(c1, c2, open_size_bb, stack_depth_bb)
    return _serialize_preflop(decision)


def preflop_btn_vs_3bet(
    notation: str, three_bet_size_bb: float = 8.0, stack_depth_bb: float = 100.0
) -> dict[str, Any]:
    """HU BTN/SB decision facing a BB 3-bet (4-bet / call / fold)."""
    c1, c2 = cards_from_notation(notation)
    decision = _preflop.button_vs_3bet_decision(c1, c2, three_bet_size_bb, stack_depth_bb)
    return _serialize_preflop(decision)


def board_classification(board_str: str, is_4bet_pot: bool = False) -> dict[str, Any]:
    """Flop classification: texture, c-bet frequency, sizing, range advantage."""
    cards = parse_board(board_str)
    analysis = _board.classify_board(cards, is_4bet_pot=is_4bet_pot)
    return {
        "data": {
            "category": analysis.category.value,
            "cbet_frequency": analysis.cbet_frequency,
            "cbet_frequency_pct": analysis.cbet_frequency_pct,
            "cbet_size_pct": analysis.cbet_size_pct,
            "cbet_size_pct_display": analysis.cbet_size_pct_display,
            "range_advantage": analysis.range_advantage,
            "nut_advantage": analysis.nut_advantage,
            "principle": analysis.principle,
            "explanation": analysis.explanation,
        },
        "confidence": _confidence_from_emoji(analysis.confidence).value,
        "source": "hu-poker-trainer/board.py (solver-verified, STRATEGY_NOTES.md)",
    }


def cbet_for_hand(
    notation: str, board_str: str, is_ip: bool = True, is_4bet_pot: bool = False
) -> dict[str, Any]:
    """Hand-specific c-bet decision on top of board-level classification."""
    c1, c2 = cards_from_notation(notation)
    board_cards = parse_board(board_str)
    board_analysis = _board.classify_board(board_cards, is_4bet_pot=is_4bet_pot)
    decision = _postflop.cbet_decision([c1, c2], board_cards, board_analysis, is_ip=is_ip)
    return {
        "data": {
            "should_bet": decision.should_bet,
            "frequency": decision.frequency,
            "is_mixed": decision.is_mixed,
            "sizing_pct": decision.sizing_pct,
            "hand_category": decision.hand_category.value,
            "principle": decision.principle,
            "explanation": decision.explanation,
            "board_category": board_analysis.category.value,
            "board_cbet_frequency": board_analysis.cbet_frequency,
            "board_cbet_size_pct": board_analysis.cbet_size_pct,
            "range_advantage": board_analysis.range_advantage,
        },
        "confidence": _confidence_from_emoji(decision.confidence).value,
        "source": "hu-poker-trainer/postflop.py (solver-verified, STRATEGY_NOTES.md)",
    }


def _serialize_preflop(decision: Any) -> dict[str, Any]:
    return {
        "data": {
            "action": decision.action.value,
            "frequency": decision.frequency,
            "is_mixed": decision.is_mixed,
            "alternative": decision.alternative.value if decision.alternative else None,
            "alt_frequency": decision.alt_frequency,
            "sizing_bb": decision.sizing_bb,
            "principle": decision.principle,
            "explanation": decision.explanation,
        },
        "confidence": _confidence_from_emoji(decision.confidence).value,
        "source": "hu-poker-trainer/preflop.py (solver-verified, STRATEGY_NOTES.md)",
    }
