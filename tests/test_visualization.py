from data_agent.visualization.chart import (
    choose_chart_columns,
    data_to_markdown_table,
    generate_bar_chart,
    generate_line_chart,
    generate_table_image,
    infer_chart_spec,
    infer_metric_column,
    is_time_series_chart,
    metric_color,
    parse_order_by_column,
    render_chart,
)
from data_agent.visualization.formatting import format_metric_value, metric_kind
from data_agent.visualization.recipes.theme import pct_color


def test_data_to_markdown_table_formats_numbers() -> None:
    table = data_to_markdown_table(
        [{"asin": "B001", "revenue": 1234.5, "units": 12}],
        ["asin", "revenue", "units"],
    )

    assert "| asin | revenue | units |" in table
    assert "1,234.50" in table
    assert "12" in table


def test_data_to_markdown_table_formats_percent_metrics() -> None:
    table = data_to_markdown_table(
        [{"asin": "B001", "conversion_rate": 0.1234, "acos": 0.4567}],
        ["asin", "conversion_rate", "acos"],
    )

    assert "12.34%" in table
    assert "45.67%" in table


def test_metric_formatting_detects_common_metric_types() -> None:
    assert metric_kind("salesbyasin_unitsordered") == "count"
    assert format_metric_value(1234.56, "ordered_product_sales_amount") == "$1,234.56"
    assert format_metric_value(0.0912, "ctr") == "9.12%"
    assert format_metric_value(1234, "sessions") == "1,234"
    assert metric_kind("sales_mom_change_pct") == "percent"
    assert metric_kind("units_mom_change_pct") == "percent"
    assert metric_kind("sales change pct") == "percent"
    assert metric_kind("units change pct") == "percent"
    assert format_metric_value(0.104, "sales_mom_change_pct") == "10.40%"
    assert format_metric_value(0.08, "units_mom_change_pct") == "8.00%"
    assert format_metric_value(-0.07, "sales change pct") == "-7.00%"
    assert format_metric_value(float("nan"), "sales_change_pct") == "-"
    assert pct_color(float("nan")) == "#6B7280"


def test_choose_chart_columns_uses_text_dimension_and_numeric_metric() -> None:
    columns = choose_chart_columns(
        [{"parent_asin": "P1", "revenue": 100.0}],
        ["parent_asin", "revenue"],
    )

    assert columns == ("parent_asin", "revenue")


def test_choose_chart_columns_prefers_order_by_column() -> None:
    data = [
        {"asin": "B001", "ad_spend": 120.0, "br_sales": 500.0, "acos": 0.24},
        {"asin": "B002", "ad_spend": 80.0, "br_sales": 900.0, "acos": 0.09},
    ]
    columns = ["asin", "ad_spend", "br_sales", "acos"]

    assert choose_chart_columns(data, columns, prefer_y="ad_spend") == ("asin", "ad_spend")
    assert choose_chart_columns(data, columns) == ("asin", "acos")


def test_parse_order_by_column_handles_prefix_and_desc() -> None:
    sql = (
        "SELECT t.advertised_asin AS asin, ROUND(t.ad_spend::numeric, 2) AS ad_spend\n"
        "FROM top10_spend t\n"
        "ORDER BY t.ad_spend DESC;"
    )

    assert parse_order_by_column(sql) == "ad_spend"


def test_parse_order_by_column_returns_none_without_order_by() -> None:
    assert parse_order_by_column("SELECT 1") is None
    assert parse_order_by_column("") is None


def test_infer_metric_column_prefers_user_intent_over_order_by() -> None:
    columns = ["asin", "ad_spend", "br_sales", "acos"]
    user_text = "2026年6月，广告花费最多的10个asin，以及他们的Business Report销售额和acos"

    assert infer_metric_column(user_text, columns) == "ad_spend"


def test_infer_metric_column_distinguishes_ad_sales_vs_ad_spend() -> None:
    columns = ["asin", "ad_spend", "ad_sales"]

    assert infer_metric_column("广告销售额最高的 ASIN", columns) == "ad_sales"
    assert infer_metric_column("广告花费最高的 ASIN", columns) == "ad_spend"


def test_infer_metric_column_returns_none_when_no_match() -> None:
    assert infer_metric_column("随便看看", ["asin", "ad_spend"]) is None
    assert infer_metric_column("销售额", ["asin", "sessions"]) is None


def test_choose_chart_columns_falls_back_when_prefer_y_missing() -> None:
    data = [{"asin": "B001", "sessions": 100, "clicks": 50}]
    # User asked about "impressions" but result has no such column → fallback to last numeric.
    assert choose_chart_columns(data, ["asin", "sessions", "clicks"], prefer_y="impressions") == (
        "asin",
        "clicks",
    )


def test_is_time_series_chart_detects_trend_intent_and_date_axis() -> None:
    assert is_time_series_chart("Brumate 2026年6月份订单销售额趋势", "report_date", 30) is True
    assert is_time_series_chart("看一下销量", "report_date", 30) is True
    assert is_time_series_chart("广告花费最多的 ASIN", "asin", 10) is False


