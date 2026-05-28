"""End-to-end eval suite — the 10 canonical spots from DESIGN.md.

This is what we run on every deploy to make sure the backend gives the ConvAI
LLM what it needs to produce trustworthy poker discussion. Each test maps to
one numbered spot in DESIGN.md "Testing & rollout".

The LLM itself lives in ElevenLabs ConvAI, so we can't directly assert what
it says. What we CAN guarantee is the tool-layer contract: confidence tags,
data shapes, presence of grounding for the agent to lean on, and that the
hard rules (boundary refusal, opponent-label privacy) are encoded in the
system prompt.

If any of these fail, the buddy will either fabricate frequencies (bad),
overclaim confidence (bad), or refuse spots it should handle (also bad).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture — isolated DB + fresh app, mirrors test_main.py
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("BUDDY_DB_PATH", str(Path(d) / "eval.db"))
        # Disable auth middleware for in-process tests. Set to "" not delenv
        # because main.py runs load_dotenv() which would repopulate from .env.
        monkeypatch.setenv("BUDDY_SHARED_SECRET", "")
        import importlib
        import backend.db as db_mod
        importlib.reload(db_mod)
        import backend.tools.memory as mem_mod
        importlib.reload(mem_mod)
        import backend.main as main_mod
        importlib.reload(main_mod)
        from fastapi.testclient import TestClient
        with TestClient(main_mod.app) as c:
            yield c


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Spot 1 — HU BTN open, standard hand
# ---------------------------------------------------------------------------

def test_spot_01_hu_btn_open_standard_hand(client):
    """HU BTN open with a premium hand returns a green/yellow solver-verified
    raise. The buddy can then say 'solver says raise' instead of guessing."""
    r = client.post(
        "/tools/preflop_lookup",
        json={"format": "hu", "position": "btn", "hand": "AKs"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confidence"] in ("green", "yellow"), body
    assert body["data"] is not None, "BTN open must return concrete data, not amber"
    assert body["data"].get("action") == "raise"


# ---------------------------------------------------------------------------
# Spot 2 — HU BB defense vs small open
# ---------------------------------------------------------------------------

def test_spot_02_hu_bb_defense_vs_small_open(client):
    """BB facing a 2.5x BTN open: solver-verified defense decision with action
    and (ideally) frequency or sizing context, so the buddy doesn't invent."""
    r = client.post(
        "/tools/preflop_lookup",
        json={
            "format": "hu",
            "position": "bb",
            "hand": "JTs",
            "action_so_far": ["btn_open_2.5"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confidence"] in ("green", "yellow"), body
    assert body["data"] is not None, "BB defense must return concrete data"
    assert "action" in body["data"]


# ---------------------------------------------------------------------------
# Spot 3 — HU BTN c-bet on dry board (range advantage)
# ---------------------------------------------------------------------------

def test_spot_03_hu_cbet_dry_board(client):
    """Dry high-card board (K72r) — BTN should c-bet a wide range small.
    Backend must return should_bet=True with sizing and frequency context."""
    r = client.post(
        "/tools/postflop_lookup",
        json={
            "format": "hu",
            "hand": "AhKd",
            "board": "Kh7d2c",
            "position": "btn",
            "line": ["btn_open_2.5", "bb_call"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"] is not None, "Dry-board c-bet must return concrete data"
    assert body["data"].get("should_bet") is True


# ---------------------------------------------------------------------------
# Spot 4 — HU BTN c-bet on wet board (smaller frequency, larger sizing)
# ---------------------------------------------------------------------------

def test_spot_04_hu_cbet_wet_board(client):
    """Wet, connected board (9h8h7c) — BTN c-bets less often, larger when it
    does. Backend should return data; the agent contrasts it against spot 3."""
    r = client.post(
        "/tools/postflop_lookup",
        json={
            "format": "hu",
            "hand": "AhKh",
            "board": "9h8h7c",
            "position": "btn",
            "line": ["btn_open_2.5", "bb_call"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"] is not None, "Wet-board spot must still return concrete data"
    assert "should_bet" in body["data"]


# ---------------------------------------------------------------------------
# Spot 5 — 6-max CO open: confidence MUST be amber, no fabricated frequency
# ---------------------------------------------------------------------------

def test_spot_05_6max_co_open_amber(client):
    """The trust rule: 6-max preflop has no solver engine, so the tool MUST
    return amber with data=None. If this ever turns green/yellow with concrete
    frequencies, the buddy will start making numbers up."""
    r = client.post(
        "/tools/preflop_lookup",
        json={"format": "6max", "position": "co", "hand": "JTs"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confidence"] == "amber", body
    assert body["data"] is None, "6-max preflop must NOT fabricate concrete data"
    assert "note" in body and body["note"], "Amber response must include a note"


# ---------------------------------------------------------------------------
# Spot 6 — 6-max 3-bet pot postflop: tool gives amber, theory_lookup gives grounding
# ---------------------------------------------------------------------------

def test_spot_06_6max_3bet_pot_falls_back_to_theory(client):
    """6-max 3-bet pot postflop. Postflop tool returns amber. The agent is
    expected to call theory_lookup for grounding — verify theory_lookup
    actually returns relevant chunks for the kind of query it would make."""
    # Step 1: postflop must be amber for 6-max (no fabrication).
    postflop = client.post(
        "/tools/postflop_lookup",
        json={
            "format": "6max",
            "hand": "AhKh",
            "board": "Kh7d2c",
            "position": "btn",
            "line": ["co_open_2.5", "btn_3bet_8", "co_call"],
        },
    ).json()
    assert postflop["confidence"] == "amber"
    assert postflop["data"] is None

    # Step 2: theory_lookup must return *something* for a typical 3-bet-pot query.
    theory = client.post(
        "/tools/theory_lookup",
        json={"query": "3-bet pot postflop range advantage", "k": 3},
    ).json()
    assert theory["data"], "theory_lookup must return chunks for the agent to lean on"
    assert len(theory["data"]) >= 1


# ---------------------------------------------------------------------------
# Spot 7 — opponent profile update with auto-tagging
# ---------------------------------------------------------------------------

def test_spot_07_opponent_profile_update(client):
    """When Bill says 'the Russian reg 3-bets very wide', the agent calls
    opponent_profile_update. The backend must auto-tag (LAG-ish) and store
    under HIS label (never a real online ID)."""
    r = client.post(
        "/tools/opponent_profile_update",
        json={
            "label": "Russian reg",
            "observation": "3-bets very wide from BTN, bluff-heavy on rivers",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # Confirm it's queryable and the auto-tags fired.
    opp = client.post("/tools/memory_read", json={"topic": "opponents"}).json()
    labels = {o["label"] for o in opp["data"]}
    assert "Russian reg" in labels
    bob = next(o for o in opp["data"] if o["label"] == "Russian reg")
    # Should have surfaced at least one structured tag from the free text.
    assert bob["tags"], "Free-text observation must auto-tag into structured tags"


# ---------------------------------------------------------------------------
# Spot 8 — cold-start memory recall ("what stakes do I play?")
# ---------------------------------------------------------------------------

def test_spot_08_memory_recall_after_profile_set(client):
    """Set the profile in one call (Monday). Read it back cold in a new
    memory_read (Tuesday). The buddy can now answer 'I play $1/$2 6-max
    online' without prompting."""
    client.post(
        "/tools/memory_write",
        json={
            "kind": "profile_update",
            "content": {
                "stakes": "$1/$2 6-max online, $2/$5 live",
                "variants": ["hu_cash", "6max_cash"],
                "study_goals": "tighten BB defense vs small opens",
            },
        },
    )
    r = client.post("/tools/memory_read", json={"topic": "profile"}).json()
    assert r["data"] is not None, "Profile must persist across calls"
    assert "$1/$2" in r["data"]["stakes"]
    assert "hu_cash" in r["data"]["variants"]


# ---------------------------------------------------------------------------
# Spot 9 — leak surfacing: prior leak is recallable
# ---------------------------------------------------------------------------

def test_spot_09_leak_surfacing(client):
    """When the agent reads recent_leaks at session start, prior leaks must
    be there to surface. ('You've been folding rivers in 3-bet pots OOP —
    look familiar?') The agent's actual surfacing is system-prompt-driven;
    we guarantee the data is fetchable and shaped right."""
    client.post(
        "/tools/memory_write",
        json={
            "kind": "leak_identified",
            "content": {
                "description": "Folding river too often in 3-bet pots OOP",
                "severity": "real",
            },
        },
    )
    r = client.post("/tools/memory_read", json={"topic": "recent_leaks"}).json()
    assert r["data"], "Leaks must be retrievable for the agent to surface"
    assert any("folding river" in leak["description"].lower() for leak in r["data"])


# ---------------------------------------------------------------------------
# Spot 10 — boundary test: real-time online assistance is system-prompt-refused
# ---------------------------------------------------------------------------

def test_spot_10_boundary_rule_documented_in_system_prompt():
    """The agent must refuse real-time advice during an active online hand.
    This is a system-prompt rule, not a backend tool. We assert the rule is
    actually in system-prompt.md — if someone edits it away, this test fires."""
    sys_prompt = (PROJECT_ROOT / "system-prompt.md").read_text()
    text = sys_prompt.lower()
    # Must mention the TOS-violation rule AND name the carve-out (live cash OK).
    assert "real-time" in text or "real time" in text, \
        "system prompt must address real-time online assistance"
    assert "tos" in text or "ban" in text or "violation" in text, \
        "system prompt must explain WHY it's refused (TOS / ban)"
    assert "live" in text, \
        "system prompt must allow the live-cash carve-out so we don't over-refuse"


# ---------------------------------------------------------------------------
# Discipline checks — additional rules that protect the buddy's trust
# ---------------------------------------------------------------------------

def test_discipline_opponent_label_privacy_in_system_prompt():
    """Hard rule: opponent labels are Bill's own tags, never real online IDs.
    If this drifts out of the system prompt, we risk a privacy leak."""
    sys_prompt = (PROJECT_ROOT / "system-prompt.md").read_text().lower()
    assert "nickname" in sys_prompt or "his tag" in sys_prompt or "own tag" in sys_prompt, \
        "system prompt must require opponent labels to be Bill's own nicknames"


def test_discipline_no_gto_frequencies_from_memory():
    """The single rule that flips the agent from 'confident bullshit' to peer:
    never state GTO frequencies/sizings/ranges without a tool call."""
    sys_prompt = (PROJECT_ROOT / "system-prompt.md").read_text().lower()
    # The rule mentions GTO and a tool-call requirement somewhere together.
    assert "gto" in sys_prompt
    assert "preflop_lookup" in sys_prompt or "tool" in sys_prompt
    assert "never" in sys_prompt or "must" in sys_prompt


def test_discipline_trust_block_and_coverage_map():
    """The front-loaded 'one rule that matters most' block + an accurate
    coverage map are what closed the postflop fabrication leak. Guard them
    from silent removal: the block must exist, the leak streets must be named,
    and the prompt must distinguish yellow (HU turn/river) from amber (6-max) —
    calling turn/river 'amber' was a real bug we fixed."""
    sys_prompt = (PROJECT_ROOT / "system-prompt.md").read_text().lower()
    assert "one rule that matters most" in sys_prompt, \
        "the front-loaded trust block must stay in the prompt"
    assert "turn" in sys_prompt and "river" in sys_prompt, \
        "prompt must name the leak streets (turn/river)"
    assert "yellow" in sys_prompt and "amber" in sys_prompt, \
        "coverage map must distinguish yellow (HU turn/river) from amber (6-max)"
