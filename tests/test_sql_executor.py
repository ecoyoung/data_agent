from data_agent.agent.sql_executor import execute_query, validate_sql


def test_validate_sql_allows_select() -> None:
    valid, error = validate_sql("SELECT parent_asin, SUM(revenue) FROM orders GROUP BY parent_asin")
    assert valid is True
    assert error == ""


def test_validate_sql_allows_cte_select() -> None:
    valid, error = validate_sql(
        "WITH daily AS (SELECT date, revenue FROM orders) SELECT * FROM daily"
    )
    assert valid is True
    assert error == ""


def test_validate_sql_rejects_write_keyword() -> None:
    valid, error = validate_sql("DELETE FROM orders WHERE date < CURRENT_DATE")
    assert valid is False
    assert "DELETE" in error


def test_validate_sql_rejects_multiple_statements() -> None:
    valid, error = validate_sql("SELECT 1; SELECT 2")
    assert valid is False
    assert "多条 SQL" in error


def test_execute_query_rejects_business_rule_errors_before_database(monkeypatch) -> None:
    def fail_if_called():
        raise AssertionError("database connection should not be opened")

    monkeypatch.setattr("data_agent.agent.sql_executor.get_connection", fail_if_called)

    rows, columns, error = execute_query(
        """
        SELECT childasin, AVG(trafficbyasin_unitsessionpercentage)
        FROM amazon_3p_sales_and_traffic_innerbrightness
        WHERE report_date >= DATE '2026-05-01'
        GROUP BY childasin
        """
    )

    assert rows == []
    assert columns == []
    assert error is not None
    assert "业务规则校验失败" in error


def test_execute_query_repairs_month_alias_before_business_check(monkeypatch) -> None:
    seen = {"sql": ""}

    def fake_validate_business_sql(sql: str):
        seen["sql"] = sql
        return False, "stop before database"

    def fail_if_called():
        raise AssertionError("database connection should not be opened")

    monkeypatch.setattr("data_agent.agent.sql_executor.validate_business_sql", fake_validate_business_sql)
    monkeypatch.setattr("data_agent.agent.sql_executor.get_connection", fail_if_called)

    rows, columns, error = execute_query(
        """
        SELECT to_char(report_date, 'YYYY-MM') AS month, SUM(ordered_revenue) AS sales
        FROM intermediate_amazon_3p_orders_brumate_view
        WHERE report_date >= DATE '2026-06-01'
          AND report_date < DATE '2026-07-01'
          AND country_code = 'US'
        GROUP BY month
        ORDER BY month
        """
    )

    assert rows == []
    assert columns == []
    assert "GROUP BY 1" in seen["sql"]
    assert "GROUP BY month" not in seen["sql"]
    assert error == "业务规则校验失败：stop before database"
