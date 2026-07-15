from data_agent.agent.sql_checker import (
    check_column_existence,
    coerce_round_to_numeric,
    referenced_tables,
    validate_business_sql,
)


def assert_invalid(sql: str, expected: str) -> None:
    valid, error = validate_business_sql(sql)

    assert valid is False
    assert expected in error


def test_referenced_tables_extracts_from_and_join_tables() -> None:
    tables = referenced_tables(
        """
        WITH sales AS (
            SELECT * FROM public.intermediate_amazon_3p_orders_innerbrightness_view
        )
        SELECT *
        FROM sales
        JOIN intermediate_amazon_ams_campaigns_innerbrightness_view ads ON true
        """
    )

    assert "intermediate_amazon_3p_orders_innerbrightness_view" in tables
    assert "intermediate_amazon_ams_campaigns_innerbrightness_view" in tables


def test_business_checker_allows_valid_business_report_sql() -> None:
    valid, error = validate_business_sql(
        """
        SELECT
            asin,
            SUM(trafficbyasin_sessions) AS sessions,
            SUM(salesbyasin_unitsordered)::numeric / NULLIF(SUM(trafficbyasin_sessions), 0) AS cvr
        FROM intermediate_amazon_3p_sales_and_traffic_innerbrightness_view
        WHERE report_date >= DATE '2026-05-01'
          AND report_date < DATE '2026-06-01'
          AND country_code = 'US'
        GROUP BY asin
        """
    )

    assert valid is True
    assert error == ""


def test_business_checker_rejects_month_alias_group_by_for_monthly_rollup() -> None:
    assert_invalid(
        """
        SELECT
            to_char(report_date, 'YYYY-MM') AS month,
            SUM(ordered_revenue) AS sales
        FROM intermediate_amazon_3p_orders_brumate_view
        WHERE report_date >= DATE '2026-06-01'
          AND report_date < DATE '2026-07-01'
          AND country_code = 'US'
        GROUP BY month
        ORDER BY month
        """,
        "不能 GROUP BY month",
    )


def test_business_checker_rejects_structured_pii_rule() -> None:
    assert_invalid(
        """
        SELECT buyer_email
        FROM intermediate_amazon_3p_orders_brumate_view
        WHERE report_date >= DATE '2026-06-01'
        """,
        "禁止展示的敏感字段",
    )


def test_business_checker_rejects_unknown_unqualified_column_in_single_table_sql() -> None:
    assert_invalid(
        """
        SELECT
            advertised_asin AS asin,
            SUM(ams_spend) AS ad_spend,
            SUM(ams_sales) AS ad_sales
        FROM intermediate_amazon_ams_advertised_product_blueland_view
        WHERE report_date::date = DATE '2026-07-13'
          AND country = 'US'
          AND LOWER(campaign_type) IN ('sp', 'sb')
        GROUP BY advertised_asin
        ORDER BY ad_spend DESC
        """,
        "不存在的列：campaign_type, country",
    )


def test_business_checker_allows_valid_unqualified_columns_in_single_table_sql() -> None:
    valid, error = validate_business_sql(
        """
        SELECT
            advertised_asin AS asin,
            SUM(ams_spend) AS ad_spend,
            SUM(ams_sales) AS ad_sales
        FROM intermediate_amazon_ams_advertised_product_blueland_view
        WHERE report_date::date = DATE '2026-07-13'
          AND country_code = 'US'
          AND LOWER(ams_type) IN ('sp', 'sb')
        GROUP BY advertised_asin
        ORDER BY ad_spend DESC
        """
    )

    assert valid is True
    assert error == ""


def test_business_checker_allows_postgres_filter_aggregate_keyword() -> None:
    valid, error = validate_business_sql(
        """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(*) FILTER (WHERE country_code = 'US') AS us_rows
        FROM intermediate_amazon_ams_advertised_product_blueland_view
        WHERE report_date::date = DATE '2026-07-13'
        """
    )

    assert valid is True
    assert error == ""


