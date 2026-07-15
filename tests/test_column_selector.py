from __future__ import annotations

from data_agent.agent.column_selector import load_tables_columns, select_columns


def _advertised_product_meta() -> dict:
    return load_tables_columns()["tables"][
        "intermediate_amazon_ams_advertised_product_innerbrightness_view"
    ]


def test_select_always_includes_structural_columns() -> None:
    """Even with an empty question, structural columns (date + business keys +
    required filters) must be exposed."""
    meta = _advertised_product_meta()
    selected = select_columns("", "t", meta)

    assert "report_date" in selected  # date_field
    assert "advertised_asin" in selected  # business_key
    assert "country_code" in selected  # required_filter
    assert "customer" in selected


def test_select_matches_question_keyword_to_metric_column() -> None:
    """'广告花费' should pull in `ams_spend` via metric_synonyms.json mapping."""
    meta = _advertised_product_meta()
    selected = select_columns("广告花费最多的 ASIN", "t", meta)

    assert "ams_spend" in selected


def test_select_includes_ad_type_column_for_sp_sd_questions() -> None:
    meta = load_tables_columns()["tables"][
        "intermediate_amazon_ams_advertised_product_blueland_view"
    ]
    selected = select_columns("blueland 2026-07-13 每个产品asin的sp+sd广告花费和销售额", "t", meta)

    assert "ams_type" in selected


def test_select_includes_formula_inputs_when_formula_named() -> None:
    """Asking for ACoS must pull in both ams_spend and ams_sales."""
    meta = _advertised_product_meta()
    selected = select_columns("看 acos", "t", meta)

    assert "ams_spend" in selected
    assert "ams_sales" in selected


def test_select_does_not_include_unrelated_metrics() -> None:
    """A question about clicks should not pull in `ams_sales` unless needed."""
    meta = _advertised_product_meta()
    selected = select_columns("impressions and clicks", "t", meta)

    assert "ams_impression" in selected
    assert "ams_click" in selected
    # ams_sales only matches via formula inputs or explicit mention; here
    # neither applies, so it should be absent.
    assert "ams_sales" not in selected


def test_select_handles_unknown_table_gracefully() -> None:
    """An empty / unknown table_meta should not raise."""
    selected = select_columns("anything", "missing_table", {})
    assert selected == set()


def test_tables_columns_json_covers_all_cataloged_tables() -> None:
    """Every table in tables_metadata.json should also have a structured
    entry in tables_columns.json — otherwise the .md fallback kicks in and
    progressive disclosure silently regresses."""
    import json
    from pathlib import Path

    catalog_dir = Path(__file__).resolve().parent.parent / "src" / "data_agent" / "data_catalog"
    metadata = json.loads((catalog_dir / "tables_metadata.json").read_text(encoding="utf-8"))
    columns = load_tables_columns()

    metadata_tables = {t["table"] for t in metadata["tables"] if t.get("select_permission")}
    json_tables = set(columns.get("tables", {}).keys())

    missing = sorted(metadata_tables - json_tables)
    assert not missing, f"tables missing from tables_columns.json: {missing}"
