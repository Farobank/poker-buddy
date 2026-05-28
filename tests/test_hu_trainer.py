"""Verify the hu-poker-trainer integration shim returns sane shapes."""

import pytest

from backend.integrations.hu_trainer import (
    board_classification,
    cards_from_notation,
    cbet_for_hand,
    preflop_btn_open,
    preflop_bb_vs_open,
)
from backend.tools.confidence import Confidence


def test_cards_from_notation_pair():
    c1, c2 = cards_from_notation("AA")
    assert c1.rank == c2.rank
    assert c1.suit != c2.suit  # different suits for a pair


def test_cards_from_notation_suited():
    c1, c2 = cards_from_notation("JTs")
    assert c1.rank != c2.rank
    assert c1.suit == c2.suit


def test_cards_from_notation_offsuit():
    c1, c2 = cards_from_notation("AKo")
    assert c1.rank != c2.rank
    assert c1.suit != c2.suit


def test_btn_open_strong_hand_raises():
    result = preflop_btn_open("AA")
    assert result["data"]["action"] == "raise"
    assert result["confidence"] in (Confidence.GREEN.value, Confidence.YELLOW.value)
    assert "solver-verified" in result["source"].lower()


def test_btn_open_garbage_folds():
    result = preflop_btn_open("32o")
    assert result["data"]["action"] == "fold"
    assert result["confidence"] == Confidence.GREEN.value


def test_board_classification_dry_high():
    result = board_classification("Kh7d2c")
    data = result["data"]
    assert data["category"] in ("dry_high", "mid_texture")  # K72r is dry_high
    assert 0.0 <= data["cbet_frequency"] <= 1.0
    assert 0.0 <= data["cbet_size_pct"] <= 2.0  # in pot fractions
    assert result["confidence"] in {c.value for c in Confidence}


def test_cbet_top_pair_on_dry_board():
    result = cbet_for_hand("KhQs", "Kh7d2c")
    data = result["data"]
    assert data["should_bet"] is True
    assert data["hand_category"] in ("top_pair", "monster")
    assert result["confidence"] == Confidence.GREEN.value


def test_cbet_air_on_dry_high():
    # JTs on K72r has no real equity. Decision may be check or low-freq bet.
    result = cbet_for_hand("JhTh", "Kh7d2c")
    data = result["data"]
    assert isinstance(data["should_bet"], bool)
    assert 0.0 <= data["frequency"] <= 1.0


def test_bb_vs_open_strong():
    result = preflop_bb_vs_open("AA", open_size_bb=2.5)
    # AA is always at least a call, often a 3-bet
    assert result["data"]["action"] in ("3bet", "raise", "call")
    assert result["data"]["frequency"] > 0