def test_business_checker_allows_monthly_rollup_group_by_position() -> None:
    valid, error = validate_business_sql(
        """
        SELECT
            to_char(report_date, 'YYYY-MM') AS month,
            SUM(ordered_revenue) AS sales
        FROM intermediate_amazon_3p_orders_brumate_view
        WHERE report_date >= DATE '2026-06-01'
          AND report_date < DATE '2026-07-01'
          AND country_code = 'US'
        GROUP BY 1
        ORDER BY 1
        """
    )

    assert valid is True
    assert error == ""


def test_business_checker_allows_case_guarded_business_report_conversion_rate() -> None:
    valid, error = validate_business_sql(
        """
        WITH daily_data AS (
            SELECT
                asin AS asin,
                report_date::date AS report_date,
                SUM(salesbyasin_unitsordered) AS units_ordered,
                SUM(trafficbyasin_sessions) AS sessions
            FROM intermediate_amazon_3p_sales_and_traffic_innerbrightness_view
            WHERE report_date::date IN (DATE '2026-06-23', DATE '2026-06-24')
              AND country_code = 'US'
            GROUP BY asin, report_date::date
        ),
        pivoted AS (
            SELECT
                asin,
                SUM(CASE WHEN report_date = DATE '2026-06-23' THEN units_ordered ELSE 0 END) AS units_23,
                SUM(CASE WHEN report_date = DATE '2026-06-24' THEN units_ordered ELSE 0 END) AS units_24,
                SUM(CASE WHEN report_date = DATE '2026-06-24' THEN sessions ELSE 0 END) AS sessions_24
            FROM daily_data
            GROUP BY asin
        )
        SELECT
            asin,
            units_23,
            units_24,
            units_24 - units_23 AS units_change,
            CASE
                WHEN sessions_24 > 0 THEN units_24::numeric / sessions_24
                ELSE 0
            END AS conversion_rate_24
        FROM pivoted
        ORDER BY units_change ASC
        LIMIT 5
        """
    )

    assert valid is True
    assert error == ""


def test_business_checker_allows_coalesce_guarded_qualified_business_report_conversion_rate() -> None:
    valid, error = validate_business_sql(
        """
        WITH
        day23 AS (
            SELECT
                asin,
                SUM(salesbyasin_unitsordered) AS units_23,
                SUM(trafficbyasin_sessions) AS sessions_23
            FROM intermediate_amazon_3p_sales_and_traffic_innerbrightness_view
            WHERE report_date = '2026-06-23'
              AND country_code = 'US'
              AND customer = 'innerbrightness'
            GROUP BY asin
        ),
        day24 AS (
            SELECT
                asin,
                SUM(salesbyasin_unitsordered) AS units_24,
                SUM(trafficbyasin_sessions) AS sessions_24
            FROM intermediate_amazon_3p_sales_and_traffic_innerbrightness_view
            WHERE report_date = '2026-06-24'
              AND country_code = 'US'
              AND customer = 'innerbrightness'
            GROUP BY asin
        )
        SELECT
            COALESCE(d23.asin, d24.asin) AS asin,
            COALESCE(d24.units_24, 0)               AS units_sold_0624,
            CASE
                WHEN COALESCE(d24.sessions_24, 0) > 0
                THEN ROUND(
                         COALESCE(d24.units_24, 0)::numeric
                         / d24.sessions_24,
                         4)
                ELSE NULL
            END                                     AS conversion_rate_0624,
            COALESCE(d24.units_24, 0)
            - COALESCE(d23.units_23, 0)             AS unit_change
        FROM day23 d23
        FULL OUTER JOIN day24 d24
            ON d23.asin = d24.asin
        WHERE COALESCE(d23.units_23, 0) > 0
           OR COALESCE(d24.units_24, 0) > 0
        ORDER BY unit_change ASC
        LIMIT 5
        """
    )

    assert valid is True
    assert error == ""


