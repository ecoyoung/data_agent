from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from data_agent.config import get_settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS query_events (
    query_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    session_id TEXT NOT NULL,
    message_id TEXT,
    chat_id TEXT,
    user_text TEXT NOT NULL,
    status TEXT NOT NULL,
    clarification_reason TEXT,
    clarification_question TEXT,
    selected_catalog_docs TEXT,
    llm_response TEXT,
    sql TEXT,
    row_count INTEGER,
    columns_json TEXT,
    error TEXT,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS feedback_events (
    feedback_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    query_id TEXT,
    feedback TEXT NOT NULL,
    message_id TEXT,
    open_id TEXT,
    raw_action_json TEXT
);

CREATE TABLE IF NOT EXISTS message_event_claims (
    message_id TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    session_id TEXT NOT NULL,
    query_id TEXT NOT NULL,
    chat_id TEXT,
    user_text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_events_created_at ON query_events(created_at);
CREATE INDEX IF NOT EXISTS idx_query_events_status ON query_events(status);
CREATE INDEX IF NOT EXISTS idx_feedback_events_query_id ON feedback_events(query_id);
CREATE INDEX IF NOT EXISTS idx_message_event_claims_session_id ON message_event_claims(session_id);
"""


def _db_path() -> Path:
    path = Path(get_settings().query_log_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    return conn


def create_query_event(
    *,
    session_id: str,
    user_text: str,
    message_id: str = "",
    chat_id: str = "",
) -> str:
    query_id = uuid4().hex
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO query_events (
                query_id, session_id, message_id, chat_id, user_text, status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (query_id, session_id, message_id, chat_id, user_text, "received"),
        )
    return query_id


def claim_message_query_event(
    *,
    session_id: str,
    user_text: str,
    message_id: str,
    chat_id: str = "",
) -> tuple[str, bool]:
    """Atomically claim a Feishu message and create its query event.

    Returns ``(query_id, True)`` when this process owns the message. Returns
    ``(existing_query_id, False)`` for duplicate deliveries, including
    duplicates across worker processes or after service restart.
    """
    if not message_id:
        return (
            create_query_event(
                session_id=session_id,
                user_text=user_text,
                message_id=message_id,
                chat_id=chat_id,
            ),
            True,
        )

    query_id = uuid4().hex
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT query_id FROM message_event_claims WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        if existing:
            return str(existing["query_id"]), False

        conn.execute(
            """
            INSERT INTO message_event_claims (
                message_id, session_id, query_id, chat_id, user_text
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, session_id, query_id, chat_id, user_text),
        )
        conn.execute(
            """
            INSERT INTO query_events (
                query_id, session_id, message_id, chat_id, user_text, status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (query_id, session_id, message_id, chat_id, user_text, "received"),
        )
    return query_id, True


def update_query_event(query_id: str, **fields: Any) -> None:
    if not fields:
        return

    fields["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    normalized = {key: _serialize(value) for key, value in fields.items()}
    assignments = ", ".join(f"{key} = ?" for key in normalized)
    values = list(normalized.values()) + [query_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE query_events SET {assignments} WHERE query_id = ?",
            values,
        )


def record_feedback(
    *,
    query_id: str,
    feedback: str,
    message_id: str = "",
    open_id: str = "",
    raw_action: dict | None = None,
) -> str:
    feedback_id = uuid4().hex
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO feedback_events (
                feedback_id, query_id, feedback, message_id, open_id, raw_action_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                query_id,
                feedback,
                message_id,
                open_id,
                json.dumps(raw_action or {}, ensure_ascii=False),
            ),
        )
    return feedback_id


def get_query_event(query_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM query_events WHERE query_id = ?",
            (query_id,),
        ).fetchone()
    return dict(row) if row else None


def list_feedback(query_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback_events WHERE query_id = ? ORDER BY created_at",
            (query_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)
