"""PD-5: retrieve similar past successful queries for few-shot prompting.

Searches query_logs.sqlite3 for status='success' rows whose user_text
resembles the current question (keyword Jaccard similarity), returns up to
`limit` {question, sql} dicts.

Failures (DB locked, file missing, etc.) are non-fatal: callers should
catch and proceed without few-shot. Designed to be cheap — no embeddings,
no external deps.
"""
from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

from data_agent.config import get_settings


_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
_STOPWORD_LEN = 2  # tokens shorter than this are ignored (e.g. "的", "是", "5")


def _db_path() -> Path:
    return Path(get_settings().query_log_db_path)


@lru_cache(maxsize=1)
def _cached_success_rows() -> tuple[tuple[set[str], str, str], ...]:
    """Load all successful question/SQL pairs once per process.

    Returns tuples of (token_set, question, sql). Cached because the table
    grows slowly relative to query rate; for very high traffic, swap to a
    periodic refresh or a proper index.
    """
    path = _db_path()
    if not path.exists():
        return ()
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT user_text, sql
            FROM query_events
            WHERE status = 'success'
              AND sql IS NOT NULL
              AND length(sql) > 0
              AND user_text IS NOT NULL
              AND length(user_text) > 0
            """
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return ()

    result: list[tuple[set[str], str, str]] = []
    for row in rows:
        question = row["user_text"]
        sql = row["sql"]
        tokens = _tokenize(question)
        if tokens:
            result.append((tokens, question, sql))
    return tuple(result)


def _tokenize(text: str) -> set[str]:
    """Lower-cased significant tokens. Splits ASCII on non-alphanumerics;
    CJK characters become single-char tokens (good enough for short business
    queries where exact-word overlap is rare)."""
    if not text:
        return set()
    text = text.lower()
    # Pull ASCII words.
    ascii_tokens = {
        t for t in _TOKEN_SPLIT_RE.split(text) if len(t) > _STOPWORD_LEN
    }
    # Pull individual CJK chars (Unicode range). Cheap, deterministic.
    cjk_chars = {
        ch for ch in text if "\u4e00" <= ch <= "\u9fff"
    }
    return ascii_tokens | cjk_chars


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def find_similar_success_queries(
    question: str,
    limit: int = 2,
    min_score: float = 0.2,
) -> list[dict[str, str]]:
    """Return up to `limit` similar past {question, sql} pairs.

    A pair is included only when its Jaccard score against `question` is at
    least `min_score`, to avoid injecting unrelated noise.
    """
    if not question:
        return []
    question_tokens = _tokenize(question)
    if not question_tokens:
        return []

    scored: list[tuple[float, str, str]] = []
    for tokens, q, sql in _cached_success_rows():
        score = _jaccard(question_tokens, tokens)
        if score >= min_score:
            scored.append((score, q, sql))

    scored.sort(key=lambda item: -item[0])
    return [{"question": q, "sql": sql} for _, q, sql in scored[:limit]]
