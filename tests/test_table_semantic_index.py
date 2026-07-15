import json
from pathlib import Path

from data_agent.agent.prompt_builder import build_messages

from scripts.build_table_semantic_index import build_index, tokenize


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "src" / "data_agent" / "data_catalog"


def test_semantic_tokenizer_handles_cjk_bigrams_and_snake_case() -> None:
    tokens = set(tokenize("Brumate GMV营收走势 ordered_revenue"))

    assert {"brumate", "gmv", "ordered_revenue", "ordered", "revenue"} <= tokens
    assert {"营收", "走势"} <= tokens


def test_generated_semantic_index_covers_order_revenue_aliases() -> None:
    index = json.loads((CATALOG_DIR / "table_semantic_index.json").read_text(encoding="utf-8"))
    table = index["tables"]["intermediate_amazon_3p_orders_brumate_view"]
    tokens = table["tokens"]

    assert index["table_count"] == 462
    assert "ordered_revenue" in tokens
    assert "营收" in tokens
    assert "gmv" in tokens
    assert "销售额" in tokens


def test_semantic_index_builder_does_not_overweight_scope_aliases() -> None:
    metadata = {
        "tables": [
            {
                "table": "intermediate_amazon_3p_orders_brumate_view",
                "domain": "orders",
                "select_permission": True,
                "scope_token": "brumate",
                "keywords": [],
            }
        ]
    }
    columns = {
        "tables": {
            "intermediate_amazon_3p_orders_brumate_view": {
                "metric_columns": {"ordered_revenue": "ordered revenue (numeric)"},
                "dimension_columns": {},
            }
        }
    }
    scope_aliases = {"scopes": {"brumate": {"aliases": ["bru mate", "brümate"]}}}

    index = build_index(metadata, columns, scope_aliases)
    tokens = index["tables"]["intermediate_amazon_3p_orders_brumate_view"]["tokens"]

    assert "营收" in tokens
    assert "gmv" in tokens
    assert "bru" not in tokens
    assert "brümate" not in tokens


def test_semantic_routing_for_long_tail_sales_and_br_questions() -> None:
    sales_system = build_messages([], "Brumate 2026年6月 GMV 趋势")[0]["content"]
    br_system = build_messages([], "Brumate 2026年6月为什么用户不点进购物车")[0]["content"]

    assert "## intermediate_amazon_3p_orders_brumate_view" in sales_system
    assert "## intermediate_amazon_3p_sales_and_traffic_brumate_view" not in sales_system
    assert "## intermediate_amazon_3p_sales_and_traffic_brumate_view" in br_system
    assert "## intermediate_amazon_3p_orders_brumate_view" not in br_system
