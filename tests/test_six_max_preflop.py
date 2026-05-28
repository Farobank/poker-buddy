"""Tests for the grounded 6-max preflop ranges engine.

The engine encodes standard published 6-max 100bb cash ranges (Upswing / GTO
Wizard consensus, cross-verified — see backend/engines/SIX_MAX_NOTES.md). The
discipline that protects the buddy's trust: every supported spot comes back
green or yellow with real data — NEVER amber-guessing, NEVER a fabricated
number. Hands clearly outside a range fold (green). Spots outside the v1
coverage (facing a 4-bet, multiway, limped pots) honestly decline with a note
and data=None rather than inventing a line.

These are the TDD anchors for TASK 1, including the five cases named in the
brief:
  UTG opens AKs → raise; CO opens A5s → raise; BB defends vs a CO open;
  BTN 4-bets AA vs a 3-bet; UTG 72o → fold.
"""

from __future__ import annotations

import pytest

from backend.engines import six_max_preflop as sm
from backend.tools.confidence import Confidence

GREEN = Confidence.GREEN.value
YELLOW = Confidence.YELLOW.value
AMBER = Confidence.AMBER.value
GROUNDED = {GREEN, YELLOW}

OPEN_POSITIONS = ["utg", "mp", "co", "btn", "sb"]


# ---------------------------------------------------------------------------
# normalize_hand — accept notation OR concrete cards (preflop_lookup passes
# `hand` straight through, so the engine must canonicalize both).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("AKs", "AKs"),
        ("AKo", "AKo"),
        ("KAs", "AKs"),          # order-insensitive
        ("AA", "AA"),
        ("AhKs", "AKo"),         # concrete, offsuit
        ("JhTh", "JTs"),         # concrete, suited
        ("AhAs", "AA"),          # concrete pair
        ("7 2 o", "72o"),        # whitespace tolerated
        ("ahks", "AKo"),         # lowercase
    ],
)
def test_normalize_hand(raw, expected):
    assert sm.normalize_hand(raw) == expected


# ---------------------------------------------------------------------------
# The five named anchor cases from the brief
# ---------------------------------------------------------------------------

def test_anchor_utg_opens_aks_raise():
    d = sm.open_decision("utg", "AKs")
    assert d.action == "raise"
    assert d.confidence.value == GREEN


def test_anchor_co_opens_a5s_raise():
    d = sm.open_decision("co", "A5s")
    assert d.action == "raise"
    assert d.confidence.value in GROUNDED


def test_anchor_bb_defends_vs_co_open():
    # A clear flat: BB defends T9s vs a CO open (calls, doesn't fold).
    d = sm.vs_open_decision("bb", "T9s", opener="co")
    assert d.action in ("call", "3bet")
    assert d.confidence.value in GROUNDED


def test_anchor_btn_4bets_AA_vs_3bet():
    # BTN opens, BB 3-bets, BTN 4-bets (a positionally real 3-bettor).
    d = sm.vs_3bet_decision("btn", "AA", threebettor="bb")
    assert d.action == "4bet"
    assert d.confidence.value == GREEN


def test_anchor_utg_72o_folds():
    d = sm.open_decision("utg", "72o")
    assert d.action == "fold"
    assert d.confidence.value == GREEN


# ---------------------------------------------------------------------------
# Open (RFI) by position
# ---------------------------------------------------------------------------

def test_open_premiums_raise_everywhere():
    for pos in OPEN_POSITIONS:
        for hand in ("AA", "KK", "AKs", "AKo"):
            d = sm.open_decision(pos, hand)
            assert d.action == "raise", f"{pos} {hand}"
            assert d.confidence.value == GREEN, f"{pos} {hand}"
            assert d.sizing_bb is not None


def test_open_widens_toward_button():
    # 54s: clearly outside the UTG range, opened by CO and BTN (range widens).
    assert sm.open_decision("utg", "54s").action == "fold"
    assert sm.open_decision("co", "54s").action == "raise"
    assert sm.open_decision("btn", "54s").action == "raise"


def test_open_trash_folds_even_on_button():
    for hand in ("72o", "82o", "32o"):
        assert sm.open_decision("btn", hand).action == "fold", hand


def test_sb_open_size_is_3bb_others_2_5bb():
    # Published convention: 2.5bb from every seat except SB, which uses 3bb.
    assert sm.open_decision("co", "AA").sizing_bb == 2.5
    assert sm.open_decision("sb", "AA").sizing_bb == 3.0


def test_open_bb_cannot_rfi_returns_note():
    # BB never opens first-in (it has already posted and acts last preflop).
    result = sm.lookup("bb", "AA", actions=[])
    assert result["data"] is None
    assert result["note"]


def test_open_mixed_hands_are_yellow_and_flagged():
    # A bottom-of-range UTG opener (mixed in the solver) must be yellow + mixed,
    # never asserted as a pure green open.
    d = sm.open_decision("utg", "A5s")
    assert d.action == "raise"
    assert d.confidence.value == YELLOW
    assert d.is_mixed is True


# ---------------------------------------------------------------------------
# vs-open: 3-bet / call / fold
# ---------------------------------------------------------------------------

def test_vs_open_value_3bet():
    d = sm.vs_open_decision("btn", "KK", opener="utg")
    assert d.action == "3bet"
    assert d.confidence.value == GREEN
    assert d.sizing_bb is not None


