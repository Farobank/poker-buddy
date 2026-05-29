"""Memory tool tests. Uses an isolated tmp DB per test."""

import json
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "test.db")
        monkeypatch.setenv("BUDDY_DB_PATH", path)
        # Reload modules that captured DEFAULT_DB_PATH at import time.
        import importlib
        import backend.db as db_mod
        importlib.reload(db_mod)
        import backend.tools.memory as mem_mod
        importlib.reload(mem_mod)
        yield path


def test_memory_read_unknown_topic_returns_note():
    from backend.tools.memory import memory_read
    r = memory_read("not_a_topic")
    assert r["data"] is None
    assert "Unknown topic" in r["note"]


def test_memory_read_profile_empty_by_default():
    from backend.tools.memory import memory_read
    r = memory_read("profile")
    assert r["data"] is None


def test_profile_update_then_read():
    from backend.tools.memory import memory_read, memory_write
    out = memory_write("profile_update", {
        "stakes": "$1/$2 6-max online",
        "variants": ["hu_cash", "6max_cash"],
        "study_goals": "tighten BB defense vs small opens",
    })
    assert out["ok"]
    r = memory_read("profile")
    assert r["data"]["stakes"] == "$1/$2 6-max online"
    assert "hu_cash" in r["data"]["variants"]


def test_hand_discussed_writes_to_hands_table():
    from backend.tools.memory import memory_read, memory_write
    memory_write("hand_discussed", {
        "format": "hu",
        "hand": "JhTh",
        "position": "btn",
        "board": "Kh7d2c",
        "action": ["btn_open_2.5", "bb_call"],
        "takeaway": "Small c-bet on dry high; range advantage clearly held.",
        "confidence": "green",
    })
    r = memory_read("recent_hands")
    assert len(r["data"]) == 1
    h = r["data"][0]
    assert h["hand_text"] == "JhTh"
    assert h["board"] == "Kh7d2c"


def test_leak_identified_writes_to_leaks_table():
    from backend.tools.memory import memory_read, memory_write
    memory_write("leak_identified", {
        "description": "Folding river too often in 3-bet pots OOP",
        "severity": "real",
    })
    r = memory_read("recent_leaks")
    assert len(r["data"]) == 1
    assert "folding river" in r["data"][0]["description"].lower()


def test_opponent_profile_update_auto_tags():
    from backend.tools.memory import memory_read, opponent_profile_update
    out = opponent_profile_update("Russian reg", "LAG, 3bets wide from button, bluff heavy")
    assert out["ok"]
    assert "lag" in out["auto_tags"]
    assert "bluff_heavy" in out["auto_tags"]
    r = memory_read("opponents")
    assert any(o["label"] == "Russian reg" for o in r["data"])


def test_opponent_observation_via_memory_write():
    from backend.tools.memory import memory_read, memory_write
    memory_write("opponent_observation", {
        "label": "Maria",
        "observation": "calling station — calls down with weak holdings",
    })
    r = memory_read("opponents")
    labels = {o["label"] for o in r["data"]}
    assert "Maria" in labels


def test_opponent_update_merges_tags_and_appends_notes():
    from backend.tools.memory import memory_read, opponent_profile_update
    opponent_profile_update("Whale Bob", "loose passive, calls everything")
    opponent_profile_update("Whale Bob", "raised river once — atypical")
    r = memory_read("opponents")
    bob = next(o for o in r["data"] if o["label"] == "Whale Bob")
    assert "loose" in bob["tags"] or "passive" in bob["tags"]
    assert "atypical" in bob["notes"]
    assert bob["hands_count"] == 2


def test_memory_write_unknown_kind_returns_note():
    from backend.tools.memory import memory_write
    r = memory_write("weird_kind", {"foo": "bar"})
    assert not r["ok"]
    assert "Unknown kind" in r["note"]


def test_session_note_creates_session_then_updates():
    from backend.tools.memory import memory_read, memory_write
    memory_write("session_note", {"summary": "Studied K72r c-bet."})
    r = memory_read("session")
    assert r["data"]["summary"] == "Studied K72r c-bet."

    memory_write("session_note", {"update_latest": True, "hands_discussed": 5})
    r = memory_read("session")
    assert r["data"]["hands_discussed"] == 5


# ---------------------------------------------------------------------------
# Robustness (audit): never crash mid-conversation; never report a save that
# didn't happen; never silently corrupt a field's type.
# ---------------------------------------------------------------------------

def test_memory_write_malformed_content_returns_note_not_crash():
    # A content value SQLite can't bind (a dict where a scalar is expected) used
    # to raise -> HTTP 500 mid-spot. It must degrade to an honest {ok:False, note}.
    from backend.tools.memory import memory_write
    r = memory_write("session_note", {"hands_discussed": {"nested": 1}, "summary": "x"})
    assert r["ok"] is False
    assert r["note"]


def test_opponent_observation_missing_field_reports_not_ok():
    # Missing label/observation skipped the upsert but still returned ok:True —
    # the buddy believed it logged a read it actually dropped.
    from backend.tools.memory import memory_read, memory_write
    r = memory_write("opponent_observation", {"label": "Ghost"})  # no observation
    assert r["ok"] is False
    assert all(o["label"] != "Ghost" for o in memory_read("opponents")["data"])


def test_profile_update_coerces_scalar_variant_to_list():
    # variants sent as a bare string round-tripped to the wrong type (a string,
    # not a list). Coerce so memory_read always returns a list.
    from backend.tools.memory import memory_read, memory_write
    memory_write("profile_update", {"stakes": "$1/$2", "variants": "hu_cash"})
    assert memory_read("profile")["data"]["variants"] == ["hu_cash"]
