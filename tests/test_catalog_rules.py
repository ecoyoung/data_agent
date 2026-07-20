from data_agent.data_catalog import (
    load_catalog_hints,
    load_relationships,
    render_catalog_hints_for_prompt,
    render_catalog_rules_for_prompt,
    load_catalog_rules,
)


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


def test_load_catalog_hints_are_intermediate_amazon_specific() -> None:
    hints = load_catalog_hints()
    ids = {hint["id"] for hint in hints["family_hints"]}

    assert "orders_default_sales" in ids
    assert "business_report_traffic_conversion" in ids
    assert "ams_advertised_product_type_filter" in ids
    assert all("shopify" not in str(hint).lower() for hint in hints["family_hints"])


def test_render_catalog_hints_includes_negative_examples() -> None:
    rendered = render_catalog_hints_for_prompt()

    assert "intermediate_amazon AI_HINT" in rendered
    assert "negative_examples" in rendered
    assert "不要幻觉 `campaign_type`" in rendered
    assert "不要把广告归因销售额 `ams_sales` 当成店铺总销售额" in rendered


def test_load_relationships_exposes_join_rules() -> None:
    relationships = load_relationships()["relationships"]
    ids = {relationship["id"] for relationship in relationships}

    assert "orders_to_ams_advertised_product_by_asin_date_scope" in ids
    assert "orders_to_ams_campaigns_by_date_scope" in ids
