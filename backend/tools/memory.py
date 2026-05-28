"""Memory tools — read/write the buddy's persistent state.

Three public functions matching ConvAI tool definitions:
  - memory_read(topic)              → fetch scoped state
  - memory_write(kind, content)     → append to journal + maybe structured row
  - opponent_profile_update(...)    → upsert opponent profile

All payloads are JSON-shaped. Errors return a `note` field; callers should
never receive a thrown exception.
"""

from __future__ import annotations

import json
from typing import Any

from backend.db import connect, init_db, now_ts


# Ensure schema exists on first import in case the FastAPI app hasn't yet.
init_db()


# ---------------------------------------------------------------------------
# memory_read
# ---------------------------------------------------------------------------

_VALID_TOPICS = {"profile", "recent_leaks", "opponents", "recent_hands", "session"}


def memory_read(topic: str) -> dict[str, Any]:
    """Topic-scoped read. Topic determines which table is queried."""
    topic = (topic or "").strip().lower()
    if topic not in _VALID_TOPICS:
        return {
            "data": None,
            "note": f"Unknown topic {topic!r}. Valid: {sorted(_VALID_TOPICS)}",
        }

    if topic == "profile":
        return {"data": _read_profile()}
    if topic == "recent_leaks":
        return {"data": _read_recent_leaks(limit=10)}
    if topic == "opponents":
        return {"data": _read_opponents(limit=20)}
    if topic == "recent_hands":
        return {"data": _read_recent_hands(limit=10)}
    if topic == "session":
        return {"data": _read_latest_session()}
    return {"data": None, "note": "unreachable"}


def _read_profile() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, stakes, variants_json, study_goals, updated_at FROM profile WHERE id = 1"
        ).fetchone()
    if not row:
        return None
    return {
        "stakes": row["stakes"],
        "variants": json.loads(row["variants_json"]) if row["variants_json"] else [],
        "study_goals": row["study_goals"],
        "updated_at": row["updated_at"],
    }


def _read_recent_leaks(limit: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, description, severity, last_surfaced_at, fix_status "
            "FROM leaks WHERE fix_status != 'fixed' "
            "ORDER BY COALESCE(last_surfaced_at, 0) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def _read_opponents(limit: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT label, profile_tags_json, notes, last_seen, hands_count "
            "FROM opponents ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "label": r["label"],
            "tags": json.loads(r["profile_tags_json"]) if r["profile_tags_json"] else [],
            "notes": r["notes"],
            "last_seen": r["last_seen"],
            "hands_count": r["hands_count"],
        })
    return out


