from __future__ import annotations

from unittest.mock import MagicMock

from scripts.refresh_catalog_metadata import (
    _extract_index_columns,
    _index_columns,
    _latest_business_date,
    refresh,
)


def test_extract_index_columns_handles_composite_and_quoted() -> None:
    assert _extract_index_columns(
        "CREATE INDEX idx_x ON public.foo (a, b, c)"
    ) == ["a", "b", "c"]
    assert _extract_index_columns(
        'CREATE INDEX idx_y ON public.foo ("CamelCase", lower_col)'
    ) == ["camelcase", "lower_col"]
    assert _extract_index_columns("CREATE INDEX pk ON foo (id)") == ["id"]


def test_index_columns_skips_primary_key(mock_index_rows) -> None:
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = mock_index_rows
    conn.cursor.return_value.__enter__.return_value = cur

    result = _index_columns(conn, "some_table")
    # PK index dropped; only business index kept.
    assert result == [["date", "country_code_request", "customer_request"]]


def test_latest_business_date_tolerates_text_and_month_shapes() -> None:
    conn = MagicMock()
    cur = MagicMock()
    # First query (::date) succeeds.
    cur.fetchone.return_value = {"max": "2026-07-09"}
    conn.cursor.return_value.__enter__.return_value = cur

    assert _latest_business_date(conn, "t", "report_date") == "2026-07-09"


def test_latest_business_date_falls_back_to_to_date() -> None:
    import psycopg.errors

    conn = MagicMock()
    cur = MagicMock()
    # First two queries fail with psycopg errors, third returns a value.
    side_effects = [
        psycopg.errors.InvalidTextRepresentation("bad cast"),
        psycopg.errors.InvalidTextRepresentation("not yyyy-mm-dd"),
        {"max": "2026-05-01"},
    ]

    def side(_query, *_args):
        result = side_effects.pop(0)
        if isinstance(result, Exception):
            raise result
        cur.fetchone.return_value = result
        return None

    cur.execute.side_effect = side
    conn.cursor.return_value.__enter__.return_value = cur

    assert _latest_business_date(conn, "t", "report_month") == "2026-05-01"


def test_refresh_noop_when_already_fresh(tmp_path, monkeypatch) -> None:
    import json

    metadata = {
        "tables": [
            {
                "table": "t1",
                "select_permission": True,
                "date_field": "report_date",
                "indexed_columns": [["report_date"]],
                "latest_business_date": "2026-07-09",
            }
        ]
    }
    path = tmp_path / "tables_metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")

    monkeypatch.setattr("scripts.refresh_catalog_metadata.METADATA_PATH", path)
    # Mock helpers to return matching values so no diff produced.
    monkeypatch.setattr("scripts.refresh_catalog_metadata._index_columns", lambda c, t: [["report_date"]])
    monkeypatch.setattr("scripts.refresh_catalog_metadata._latest_business_date", lambda c, t, d: "2026-07-09")
    monkeypatch.setattr("scripts.refresh_catalog_metadata.get_connection", lambda: MagicMock())

    assert refresh() == 0
    # File unchanged.
    assert json.loads(path.read_text(encoding="utf-8")) == metadata


# Module-scope fixture data for the index-columns test.
import pytest  # noqa: E402


@pytest.fixture
def mock_index_rows() -> list[dict]:
    return [
        {
            "indexname": "t_pkey",
            "indexdef": "CREATE UNIQUE INDEX t_pkey ON public.t (id) PRIMARY KEY",
        },
        {
            "indexname": "idx_t_date_etc",
            "indexdef": "CREATE INDEX idx_t_date_etc ON public.t (date, country_code_request, customer_request)",
        },
    ]
