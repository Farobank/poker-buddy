"""Schema + migration tests."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.db import SCHEMA, connect, init_db, now_ts


@pytest.fixture
def tmp_db():
    with tempfile.TemporaryDirectory() as d:
        yield str(Path(d) / "test.db")


def test_init_db_creates_all_tables(tmp_db):
    init_db(tmp_db)
    with sqlite3.connect(tmp_db) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"profile", "opponents", "hands", "sessions", "leaks", "hand_journal"}.issubset(names)


def test_init_db_is_idempotent(tmp_db):
    init_db(tmp_db)
    init_db(tmp_db)
    init_db(tmp_db)
    # No error means we're good.


def test_connect_rolls_back_on_error(tmp_db):
    init_db(tmp_db)
    with pytest.raises(sqlite3.IntegrityError):
        with connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO opponents (label, last_seen) VALUES (?, ?)",
                ("test", now_ts()),
            )
            # Second insert with same PK triggers IntegrityError → rollback.
            conn.execute(
                "INSERT INTO opponents (label, last_seen) VALUES (?, ?)",
                ("test", now_ts()),
            )
    with connect(tmp_db) as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM opponents").fetchone()["c"]
    assert n == 0  # First insert was rolled back along with the failing second.


def test_profile_singleton_check(tmp_db):
    """The profile table is constrained to a single row (id=1)."""
    init_db(tmp_db)
    with connect(tmp_db) as conn:
        conn.execute(
            "INSERT INTO profile (id, stakes, updated_at) VALUES (1, '$1/$2', ?)",
            (now_ts(),),
        )
    with pytest.raises(sqlite3.IntegrityError):
        with connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO profile (id, stakes, updated_at) VALUES (2, '$2/$5', ?)",
                (now_ts(),),
            )


def test_now_ts_is_unix_seconds():
    import time as _time
    t = now_ts()
    assert abs(t - int(_time.time())) < 2


def test_foreign_keys_enforced(tmp_db):
    """hands.opponent_label must reference opponents.label."""
    init_db(tmp_db)
    with pytest.raises(sqlite3.IntegrityError):
        with connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO hands (format, opponent_label, ts) VALUES (?, ?, ?)",
                ("hu", "nonexistent_villain", now_ts()),
            )
