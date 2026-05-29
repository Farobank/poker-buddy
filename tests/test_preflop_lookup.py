import pytest

from backend.tools.confidence import Confidence
from backend.tools.preflop_lookup import preflop_lookup


def test_hu_btn_open_strong_hand():
    r = preflop_lookup("hu", "btn", "AA", stack_depth_bb=100)
    assert r["data"]["action"] == "raise"
    assert r["confidence"] in (Confidence.GREEN.value, Confidence.YELLOW.value)


def test_hu_btn_open_garbage():
    r = preflop_lookup("hu", "btn", "32o")
    assert r["data"]["action"] == "fold"
    assert r["confidence"] == Confidence.GREEN.value


def test_hu_bb_vs_open():
    r = preflop_lookup(
        "hu", "bb", "AA", stack_depth_bb=100, action_so_far=["btn_open_2.5"]
    )
    assert r["data"] is not None
    assert r["data"]["action"] in ("3bet", "raise", "call")


def test_hu_bb_no_action_returns_amber_with_note():
    r = preflop_lookup("hu", "bb", "AA")
    assert r["data"] is None
    assert r["confidence"] == Confidence.AMBER.value
    assert "BTN" in r["note"] or "btn" in r["note"].lower()


def test_six_max_co_open_is_grounded():
    # The 6-max branch now routes to the grounded preflop engine: a CO open of a
    # suited ace comes back green/yellow with real data, NOT amber/None.
    r = preflop_lookup("6max", "co", "A5s", action_so_far=[])
    assert r["data"] is not None, "6-max CO open must now be grounded, not amber"
    assert r["confidence"] in (Confidence.GREEN.value, Confidence.YELLOW.value)
    assert r["data"]["action"] == "raise"
    assert "6-max" in r["source"]


def test_six_max_utg_trash_folds_green():
    r = preflop_lookup("6max", "utg", "72o", action_so_far=[])
    assert r["data"]["action"] == "fold"
    assert r["confidence"] == Confidence.GREEN.value


def test_six_max_bb_defends_vs_open():
    r = preflop_lookup("6max", "bb", "T9s", action_so_far=["co_open_2.5"])
    assert r["data"] is not None
    assert r["data"]["action"] in ("call", "3bet")


def test_six_max_vs_3bet_4bets_aces():
    # CO opens, BTN 3-bets, CO holds aces -> grounded 4-bet for value.
    r = preflop_lookup(
        "6max", "co", "AA", action_so_far=["co_open_2.5", "btn_3bet_8"]
    )
    assert r["data"] is not None
    assert r["data"]["action"] == "4bet"
    assert r["confidence"] == Confidence.GREEN.value


def test_six_max_out_of_scope_spot_declines_amber():
    # Facing a 4-bet is outside the v1 grounded set: amber + note, no invented line.
    r = preflop_lookup(
        "6max", "co", "AA",
        action_so_far=["co_open_2.5", "btn_3bet_8", "co_4bet_18", "btn_5bet"],
    )
    assert r["data"] is None
    assert r["confidence"] == Confidence.AMBER.value
    assert r["note"]


def test_unknown_format():
    r = preflop_lookup("plo", "btn", "AAhh")
    assert r["data"] is None
    assert r["confidence"] == Confidence.AMBER.value


def test_hu_open_with_explicit_size_parses():
    # action 'btn_open_3' → BB facing a 3x open
    r = preflop_lookup("hu", "bb", "KQs", action_so_far=["btn_open_3"])
    # Just needs to not crash and return something reasonable.
    assert r["confidence"] in {c.value for c in Confidence}


def test_unsupported_hu_spot_returns_yellow():
    # BB facing a 4-bet is not v1-supported; we get yellow with a note.
    # (BTN/SB facing a 3-bet IS now supported — see the 3-bet test in test_eval.py.)
    r = preflop_lookup(
        "hu", "bb", "AA",
        action_so_far=["btn_open_2.5", "bb_3bet_9", "btn_4bet_21"],
    )
    assert r["data"] is None
    assert r["confidence"] == Confidence.YELLOW.value


# ---------------------------------------------------------------------------
# Action-verb normalization (audit): the agent phrases an open many ways and, in
# HU, the SB *is* the button. These must all route to the grounded lookup, not a
# yellow "not in my solver-verified set" decline (which made the buddy sound
# unsure on a spot it can answer perfectly). Mirrors six_max_preflop._parse_action.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("open_action", ["btn_open_2.5", "btn_raise_2.5", "btn_rfi_2.5", "sb_open_2.5"])
def test_hu_bb_vs_open_accepts_verb_variants(open_action):
    r = preflop_lookup("hu", "bb", "AA", action_so_far=[open_action])
    assert r["data"] is not None, f"{open_action} should ground BB defense, not decline"
    assert r["confidence"] in (Confidence.GREEN.value, Confidence.YELLOW.value)


@pytest.mark.parametrize("threebet_action", ["bb_3bet_10", "bb_reraise_10", "bb_rr_10"])
def test_hu_btn_vs_3bet_accepts_verb_variants(threebet_action):
    r = preflop_lookup("hu", "btn", "AKs", action_so_far=["btn_open_2.5", threebet_action])
    assert r["data"] is not None, f"{threebet_action} should ground the vs-3bet decision"
    assert r["confidence"] in (Confidence.GREEN.value, Confidence.YELLOW.value)


def test_hu_4bet_label_still_declines_to_yellow():
    # Guard: a genuine 4-bet label is NOT an open/3bet and must still fall through.
    r = preflop_lookup("hu", "bb", "AA", action_so_far=["btn_open_2.5", "bb_3bet_9", "btn_4bet_21"])
    assert r["data"] is None
    assert r["confidence"] == Confidence.YELLOW.value
