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


def test_six_max_returns_null_amber():
    r = preflop_lookup("6max", "co", "AKs", action_so_far=[])
    assert r["data"] is None
    assert r["confidence"] == Confidence.AMBER.value
    assert "6-max" in r["note"] or "solver-verified" in r["note"]


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
