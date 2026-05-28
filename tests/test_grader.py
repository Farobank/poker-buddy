"""Tests for the transcript grader.

The grader pulls ConvAI conversation history and flags violations of the
system-prompt's hard rules — above all the trust rule: never state a GTO
frequency/sizing/percentage without a backing solver lookup. This is the
compounding leak-finder NEXT.md asks for.

Design: `grade_transcript` is a PURE function over normalized turns. Each
turn carries a `grounded` flag (did a preflop/postflop lookup return a real
number this turn, or carried from a prior agent turn since the last user
message). `normalize_transcript` maps the ElevenLabs API shape into that
contract and is tested separately.
"""

from __future__ import annotations

from backend.grader import grade_transcript, normalize_transcript


def agent(text: str, grounded: bool = False) -> dict:
    return {"role": "agent", "text": text, "grounded": grounded}


def user(text: str) -> dict:
    return {"role": "user", "text": text, "grounded": False}


# ---------------------------------------------------------------------------
# The trust rule — fabricated numbers (the critical check)
# ---------------------------------------------------------------------------

def test_flags_ungrounded_digit_percentage():
    v = grade_transcript([agent("I'm betting about 60% here")])
    assert any(x.rule == "fabricated_number" and x.severity == "critical" for x in v)


def test_flags_ungrounded_spelled_percentage():
    """The sneaky case: the prompt tells it to spell numbers out, so a
    fabricating-but-obedient agent says 'sixty percent', not '60%'."""
    v = grade_transcript([agent("On the turn I'm betting around sixty percent")])
    assert any(x.rule == "fabricated_number" for x in v)


def test_grounded_percentage_not_flagged():
    v = grade_transcript([
        agent("Solver says BTN opens about sixty percent, that's verified", grounded=True)
    ])
    assert not any(x.rule == "fabricated_number" for x in v)


def test_amber_lookup_then_number_is_fabricated():
    """A lookup that returned amber (no number) does NOT ground a stated
    number. grounded=False even though a tool was called — the exact leak."""
    v = grade_transcript([
        agent("No solver data for six-max, but I'm opening around forty percent", grounded=False)
    ])
    assert any(x.rule == "fabricated_number" for x in v)


def test_pot_sizing_without_grounding_flagged():
    v = grade_transcript([agent("I'm going half pot on the river here")])
    assert any(x.rule == "fabricated_number" for x in v)


def test_honest_read_no_number_is_clean():
    v = grade_transcript([
        agent("My read is keep firing, this card's great for my range, but that's feel not a number")
    ])
    assert v == []


def test_user_turn_with_number_not_flagged():
    v = grade_transcript([user("I bet 75% pot and he called")])
    assert v == []


# ---------------------------------------------------------------------------
# False-positive guards — poker language that is NOT a fabricated stat
# ---------------------------------------------------------------------------

def test_action_name_not_flagged():
    assert grade_transcript([agent("I'd three bet here and barrel most turns")]) == []
    assert grade_transcript([agent("standard 3-bet spot, snap it")]) == []


def test_stack_depth_allowed():
    v = grade_transcript([agent("At a hundred big blinds deep I'm happy to stack off")])
    assert v == []


def test_villain_bet_narration_not_flagged():
    """Narrating the villain's bet ('he leads half pot') is the hand being
    discussed, not a fabricated stat — it must not trip the critical rule."""
    v = grade_transcript([
        agent("River pairs the board, he leads tiny, half pot ish, after checking twice. "
              "No solver data on rivers, just my read: I'm calling, great price.")
    ])
    assert not any(x.rule == "fabricated_number" for x in v)


def test_buddy_own_sizing_still_flagged_alongside_villain_narration():
    """The villain guard is scoped: the agent's OWN recommended sizing in the
    same turn is still a fabrication, even if a villain bet was narrated too."""
    v = grade_transcript([
        agent("He bet half pot, and my read is I'm raising to full pot here")
    ])
    assert any(x.rule == "fabricated_number" for x in v)


# ---------------------------------------------------------------------------
# Voice formatting — length + spell-out
# ---------------------------------------------------------------------------

def test_over_length_agent_turn_flagged():
    long_text = " ".join(["word"] * 80)
    v = grade_transcript([agent(long_text)])
    assert any(x.rule == "over_length" and x.severity == "minor" for x in v)