def test_business_checker_rejects_unguarded_business_report_conversion_rate() -> None:
    assert_invalid(
        """
        SELECT
            asin,
            SUM(salesbyasin_unitsordered)::numeric / SUM(trafficbyasin_sessions) AS cvr
        FROM intermediate_amazon_3p_sales_and_traffic_innerbrightness_view
        WHERE report_date >= DATE '2026-05-01'
          AND country_code = 'US'
        GROUP BY asin
        """,
        "防止除零",
    )


def test_business_checker_rejects_round_division_without_numeric_result() -> None:
    assert_invalid(
        """
        WITH top10_ads AS (
            SELECT
                advertised_asin,
                SUM(ams_spend) AS ad_spend,
                SUM(ams_sales) AS ad_sales
            FROM intermediate_amazon_ams_advertised_product_innerbrightness_view
            WHERE report_date::date >= DATE '2026-06-01'
              AND report_date::date < DATE '2026-07-01'
              AND country_code = 'US'
              AND customer = 'Inner brightness-New'
            GROUP BY advertised_asin
            ORDER BY ad_spend DESC
            LIMIT 10
        )
        SELECT
            advertised_asin,
            ROUND(ad_spend::numeric / NULLIF(ad_sales, 0), 4) AS acos
        FROM top10_ads
        """,
        "除法结果必须整体转为 numeric",
    )


def test_business_checker_allows_round_division_with_numeric_result() -> None:
    valid, error = validate_business_sql(
        """
        WITH top10_ads AS (
            SELECT
                advertised_asin,
                SUM(ams_spend) AS ad_spend,
                SUM(ams_sales) AS ad_sales
            FROM intermediate_amazon_ams_advertised_product_innerbrightness_view
            WHERE report_date::date >= DATE '2026-06-01'
              AND report_date::date < DATE '2026-07-01'
              AND country_code = 'US'
              AND customer = 'Inner brightness-New'
            GROUP BY advertised_asin
        )
        SELECT
            advertised_asin,
            ROUND((ad_spend / NULLIF(ad_sales, 0))::numeric, 4) AS acos
        FROM top10_ads
        """
    )

    assert valid is True
    assert error == ""


def test_business_checker_allows_round_division_with_numeric_denominator() -> None:
    valid, error = validate_business_sql(
        """
        SELECT
            campaign_name,
            ROUND(SUM(ams_spend)::numeric / NULLIF(SUM(ams_sales)::numeric, 0), 4) AS acos
        FROM intermediate_amazon_ams_campaigns_innerbrightness_view
        WHERE report_date::date >= DATE '2026-06-01'
          AND report_date::date < DATE '2026-07-01'
        GROUP BY campaign_name
        """
    )

    assert valid is True
    assert error == ""


def test_business_checker_rejects_catalog_unknown_table() -> None:
    assert_invalid(
        "SELECT * FROM orders WHERE date >= DATE '2026-05-01'",
        "Catalog 外或无权限表",
    )


def test_business_checker_requires_date_filter_for_fact_tables() -> None:
    assert_invalid(
        "SELECT asin, SUM(ordered_revenue) FROM intermediate_amazon_3p_orders_innerbrightness_view GROUP BY asin",
        "业务日期过滤",
    )


def test_business_checker_rejects_pii_fields() -> None:
    assert_invalid(
        """
        SELECT customer_comments
        FROM intermediate_amazon_fba_returns_belliwelli_view
        WHERE return_date >= DATE '2026-07-01'
        """,
        "敏感字段",
    )


def test_business_checker_rejects_business_report_avg_conversion_rate() -> None:
    assert_invalid(
        """
        SELECT asin, AVG(trafficbyasin_unitsessionpercentage)
        FROM intermediate_amazon_3p_sales_and_traffic_innerbrightness_view
        WHERE report_date >= DATE '2026-05-01'
        GROUP BY asin
        """,
        "不能默认 AVG",
    )


