"""End-to-end smoke tests against the FastAPI app.

Uses TestClient (synchronous). Each endpoint is hit with a realistic payload
and the response is checked for shape.
"""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def client(monkeypatch):
    """Spin up a TestClient with an isolated DB per test."""
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("BUDDY_DB_PATH", str(Path(d) / "test.db"))
        # Disable auth middleware for the rest of the tests; the dedicated
        # test_shared_secret_blocks_when_set test re-enables it explicitly.
        # Set to "" not delenv because load_dotenv() will repopulate from .env.
        monkeypatch.setenv("BUDDY_SHARED_SECRET", "")
        # Reload db + memory + main so they pick up the env var.
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


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_root_lists_tools(client):
    r = client.get("/")
    assert r.status_code == 200
    tools = r.json()["tools"]
    assert any("preflop_lookup" in t for t in tools)
    assert any("memory_read" in t for t in tools)


def test_preflop_lookup_endpoint(client):
    r = client.post(
        "/tools/preflop_lookup",
        json={"format": "hu", "position": "btn", "hand": "AA"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["action"] == "raise"
    assert body["confidence"] in ("green", "yellow")


def test_postflop_lookup_endpoint(client):
    r = client.post(
        "/tools/postflop_lookup",
        json={
            "format": "hu",
            "hand": "KdQs",  # top pair of kings; Kd not on the board (no collision)
            "board": "Kh7d2c",
            "position": "btn",
            "line": ["btn_open_2.5", "bb_call"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["should_bet"] is True


def test_theory_lookup_endpoint(client):
    r = client.post("/tools/theory_lookup", json={"query": "range advantage", "k": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) > 0


def test_memory_write_then_read(client):
    r = client.post(
        "/tools/memory_write",
        json={
            "kind": "profile_update",
            "content": {"stakes": "$1/$2", "variants": ["hu_cash"]},
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.post("/tools/memory_read", json={"topic": "profile"})
    assert r.status_code == 200
    assert r.json()["data"]["stakes"] == "$1/$2"


def test_opponent_profile_update_endpoint(client):
    r = client.post(
        "/tools/opponent_profile_update",
        json={"label": "Russian reg", "observation": "LAG, 3bets wide"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    r = client.post("/tools/memory_read", json={"topic": "opponents"})
    labels = {o["label"] for o in r.json()["data"]}
    assert "Russian reg" in labels


def test_invalid_body_returns_422(client):
    r = client.post("/tools/preflop_lookup", json={"format": "hu"})  # missing position+hand
    assert r.status_code == 422


def test_shared_secret_blocks_when_set(client, monkeypatch):
    # Reload main with the secret enabled.
    monkeypatch.setenv("BUDDY_SHARED_SECRET", "topsecret")
    import importlib
    import backend.main as main_mod
    importlib.reload(main_mod)
    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        # Wrong secret → 401
        r = c.post(
            "/tools/preflop_lookup",
            json={"format": "hu", "position": "btn", "hand": "AA"},
        )
        assert r.status_code == 401
        # Right secret → 200
        r = c.post(
            "/tools/preflop_lookup",
            json={"format": "hu", "position": "btn", "hand": "AA"},
            headers={"X-Buddy-Secret": "topsecret"},
        )
        assert r.status_code == 200
        # Health is always open.
        assert c.get("/health").status_code == 200