def test_generate_bar_chart_returns_png_for_percent_metric() -> None:
    chart = generate_bar_chart(
        [
            {"asin": "B001", "conversion_rate": 0.1234},
            {"asin": "B002", "conversion_rate": 0.0834},
        ],
        x_col="asin",
        y_col="conversion_rate",
        title="Conversion Rate",
    )

    assert chart.startswith(b"\x89PNG")


def test_generate_line_chart_returns_png_for_daily_trend() -> None:
    chart = generate_line_chart(
        [
            {"report_date": "2026-06-01", "sales": 100.0},
            {"report_date": "2026-06-02", "sales": 120.0},
            {"report_date": "2026-06-03", "sales": 90.0},
        ],
        x_col="report_date",
        y_cols=["sales"],
        title="Sales Trend",
    )

    assert chart.startswith(b"\x89PNG")


def test_generate_table_image_returns_png_with_full_columns() -> None:
    table = generate_table_image(
        [
            {
                "month": "2026-06",
                "sales": 2798375.54,
                "units": 172429,
                "sales_change": -198977.95,
                "sales_change_pct": -0.0664,
                "units_change": -9414,
                "units_change_pct": -0.0518,
            }
        ],
        [
            "month",
            "sales",
            "units",
            "sales_change",
            "sales_change_pct",
            "units_change",
            "units_change_pct",
        ],
    )

    assert table.startswith(b"\x89PNG")


def test_infer_chart_spec_uses_policy_for_time_series() -> None:
    spec = infer_chart_spec(
        user_text="BKN US 2026年6月销售额趋势",
        data=[
            {"report_date": "2026-06-01", "ordered_revenue": 100.0},
            {"report_date": "2026-06-02", "ordered_revenue": 120.0},
            {"report_date": "2026-06-03", "ordered_revenue": 90.0},
        ],
        columns=["report_date", "ordered_revenue"],
        preferred_chart="auto",
        title="Sales Trend",
    )

    assert spec.chart_type == "line"
    assert spec.style == "time_series"
    assert spec.x_col == "report_date"
    assert spec.y_cols == ("ordered_revenue",)
    assert spec.table_max_rows == 31


def test_infer_chart_spec_uses_time_series_for_two_month_comparison() -> None:
    spec = infer_chart_spec(
        user_text="BKN US 2026年5月和6月销售额销量环比",
        data=[
            {"month": "2026-05", "revenue": 125000.0, "units": 2500},
            {"month": "2026-06", "revenue": 138000.0, "units": 2700},
        ],
        columns=["month", "revenue", "units"],
        prefer_y="revenue",
    )

    assert spec.chart_type == "line"
    assert spec.x_col == "month"
    assert spec.y_cols == ("revenue",)
    assert spec.title == "Revenue by Month"


def test_infer_chart_spec_uses_monthly_mom_recipe_for_sales_units_change() -> None:
    rows = [
        {
            "month": "2026-05",
            "sales": 125000.0,
            "units": 2500,
            "sales_change_pct": None,
            "units_change_pct": None,
        },
        {
            "month": "2026-06",
            "sales": 138000.0,
            "units": 2700,
            "sales_change_pct": 0.104,
            "units_change_pct": 0.08,
        },
    ]
    spec = infer_chart_spec(
        user_text="BKN US 2026年5月和6月销售额销量环比",
        data=rows,
        columns=["month", "sales", "units", "sales_change_pct", "units_change_pct"],
        prefer_y="sales",
    )

    assert spec.chart_type == "recipe"
    assert spec.style == "monthly_mom_sales_units"
    assert spec.y_cols == ("sales", "units")
    assert spec.meta == {
        "sales_col": "sales",
        "units_col": "units",
        "sales_pct_col": "sales_change_pct",
        "units_pct_col": "units_change_pct",
    }
    chart = render_chart(rows, spec)
    assert chart is not None
    assert chart.startswith(b"\x89PNG")


def test_infer_chart_spec_keeps_detail_requests_as_table() -> None:
    spec = infer_chart_spec(
        user_text="BKN US 2026年6月订单明细列表",
        data=[{"report_date": "2026-06-01", "sku": "SKU-1", "ordered_revenue": 10.0}],
        columns=["report_date", "sku", "ordered_revenue"],
    )

    assert spec.chart_type == "table"
    assert render_chart([{"report_date": "2026-06-01", "ordered_revenue": 10.0}], spec) is None


def test_infer_chart_spec_uses_rank_policy_and_metric_color() -> None:
    spec = infer_chart_spec(
        user_text="广告花费最高的 ASIN",
        data=[
            {"asin": "B001", "ad_spend": 120.0, "br_sales": 500.0},
            {"asin": "B002", "ad_spend": 80.0, "br_sales": 900.0},
        ],
        columns=["asin", "ad_spend", "br_sales"],
        prefer_y="ad_spend",
    )

    assert spec.chart_type == "bar"
    assert spec.style == "category_rank"
    assert spec.x_col == "asin"
    assert spec.y_cols == ("ad_spend",)
    assert metric_color("ad_spend") == "#2563EB"
    assert metric_color("acos") == "#F97316"
