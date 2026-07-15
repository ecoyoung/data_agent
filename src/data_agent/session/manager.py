from __future__ import annotations

import time
from collections import defaultdict
from threading import RLock
from typing import Any


SESSION_TTL = 3600
MAX_HISTORY_MESSAGES = 40

_sessions: dict[str, dict[str, Any]] = defaultdict(
    lambda: {"history": [], "last_active": 0.0}
)
_sessions_lock = RLock()


def get_session(session_id: str) -> dict[str, Any]:
    with _sessions_lock:
        session = _sessions[session_id]
        session["last_active"] = time.time()
        return session


def get_history(session_id: str) -> list[dict]:
    with _sessions_lock:
        return list(get_session(session_id)["history"])


def add_to_history(session_id: str, role: str, content: str) -> None:
    with _sessions_lock:
        session = get_session(session_id)
        session["history"].append({"role": role, "content": content})
        if len(session["history"]) > MAX_HISTORY_MESSAGES:
            session["history"] = session["history"][-MAX_HISTORY_MESSAGES:]


def clear_session(session_id: str) -> None:
    with _sessions_lock:
        _sessions.pop(session_id, None)


def cleanup_expired() -> None:
    now = time.time()
    with _sessions_lock:
        expired = [
            session_id
            for session_id, session in _sessions.items()
            if now - session["last_active"] > SESSION_TTL
        ]
        for session_id in expired:
            _sessions.pop(session_id, None)