def test_short_turn_no_over_length():
    v = grade_transcript([agent("Yeah that's a clean line, I'd play it the same.")])
    assert not any(x.rule == "over_length" for x in v)


def test_digit_percent_flagged_unspelled():
    """Even grounded, a digit percentage is a voice-formatting violation —
    it must be spoken spelled-out."""
    v = grade_transcript([agent("solver-verified, 25%", grounded=True)])
    assert any(x.rule == "unspelled" for x in v)


def test_spelled_percentage_not_unspelled():
    v = grade_transcript([agent("about sixty percent", grounded=True)])
    assert not any(x.rule == "unspelled" for x in v)


# ---------------------------------------------------------------------------
# Whole-transcript behavior
# ---------------------------------------------------------------------------

def test_clean_transcript():
    turns = [
        user("BTN opens 2.5, I have JTs in the BB"),
        agent("Let me check the range, one sec"),
        agent("Solver-verified, this is a clear call. You're getting a great price.", grounded=True),
    ]
    assert grade_transcript(turns) == []


def test_violation_carries_turn_index():
    turns = [user("spot?"), agent("betting 60%")]
    v = grade_transcript(turns)
    assert any(x.turn_index == 1 for x in v)


# ---------------------------------------------------------------------------
# normalize_transcript — ElevenLabs API shape → normalized turns
# ---------------------------------------------------------------------------

def test_normalize_maps_role_and_text():
    raw = {"transcript": [
        {"role": "user", "message": "what's the spot"},
        {"role": "agent", "message": "checking",
         "tool_calls": [{"tool_name": "preflop_lookup"}],
         "tool_results": [{"tool_name": "preflop_lookup",
                           "result_value": '{"confidence":"green","data":{"action":"raise"}}'}]},
    ]}
    turns = normalize_transcript(raw)
    assert turns[0] == {"role": "user", "text": "what's the spot", "grounded": False}
    assert turns[1]["role"] == "agent"
    assert turns[1]["text"] == "checking"
    assert turns[1]["grounded"] is True


def test_normalize_amber_not_grounded():
    raw = {"transcript": [
        {"role": "agent", "message": "no data for six-max",
         "tool_calls": [{"tool_name": "postflop_lookup"}],
         "tool_results": [{"tool_name": "postflop_lookup",
                           "result_value": '{"confidence":"amber","data":null}'}]},
    ]}
    turns = normalize_transcript(raw)
    assert turns[0]["grounded"] is False


def test_normalize_yellow_without_data_not_grounded():
    """HU turn/river return confidence=yellow but data=None (no number). That
    must NOT count as grounding — otherwise the grader blesses a fabricated
    turn number on the exact streets the trust rule is meant to protect."""
    raw = {"transcript": [
        {"role": "agent", "message": "on the turn I'm firing about sixty percent",
         "tool_calls": [{"tool_name": "postflop_lookup"}],
         "tool_results": [{"tool_name": "postflop_lookup",
                           "result_value": '{"confidence":"yellow","data":null}'}]},
    ]}
    turns = normalize_transcript(raw)
    assert turns[0]["grounded"] is False


def test_normalize_grounding_carries_to_next_agent_turn():
    raw = {"transcript": [
        {"role": "user", "message": "BTN opens, JTs in BB"},
        {"role": "agent", "message": "let me check, one sec",
         "tool_calls": [{"tool_name": "preflop_lookup"}],
         "tool_results": [{"tool_name": "preflop_lookup",
                           "result_value": '{"confidence":"green","data":{"action":"call"}}'}]},
        {"role": "agent", "message": "yeah solver says this is a clear call, sixty percent of the time"},
    ]}
    turns = normalize_transcript(raw)
    assert turns[2]["grounded"] is True


def test_normalize_grounding_resets_after_user_turn():
    raw = {"transcript": [
        {"role": "agent", "message": "checking",
         "tool_calls": [{"tool_name": "preflop_lookup"}],
         "tool_results": [{"tool_name": "preflop_lookup",
                           "result_value": '{"confidence":"green","data":{}}'}]},
        {"role": "user", "message": "ok what about six-max from the cutoff"},
        {"role": "agent", "message": "opening about forty percent there"},
    ]}
    turns = normalize_transcript(raw)
    assert turns[2]["grounded"] is False
