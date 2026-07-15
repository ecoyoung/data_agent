from data_agent.data_catalog import load_catalog_rules, render_catalog_rules_for_prompt


def test_load_catalog_rules_exposes_rule_groups() -> None:
    rules = load_catalog_rules()

    assert rules["version"] == 1
    assert any(rule["id"] == "generic_sales_uses_ordered_revenue" for rule in rules["business_rules"])
    assert any(rule["id"] == "missing_time_range" for rule in rules["ask_user_about"])
    assert any(rule["id"] == "month_alias_group_by" for rule in rules["forbidden_sql"])


def test_render_catalog_rules_for_prompt_includes_rule_types() -> None:
    rendered = render_catalog_rules_for_prompt()

    assert "structured rules" in rendered
    assert "business_rule" in rendered
    assert "ask_user_about" in rendered
    assert "forbidden_sql" in rendered
    assert "SUM(ordered_revenue)" in rendered
