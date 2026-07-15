from data_agent.agent.sql_repair import repair_sql


def test_repair_sql_rewrites_month_alias_grouping() -> None:
    result = repair_sql(
        """
        SELECT to_char(report_date, 'YYYY-MM') AS month, SUM(ordered_revenue) AS sales
        FROM intermediate_amazon_3p_orders_brumate_view
        WHERE report_date >= DATE '2026-06-01'
        GROUP BY month
        ORDER BY month;
        """
    )

    assert result.changed is True
    assert "GROUP BY 1" in result.sql
    assert "ORDER BY 1" in result.sql
    assert "GROUP BY month" not in result.sql
    assert "group_by_month_alias_to_position" in result.fixes


def test_repair_sql_coerces_round_to_numeric() -> None:
    result = repair_sql(
        "SELECT ROUND(ams_spend, 2) FROM intermediate_amazon_ams_campaigns_brumate_view"
    )

    assert result.changed is True
    assert "ROUND((ams_spend)::numeric, 2)" in result.sql
    assert "coerce_round_to_numeric" in result.fixes


def test_repair_sql_casts_text_report_date_for_date_literal_comparison() -> None:
    result = repair_sql(
        """
        SELECT advertised_asin, SUM(ams_spend)
        FROM intermediate_amazon_ams_advertised_product_blueland_view
        WHERE report_date = DATE '2026-07-13'
        GROUP BY advertised_asin
        """
    )

    assert result.changed is True
    assert "report_date::date = DATE '2026-07-13'" in result.sql
    assert "cast_text_report_date_to_date" in result.fixes


def test_repair_sql_casts_qualified_text_report_date_range_filters() -> None:
    result = repair_sql(
        """
        SELECT t.advertised_asin, SUM(t.ams_spend)
        FROM intermediate_amazon_ams_advertised_product_blueland_view t
        WHERE t.report_date >= DATE '2026-07-01'
          AND t.report_date < DATE '2026-08-01'
          AND t.report_date IN (DATE '2026-07-13', DATE '2026-07-14')
          AND t.report_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
        GROUP BY t.advertised_asin
        """
    )

    assert "t.report_date::date >= DATE '2026-07-01'" in result.sql
    assert "t.report_date::date < DATE '2026-08-01'" in result.sql
    assert "t.report_date::date IN (DATE '2026-07-13', DATE '2026-07-14')" in result.sql
    assert "t.report_date::date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'" in result.sql


def test_repair_sql_does_not_cast_date_typed_report_date_tables() -> None:
    result = repair_sql(
        """
        SELECT SUM(ordered_revenue)
        FROM intermediate_amazon_3p_orders_brumate_view
        WHERE report_date = DATE '2026-07-13'
        """
    )

    assert "report_date::date" not in result.sql
    assert "cast_text_report_date_to_date" not in result.fixes
