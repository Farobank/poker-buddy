from backend.tools.confidence import Confidence
from backend.tools.postflop_lookup import postflop_lookup


def test_hu_flop_cbet_top_pair_green():
    r = postflop_lookup(
        format="hu",
        hand="KhQs",
        board="Kh7d2c",
        position="btn",
        line=["btn_open_2.5", "bb_call"],
        stack_depth_bb=100,
    )
    assert r["data"] is not None
    assert r["data"]["should_bet"] is True
    assert r["confidence"] == Confidence.GREEN.value


def test_hu_flop_cbet_air():
    r = postflop_lookup(
        format="hu",
        hand="3h2s",  # nothing on K72r
        board="Kh7d2c",
        position="btn",
        line=["btn_open_2.5", "bb_call"],
    )
    assert r["data"] is not None
    assert isinstance(r["data"]["should_bet"], bool)
    assert r["confidence"] in (Confidence.GREEN.value, Confidence.YELLOW.value)


def test_six_max_returns_amber():
    r = postflop_lookup(
        format="6max",
        hand="KhQs",
        board="Kh7d2c",
        position="co",
        line=["co_open_2.5", "bb_call"],
    )
    assert r["data"] is None
    assert r["confidence"] == Confidence.AMBER.value


def test_hu_turn_returns_yellow():
    r = postflop_lookup(
        format="hu",
        hand="KhQs",
        board="Kh7d2c4s",  # turn, 4 cards
        position="btn",
        line=["btn_open_2.5", "bb_call", "btn_cbet_33", "bb_call"],
    )
    assert r["data"] is None
    assert r["confidence"] == Confidence.YELLOW.value


def test_hu_3bet_pot_yellow_not_green():
    """3-bet pots aren't in v1 c-bet engine; should return yellow with hint."""
    r = postflop_lookup(
        format="hu",
        hand="KhQs",
        board="Kh7d2c",
        position="btn",
        line=["btn_open_2.5", "bb_3bet_9", "btn_call"],
    )
    assert r["data"] is None
    assert r["confidence"] == Confidence.YELLOW.value


def test_unknown_format():
    r = postflop_lookup(format="plo", hand="AsKsQhJd", board="Kh7d2c")
    assert r["confidence"] == Confidence.AMBER.value
