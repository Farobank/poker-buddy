"""SQLite layer for poker-buddy.

Single source of truth for the buddy's persistent memory: Bill's profile,
opponents he plays against (by his own labels — never real online IDs),
hands he's discussed, sessions, identified leaks, and a raw append-only
journal that's consolidated nightly.

Schema matches DESIGN.md. Migrations are idempotent — calling `init_db()`
multiple times is safe.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = os.environ.get(
    "BUDDY_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "buddy.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    stakes        TEXT,
    variants_json TEXT,
    study_goals   TEXT,
    updated_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS opponents (
    label             TEXT PRIMARY KEY,
    profile_tags_json TEXT,
    notes             TEXT,
    last_seen         INTEGER NOT NULL,
    hands_count       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS hands (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    format          TEXT NOT NULL,
    hand_text       TEXT,
    position        TEXT,
    board           TEXT,
    action_json     TEXT,
    opponent_label  TEXT,
    takeaway        TEXT,
    confidence      TEXT,
    ts              INTEGER NOT NULL,
    FOREIGN KEY (opponent_label) REFERENCES opponents(label)
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      INTEGER NOT NULL,
    duration_sec    INTEGER,
    hands_discussed INTEGER NOT NULL DEFAULT 0,
    summary         TEXT
);

CREATE TABLE IF NOT EXISTS leaks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    description       TEXT NOT NULL,
    severity          TEXT NOT NULL,
    last_surfaced_at  INTEGER,
    fix_status        TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS hand_journal (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    content_json TEXT NOT NULL,
    ts           INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hands_ts ON hands(ts DESC);
CREATE INDEX IF NOT EXISTS idx_journal_ts ON hand_journal(ts DESC);
CREATE INDEX IF NOT EXISTS idx_opponents_last_seen ON opponents(last_seen DESC);
"""


def init_db(db_path: str | None = None) -> str:
    """Apply schema. Idempotent. Returns the resolved path."""
    path = db_path or DEFAULT_DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    return path


@contextmanager
def connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection with row-dict factory. Always closes on exit."""
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_ts() -> int:
    """Unix seconds. Used as the canonical timestamp everywhere."""
    return int(time.time())