def _read_recent_hands(limit: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, format, hand_text, position, board, opponent_label, "
            "takeaway, confidence, ts FROM hands ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def _read_latest_session() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, started_at, duration_sec, hands_discussed, summary "
            "FROM sessions ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# memory_write
# ---------------------------------------------------------------------------

_VALID_KINDS = {"hand_discussed", "leak_identified", "opponent_observation", "session_note", "profile_update"}


def memory_write(kind: str, content: dict[str, Any]) -> dict[str, Any]:
    """Append to journal; mirror to a structured table when the kind matches."""
    kind = (kind or "").strip().lower()
    if kind not in _VALID_KINDS:
        return {"ok": False, "note": f"Unknown kind {kind!r}. Valid: {sorted(_VALID_KINDS)}"}

    if not isinstance(content, dict):
        return {"ok": False, "note": "content must be a dict (JSON object)."}

    ts = now_ts()
    # First transaction: journal entry + the structured table that lives in our
    # own connection scope. Opponent observation is dispatched AFTER the
    # connection closes (it opens its own connection in opponent_profile_update).
    with connect() as conn:
        conn.execute(
            "INSERT INTO hand_journal (kind, content_json, ts) VALUES (?, ?, ?)",
            (kind, json.dumps(content), ts),
        )

        if kind == "hand_discussed":
            conn.execute(
                "INSERT INTO hands (format, hand_text, position, board, action_json, "
                "opponent_label, takeaway, confidence, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    content.get("format"),
                    content.get("hand"),
                    content.get("position"),
                    content.get("board"),
                    json.dumps(content.get("action", [])),
                    content.get("opponent_label"),
                    content.get("takeaway"),
                    content.get("confidence"),
                    ts,
                ),
            )

        elif kind == "leak_identified":
            conn.execute(
                "INSERT INTO leaks (description, severity, last_surfaced_at, fix_status) "
                "VALUES (?, ?, ?, ?)",
                (
                    content.get("description", ""),
                    content.get("severity", "real"),
                    ts,
                    content.get("fix_status", "open"),
                ),
            )

        elif kind == "session_note":
            existing = conn.execute(
                "SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if existing and content.get("update_latest"):
                conn.execute(
                    "UPDATE sessions SET duration_sec = COALESCE(?, duration_sec), "
                    "hands_discussed = COALESCE(?, hands_discussed), "
                    "summary = COALESCE(?, summary) WHERE id = ?",
                    (
                        content.get("duration_sec"),
                        content.get("hands_discussed"),
                        content.get("summary"),
                        existing["id"],
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO sessions (started_at, duration_sec, hands_discussed, summary) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        content.get("started_at", ts),
                        content.get("duration_sec"),
                        content.get("hands_discussed", 0),
                        content.get("summary"),
                    ),
                )

        elif kind == "profile_update":
            conn.execute(
                "INSERT OR REPLACE INTO profile (id, stakes, variants_json, study_goals, updated_at) "
                "VALUES (1, ?, ?, ?, ?)",
                (
                    content.get("stakes"),
                    json.dumps(content.get("variants", [])),
                    content.get("study_goals"),
                    ts,
                ),
            )

    # Dispatch nested writers AFTER the journal connection closes.
    if kind == "opponent_observation":
        label = content.get("label")
        observation = content.get("observation")
        if label and observation:
            opponent_profile_update(label, observation)

    return {"ok": True, "ts": ts}


# ---------------------------------------------------------------------------
# opponent_profile_update
# ---------------------------------------------------------------------------

_KNOWN_TAGS = {
    "nit", "lag", "tag", "station", "calling_station", "maniac", "whale", "reg",
    "tight", "loose", "passive", "aggressive", "fish", "tilted",
    "3bets_wide", "3bets_tight", "fold_to_cbet", "doesn_t_fold_river",
    "limps_btn", "bluff_heavy", "value_only",
}


def opponent_profile_update(label: str, observation: str) -> dict[str, Any]:
    """Upsert an opponent. Appends the raw observation to notes; auto-tags from a
    small known-tag dictionary so the agent can read structured profile_tags later.
    """
    if not label or not label.strip():
        return {"ok": False, "note": "label is required"}
    label = label.strip()
    observation = (observation or "").strip()

    ts = now_ts()
    auto_tags = _extract_tags(observation)

    with connect() as conn:
        row = conn.execute(
            "SELECT profile_tags_json, notes, hands_count FROM opponents WHERE label = ?",
            (label,),
        ).fetchone()

        if row:
            existing_tags = set(json.loads(row["profile_tags_json"] or "[]"))
            merged_tags = sorted(existing_tags | auto_tags)
            notes = (row["notes"] or "")
            if observation and observation not in notes:
                notes = (notes + "\n" + observation).strip()
            conn.execute(
                "UPDATE opponents SET profile_tags_json = ?, notes = ?, last_seen = ?, "
                "hands_count = hands_count + 1 WHERE label = ?",
                (json.dumps(merged_tags), notes, ts, label),
            )
        else:
            conn.execute(
                "INSERT INTO opponents (label, profile_tags_json, notes, last_seen, hands_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (label, json.dumps(sorted(auto_tags)), observation, ts, 1),
            )

    return {"ok": True, "label": label, "auto_tags": sorted(auto_tags), "ts": ts}


def _extract_tags(observation: str) -> set[str]:
    """Tiny lexical match — pulls known tags out of free-text observation."""
    if not observation:
        return set()
    lowered = observation.lower()
    found: set[str] = set()
    for tag in _KNOWN_TAGS:
        # Match underscored tags by also accepting space/dash variants
        variants = {tag, tag.replace("_", " "), tag.replace("_", "-")}
        for v in variants:
            if v in lowered:
                found.add(tag)
                break
    return found