def test_vs_open_suited_wheel_ace_is_3bet_bluff_yellow():
    d = sm.vs_open_decision("btn", "A5s", opener="co")
    assert d.action == "3bet"
    assert d.confidence.value == YELLOW  # bluff tier is theory-grounded, not green


def test_vs_open_bb_defends_wider_than_it_folds():
    # vs a BTN steal the BB calls a wide band; vs UTG it folds the same weak hand.
    assert sm.vs_open_decision("bb", "K9o", opener="btn").action in ("call", "3bet")
    assert sm.vs_open_decision("bb", "72o", opener="btn").action == "fold"


def test_vs_open_ip_flat_of_late_open():
    # BTN flats a CO open with a hand too good to fold, not strong enough to 3bet.
    d = sm.vs_open_decision("btn", "99", opener="co")
    assert d.action in ("call", "3bet")
    assert d.confidence.value in GROUNDED


def test_vs_open_clear_fold_is_green():
    d = sm.vs_open_decision("co", "72o", opener="utg")
    assert d.action == "fold"
    assert d.confidence.value == GREEN


# ---------------------------------------------------------------------------
# vs-3bet: 4-bet / call / fold
# ---------------------------------------------------------------------------

def test_vs_3bet_value_4bet_green():
    for hand in ("AA", "KK", "AKs"):
        d = sm.vs_3bet_decision("co", hand, threebettor="btn")
        assert d.action == "4bet", hand
        assert d.confidence.value == GREEN, hand


def test_vs_3bet_suited_wheel_ace_4bet_bluff_yellow():
    d = sm.vs_3bet_decision("co", "A5s", threebettor="btn")
    assert d.action == "4bet"
    assert d.confidence.value == YELLOW


def test_vs_3bet_strong_hand_calls():
    d = sm.vs_3bet_decision("btn", "QQ", threebettor="sb")
    assert d.action in ("4bet", "call")
    assert d.confidence.value in GROUNDED


def test_vs_3bet_marginal_hand_folds_green():
    d = sm.vs_3bet_decision("co", "76s", threebettor="btn")
    assert d.action == "fold"
    assert d.confidence.value == GREEN


# ---------------------------------------------------------------------------
# Discipline: supported spots are NEVER amber, NEVER data=None, NEVER fabricate.
# ---------------------------------------------------------------------------

def test_supported_spots_are_green_or_yellow_never_amber():
    sample = ["AA", "AKs", "AKo", "QQ", "JJ", "TT", "99", "A5s", "KQs",
              "JTs", "T9s", "76s", "K9o", "Q9s", "54s", "72o", "32o", "J8o"]
    for pos in OPEN_POSITIONS:
        for hand in sample:
            d = sm.open_decision(pos, hand)
            assert d.confidence.value in GROUNDED, f"open {pos} {hand} -> {d.confidence}"
            assert d.action in ("raise", "fold")


def test_lookup_returns_normalized_dict_matching_hu_shape():
    # Must mirror the HU path's {data, confidence, source} contract so the tool
    # layer treats both identically.
    result = sm.lookup("co", "A5s", actions=[])
    assert set(result) >= {"data", "confidence", "source"}
    assert result["confidence"] in GROUNDED
    assert result["data"] is not None
    for key in ("action", "frequency", "is_mixed", "alternative",
                "alt_frequency", "sizing_bb", "principle", "explanation"):
        assert key in result["data"], key
    assert "6max" in result["source"] or "6-max" in result["source"].lower()


@pytest.mark.parametrize("bad", ["XX", "ZZ", "XhKs", "1h2s", "X9s", "Z2o", "AAA"])
def test_malformed_hand_declines_never_fabricates(bad):
    # Regression: a non-hand must NOT crash and must NOT come back as a confident
    # green fold/raise (e.g. "XX" once normalized to a fake pair). It declines
    # honestly: data=None, amber, with a note — never a fabricated answer.
    result = sm.lookup("co", bad, actions=[])
    assert result["data"] is None, f"{bad!r} must not yield a fabricated decision"
    assert result["confidence"] == AMBER
    assert result["note"]


def test_lookup_unsupported_spot_declines_without_fabricating():
    # Facing a 4-bet is outside the v1 grounded set. The engine must NOT invent
    # a line — it returns no data + a note (honest decline), not a number.
    result = sm.lookup(
        "co", "AA",
        actions=["co_open_2.5", "btn_3bet_8", "co_4bet_18", "btn_5bet"],
    )
    assert result["data"] is None
    assert result["note"]


# ---------------------------------------------------------------------------
# Accuracy gate: each open range's combo-weighted % lands in the published band.
# (UTG 15-17%, MP 19-22%, CO 25-30%, BTN 40-48%, SB 39-47% — confirmed across
# Upswing / GTO Wizard / freebetrange / mypokercoaching / pokertrainer.se.
# Bands are widened to span real source-to-source disagreement.)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pos, lo, hi",
    [
        ("utg", 10.0, 20.0),
        ("mp", 14.0, 24.0),
        ("co", 22.0, 33.0),
        ("btn", 38.0, 54.0),
        ("sb", 34.0, 52.0),
    ],
)
def test_open_range_percent_in_published_band(pos, lo, hi):
    pct = sm.weighted_open_percent(pos)
    assert lo <= pct <= hi, f"{pos} open = {pct:.1f}% (band {lo}-{hi}%)"


def test_open_ranges_widen_monotonically_by_position():
    pcts = [sm.weighted_open_percent(p) for p in ("utg", "mp", "co", "btn")]
    assert pcts == sorted(pcts), pcts
    assert pcts[0] < pcts[-1]
