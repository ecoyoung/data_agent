import json
import re
from pathlib import Path

from data_agent.agent.prompt_builder import (
    build_messages,
    load_data_catalog,
    select_catalog_table_docs,
)
from data_agent.agent.sql_checker import validate_business_sql


CATALOG_DIR = Path(__file__).resolve().parents[1] / "src" / "data_agent" / "data_catalog"


def _rendered_tables(system_prompt: str) -> list[str]:
    return re.findall(r"^## (intermediate_amazon_[^\n]+)$", system_prompt, flags=re.M)


def test_catalog_is_intermediate_amazon_scoped() -> None:
    catalog = load_data_catalog(select_catalog_table_docs("Belli Welli 7月订单销售额"), "Belli Welli 7月订单销售额")

    assert "intermediate_amazon_3p_orders_belliwelli_view" in catalog
    assert "`intermediate_amazon_` 中间表是当前主数据源" in catalog
    assert "旧 `amazon_*_innerbrightness` 专用表只作为历史参考" in catalog
    assert "orders.ordered_revenue" not in catalog
    assert "advertising.spend" not in catalog


def test_tables_metadata_covers_selectable_intermediate_tables() -> None:
    metadata = json.loads((CATALOG_DIR / "tables_metadata.json").read_text(encoding="utf-8"))
    tables = metadata["tables"]

    assert len(tables) == 462
    assert all(table["select_permission"] is True for table in tables)
    assert {table["doc"] for table in tables} == {"intermediate_amazon.md"}

    table_names = {table["table"] for table in tables}
    assert "intermediate_amazon_3p_orders_belliwelli_view" in table_names
    assert "intermediate_amazon_3p_sales_and_traffic_innerbrightness_view" in table_names
    assert "intermediate_amazon_ams_campaigns_belliwelli_view" in table_names
    assert "intermediate_amazon_dsp_product_belliwelli_view" in table_names


def test_catalog_routes_questions_to_intermediate_doc_and_relevant_tables() -> None:
    docs = select_catalog_table_docs("Inner brightness 7月 Business Report sessions 和转化率")
    assert docs == ["intermediate_amazon.md"]

    messages = build_messages([], "Inner brightness 7月 Business Report sessions 和转化率")
    system = messages[0]["content"]

    assert _rendered_tables(system) == [
        "intermediate_amazon_3p_sales_and_traffic_innerbrightness_view"
    ]
    assert len(system) < 20_000


def test_catalog_guides_generic_month_sales_to_order_revenue_monthly() -> None:
    messages = build_messages([], "Belli Welli 2026年6月销售额和销量")
    system = messages[0]["content"]

    assert _rendered_tables(system) == [
        "intermediate_amazon_3p_orders_belliwelli_view"
    ]
    assert "销售额 `SUM(ordered_revenue)`" in system
    assert "to_char(report_date, 'YYYY-MM') AS month" in system
    assert "不要按 `report_date` 输出 30 行日明细" in system
    assert "intent: `auto`" in system
    assert "订单月汇总" in system
    assert "Data Catalog: structured rules" in system
    assert "`generic_sales_uses_ordered_revenue`" in system


def test_catalog_guides_trend_intent_to_daily_template() -> None:
    system = build_messages([], "Brumate 2026年6月份订单销售额趋势")[0]["content"]

    assert "intent: `trend`" in system
    assert "订单日趋势" in system
    assert "GROUP BY report_date" in system
    assert "不要月汇总成一行" in system


def test_catalog_routes_ads_and_tacos_to_intermediate_tables() -> None:
    search_system = build_messages([], "Belli Welli 7月 AMS 搜索词花费没出单")[0]["content"]
    assert _rendered_tables(search_system) == [
        "intermediate_amazon_ams_search_term_belliwelli_view"
    ]

    tacos_system = build_messages([], "Belli Welli 7月 TACOS")[0]["content"]
    assert set(_rendered_tables(tacos_system)) == {
        "intermediate_amazon_3p_orders_belliwelli_view",
        "intermediate_amazon_ams_campaigns_belliwelli_view",
    }


def test_catalog_guides_blueland_sp_sd_advertised_product_filters() -> None:
    system = build_messages([], "blueland 2026-07-13 每个产品asin的sp+sd广告花费和销售额")[0]["content"]

    assert _rendered_tables(system)[0] == "intermediate_amazon_ams_advertised_product_blueland_view"
    assert "`ams_type`" in system
    assert "不要再猜 brand/customer = scope token" in system
    assert "LOWER(ams_type) IN" in system
    assert "brand=''" not in system
    assert "customer=''" not in system


def test_catalog_routes_scope_aliases_to_matching_intermediate_tables() -> None:
    vp_system = build_messages([], "VP US 7月 DSP ROAS")[0]["content"]
    assert any("_vp_us_" in table for table in _rendered_tables(vp_system))
    assert all(table.startswith("intermediate_amazon_dsp_") for table in _rendered_tables(vp_system))

    beekeeper_system = build_messages([], "Beekeeper CA 7月退货原因")[0]["content"]
    assert _rendered_tables(beekeeper_system) == [
        "intermediate_amazon_fba_returns_beekeeper_ca_view"
    ]

    inner_system = build_messages([], "Inner brightness-New 7月 AMS campaign 花费")[0]["content"]
    assert _rendered_tables(inner_system) == [
        "intermediate_amazon_ams_campaigns_innerbrightness_view"
    ]


def test_catalog_falls_back_to_intermediate_doc_for_generic_questions() -> None:
    docs = select_catalog_table_docs("帮我看看最近表现")
    assert docs == ["intermediate_amazon.md"]

    system = build_messages([], "帮我看看最近表现")[0]["content"]
    assert _rendered_tables(system)
    assert all(table.startswith("intermediate_amazon_") for table in _rendered_tables(system))
    assert "Table document: innerbrightness_ads_sp.md" not in system


def test_intermediate_tables_are_allowed_and_require_dates() -> None:
    valid, error = validate_business_sql(
        """
        SELECT report_date, SUM(ordered_revenue)
        FROM intermediate_amazon_3p_orders_belliwelli_view
        WHERE report_date >= DATE '2026-07-01'
        GROUP BY report_date
        """
    )
    assert valid is True
    assert error == ""

    valid, error = validate_business_sql(
        "SELECT SUM(ordered_revenue) FROM intermediate_amazon_3p_orders_belliwelli_view"
    )
    assert valid is False
    assert "日期过滤" in error
