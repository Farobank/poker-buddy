from backend.tools.confidence import Confidence
from backend.tools.postflop_lookup import postflop_lookup


def test_hu_flop_cbet_top_pair_green():
    r = postflop_lookup(
        format="hu",
        hand="KdQs",  # top pair of kings; Kd is NOT on the board (no card collision)
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


# ---------------------------------------------------------------------------
# Suit-assumption bug class (audit): range notation forces both cards to hearts
# (hu_trainer.cards_from_notation). On a flush-texture board that fabricates a
# flush draw the player almost never holds. The tool must signal the assumption
# instead of serving a confident, wrong, GREEN draw read.
# ---------------------------------------------------------------------------

def test_range_notation_on_two_tone_board_not_green_phantom_draw():
    # JTs forced to Jh,Th on a two-heart board => engine sees a 4-flush and would
    # call it a GREEN "strong draw / semi-bluff." The player holds those exact
    # hearts only ~1 in 4 times, so this must NOT be a confident green draw.
    r = postflop_lookup(
        format="hu", hand="JTs", board="Ah7h2c",
        position="btn", line=["btn_open_2.5", "bb_call"],
    )
    assert r["confidence"] == Confidence.AMBER.value
    assert r["data"] is None
    assert r["note"] and "suit" in r["note"].lower()


def test_explicit_suits_real_flush_draw_stays_green():
    # The SAME hand with explicit suits (a genuine flush draw) is untouched.
    r = postflop_lookup(
        format="hu", hand="JhTh", board="Ah7h2c",
        position="btn", line=["btn_open_2.5", "bb_call"],
    )
    assert r["data"] is not None
    assert r["confidence"] == Confidence.GREEN.value


def test_range_notation_on_rainbow_board_not_over_hedged():
    # Rainbow board => no flush possible regardless of assumed suits => the read
    # is suit-invariant and must NOT be downgraded (avoid robotic over-hedging).
    r = postflop_lookup(
        format="hu", hand="AKo", board="Kh7d2c",
        position="btn", line=["btn_open_2.5", "bb_call"],
    )
    assert r["data"] is not None
    assert r["confidence"] == Confidence.GREEN.value


def test_made_hand_on_flush_board_flags_suit_assumption():
    # A made hand from range notation on a flush-texture board stays usable but
    # carries an explicit suit-assumption flag so the buddy can confirm suits.
    r = postflop_lookup(
        format="hu", hand="AQo", board="Qh7h2c",
        position="btn", line=["btn_open_2.5", "bb_call"],
    )
    assert r["data"] is not None
    assert r.get("assumption"), "made-hand read on assumed suits must flag the assumption"


def test_impossible_hand_card_on_board_declines():
    # Hole card duplicates a board card (e.g. AhKh while Ah is on the board):
    # physically impossible, must decline rather than score it as a real made hand.
    r = postflop_lookup(
        format="hu", hand="AhKh", board="Ah7d2c",
        position="btn", line=["btn_open_2.5", "bb_call"],
    )
    assert r["data"] is None
    assert r["confidence"] == Confidence.AMBER.value


# ---------------------------------------------------------------------------
# Street inference (audit): compact/texture board notation was misclassified.
# ---------------------------------------------------------------------------

def test_infer_street_handles_texture_and_compact_notation():
    from backend.tools.postflop_lookup import _infer_street
    assert _infer_street("T98tt") == "flop"   # two-tone marker, was 'unknown'
    assert _infer_street("K72r") == "flop"     # rainbow marker
    assert _infer_street("T98") == "flop"      # bare rank-only
    assert _infer_street("Kh7d2c") == "flop"   # concrete still works
    assert _infer_street("Kh7d2c4s") == "turn"
    assert _infer_street("Kh7d2c4s9h") == "river"


def test_compact_flop_board_asks_for_concrete_cards():
    # A flop read needs the real suits (texture/flush is suit-dependent). Compact
    # notation declines honestly instead of silently misreading.
    r = postflop_lookup(
        format="hu", hand="AhKh", board="T98tt",
        position="btn", line=["btn_open_2.5", "bb_call"],
    )
    assert r["data"] is None
    assert r["confidence"] in (Confidence.YELLOW.value, Confidence.AMBER.value)
    assert r["note"]


# ---------------------------------------------------------------------------
# Flop c-bet under-claim (audit): "BB checks to me" (bb_check) without restating
# the preflop open is the single most common HU postflop spot and must be the
# c-bet branch, not a yellow no-data decline.
# ---------------------------------------------------------------------------

def test_flop_cbet_from_bb_check_only_is_grounded():
    r = postflop_lookup(
        format="hu", hand="AhKd", board="Kh7d2c",
        position="btn", line=["bb_check"],
    )
    assert r["data"] is not None
    assert r["data"]["should_bet"] is True
    assert r["confidence"] == Confidence.GREEN.value


def test_flop_cbet_3bet_pot_still_declines():
    # The 3-bet exclusion is preserved: a 3-bet pot is not the v1 c-bet branch.
    r = postflop_lookup(
        format="hu", hand="AhKd", board="Kh7d2c",
        position="btn", line=["btn_open_2.5", "bb_3bet_8", "bb_check"],
    )
    assert r["data"] is None
    assert r["confidence"] == Confidence.YELLOW.value