def test_coerce_round_to_numeric_casts_plain_double_column() -> None:
    sql = "SELECT ROUND(ams_spend, 2) FROM intermediate_amazon_ams_campaigns_innerbrightness_view"
    assert coerce_round_to_numeric(sql) == (
        "SELECT ROUND((ams_spend)::numeric, 2) FROM intermediate_amazon_ams_campaigns_innerbrightness_view"
    )


def test_coerce_round_to_numeric_handles_nested_function_args() -> None:
    sql = (
        "SELECT ROUND(SUM(ams_spend) / NULLIF(SUM(ams_sales), 0), 4) "
        "FROM intermediate_amazon_ams_campaigns_innerbrightness_view"
    )
    coerced = coerce_round_to_numeric(sql)
    assert "::numeric" in coerced
    # NULLIF's internal comma must not be mistaken for ROUND's argument separator.
    assert "NULLIF(SUM(ams_sales), 0)" in coerced


def test_coerce_round_to_numeric_skips_when_already_numeric() -> None:
    sql = "SELECT ROUND((ams_spend)::numeric, 2) FROM intermediate_amazon_ams_campaigns_innerbrightness_view"
    assert coerce_round_to_numeric(sql) == sql


def test_coerce_round_to_numeric_is_idempotent() -> None:
    sql = "SELECT ROUND(ad_spend, 2), ROUND(cost / NULLIF(sales, 0), 4) FROM t"
    once = coerce_round_to_numeric(sql)
    twice = coerce_round_to_numeric(once)
    assert once == twice


def test_coerce_round_to_numeric_preserves_string_literals_with_commas() -> None:
    sql = "SELECT ROUND(x, 2) FROM t WHERE reason = 'a, b'"
    coerced = coerce_round_to_numeric(sql)
    assert "'a, b'" in coerced
    assert "ROUND((x)::numeric, 2)" in coerced


def test_check_column_existence_passes_for_real_column() -> None:
    # advertised_asin is a real column on the advertised_product table.
    sql = (
        "SELECT advertised_asin AS asin, SUM(ams_spend) AS spend "
        "FROM intermediate_amazon_ams_advertised_product_innerbrightness_view t "
        "WHERE t.report_date::date >= DATE '2026-06-01' "
        "GROUP BY t.advertised_asin ORDER BY spend DESC LIMIT 5"
    )
    assert check_column_existence(sql) == []


def test_check_column_existence_flags_hallucinated_column() -> None:
    # advertised_sku_cost does not exist; the LLM sometimes invents composites.
    sql = (
        "SELECT t.advertised_asin, SUM(t.advertised_sku_cost) AS spend "
        "FROM intermediate_amazon_ams_advertised_product_innerbrightness_view t "
        "WHERE t.report_date::date >= DATE '2026-06-01' "
        "GROUP BY t.advertised_asin"
    )
    issues = check_column_existence(sql)
    assert issues
    assert any("advertised_sku_cost" in issue for issue in issues)


def test_check_column_existence_handles_cte_aliases() -> None:
    # CTE name 'spend' shadows nothing — the inner query references
    # intermediate_amazon_ams_campaigns_innerbrightness_view via alias 'c'.
    sql = (
        "WITH spend AS ("
        "  SELECT c.campaign_name, SUM(c.ams_spend) AS spend FROM intermediate_amazon_ams_campaigns_innerbrightness_view c "
        "  WHERE c.report_date::date >= DATE '2026-06-01' GROUP BY c.campaign_name"
        ") SELECT * FROM spend"
    )
    assert check_column_existence(sql) == []


def test_check_column_existence_skips_when_allowed_columns_missing(monkeypatch) -> None:
    monkeypatch.setattr("data_agent.agent.sql_checker.allowed_columns", lambda: {})
    assert check_column_existence("SELECT t.fake_col FROM intermediate_amazon_ams_campaigns_innerbrightness_view t") == []
