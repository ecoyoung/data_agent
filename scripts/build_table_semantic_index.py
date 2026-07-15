"""Build a lightweight local semantic index for catalog table routing.

This is PD-4-lite: it does not call an embedding service. Instead it extracts
weighted tokens from table metadata, column metadata, scope aliases, and a
small set of business aliases. Runtime routing can use these weights as a
supplement to existing keyword/scope/domain scores.

Run:
    .venv/bin/python scripts/build_table_semantic_index.py
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "src" / "data_agent" / "data_catalog"
METADATA_PATH = CATALOG_DIR / "tables_metadata.json"
COLUMNS_PATH = CATALOG_DIR / "tables_columns.json"
SCOPE_ALIASES_PATH = CATALOG_DIR / "scope_aliases.json"
OUTPUT_PATH = CATALOG_DIR / "table_semantic_index.json"

ASCII_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


DOMAIN_ALIASES: dict[str, list[str]] = {
    "orders": ["订单", "销售", "销售额", "营收", "收入", "gmv", "revenue", "ordered revenue", "ordered_revenue", "销量"],
    "business_report": [
        "business report",
        "br",
        "流量",
        "sessions",
        "session",
        "page views",
        "转化率",
        "conversion",
        "buy box",
        "购物车",
        "加购",
        "asin表现",
    ],
    "ams_campaigns": ["广告", "campaign", "活动", "花费", "spend", "acos", "roas", "tacos", "投放"],
    "ams_search_term": ["搜索词", "search term", "关键词", "keyword", "出单词", "花费没出单"],
    "ams_targeting": ["targeting", "投放词", "target", "关键词", "投放"],
    "ams_advertised_product": ["广告商品", "广告asin", "advertised asin", "advertised product", "asin广告"],
    "ams_placement": ["placement", "广告位", "top of search"],
    "dsp_product": ["dsp", "商品", "product", "roas", "广告销售"],
    "dsp_order_funnel": ["dsp", "漏斗", "funnel", "转化"],
    "fba_inventory": ["库存", "补货", "inventory", "fba", "可售天数"],
    "fba_returns": ["退货", "return", "refund", "退货原因"],
    "search_term": ["自然搜索词", "搜索词", "search term", "organic"],
}

COLUMN_ALIASES: dict[str, list[str]] = {
    "ordered_revenue": ["销售额", "营收", "收入", "gmv", "订单销售额", "ordered revenue"],
    "ordered_units": ["销量", "件数", "units", "ordered units"],
    "order_items": ["订单量", "订单数", "order items"],
    "salesbyasin_orderedproductsales_amount": ["br销售额", "business report销售额", "asin销售额"],
    "trafficbyasin_sessions": ["sessions", "流量", "访问", "会话"],
    "trafficbyasin_pageviews": ["page views", "浏览量", "页面浏览"],
    "trafficbyasin_unitsessionpercentage": ["转化率", "conversion", "unit session percentage"],
    "trafficbyasin_buyboxpercentage": ["buy box", "购物车", "buybox", "购物车占比"],
    "ams_spend": ["广告花费", "花费", "spend", "cost"],
    "ams_sales": ["广告销售额", "广告销售", "ad sales"],
    "ams_acos": ["acos", "广告成本销售比"],
    "ams_roas": ["roas", "广告投入产出"],
    "ams_click": ["点击", "click", "clicks"],
    "ams_impression": ["曝光", "impression", "impressions"],
}


def tokenize(text: str) -> list[str]:
    text = str(text or "").lower()
    tokens: list[str] = []

    for match in ASCII_TOKEN_RE.finditer(text):
        raw = match.group(0)
        tokens.append(raw)
        if "_" in raw:
            tokens.extend(part for part in raw.split("_") if len(part) >= 2)

    for match in CJK_RE.finditer(text):
        raw = match.group(0)
        if len(raw) <= 8:
            tokens.append(raw)
        if len(raw) >= 2:
            tokens.extend(raw[i : i + 2] for i in range(len(raw) - 1))

    return tokens


def _add(counter: Counter[str], value: Any, weight: float) -> None:
    for token in tokenize(str(value or "")):
        counter[token] += weight


def _table_scope_aliases(scope_token: str, scope_aliases: dict[str, Any]) -> list[str]:
    if not scope_token:
        return []
    return list(scope_aliases.get("scopes", {}).get(scope_token, {}).get("aliases", []))


def _domain_aliases(domain: str) -> list[str]:
    aliases = list(DOMAIN_ALIASES.get(domain, []))
    if domain.startswith("dsp_"):
        aliases.extend(["dsp", "display", "程序化广告"])
    if domain.startswith("ams_"):
        aliases.extend(["广告", "ams", "amazon ads"])
    return aliases


def _column_aliases(column_name: str) -> list[str]:
    aliases = list(COLUMN_ALIASES.get(column_name, []))
    if "revenue" in column_name:
        aliases.extend(["销售额", "营收", "收入", "revenue"])
    if "session" in column_name:
        aliases.extend(["sessions", "流量", "会话"])
    if "conversion" in column_name or "unitsessionpercentage" in column_name:
        aliases.extend(["转化率", "conversion"])
    if "buybox" in column_name:
        aliases.extend(["buy box", "购物车"])
    if "spend" in column_name:
        aliases.extend(["花费", "spend", "cost"])
    if "return" in column_name:
        aliases.extend(["退货", "return"])
    return aliases


def build_index(
    metadata: dict[str, Any],
    columns_catalog: dict[str, Any],
    scope_aliases: dict[str, Any],
    max_tokens_per_table: int = 90,
) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    columns_by_table = columns_catalog.get("tables", {})

    for table in metadata.get("tables", []):
        if table.get("select_permission") is not True:
            continue
        table_name = str(table.get("table") or "")
        if not table_name:
            continue

        counter: Counter[str] = Counter()
        domain = str(table.get("domain") or "")
        scope_token = str(table.get("scope_token") or "")
        table_columns = columns_by_table.get(table_name, {})

        _add(counter, table_name, 4.0)
        _add(counter, domain, 3.0)
        # Scope/brand aliases are intentionally not indexed here: runtime
        # routing already has a dedicated high-confidence scope alias score.
        # Duplicating them in the semantic score would lift every table for a
        # brand equally and make domain routing less precise.
        _add(counter, scope_token, 0.5)
        for keyword in table.get("keywords", []):
            _add(counter, keyword, 4.0)
        for alias in _domain_aliases(domain):
            _add(counter, alias, 5.0)

        for field in ("use_when", "avoid_when", "grain", "date_field"):
            _add(counter, table.get(field), 2.0)
        for field in ("purpose", "grain", "date_field"):
            _add(counter, table_columns.get(field), 2.0)

        for key in table_columns.get("business_keys", []):
            _add(counter, key, 3.0)

        for col_name, description in table_columns.get("metric_columns", {}).items():
            _add(counter, col_name, 3.0)
            _add(counter, description, 1.5)
            for alias in _column_aliases(col_name):
                _add(counter, alias, 5.0)

        for col_name, description in table_columns.get("dimension_columns", {}).items():
            _add(counter, col_name, 1.0)
            _add(counter, description, 0.5)
            for alias in _column_aliases(col_name):
                _add(counter, alias, 2.0)

        for formula_name, formula_sql in (table_columns.get("formulas") or {}).items():
            _add(counter, formula_name, 2.0)
            _add(counter, formula_sql, 1.0)

        top_tokens = dict(counter.most_common(max_tokens_per_table))
        norm = math.sqrt(sum(value * value for value in top_tokens.values())) or 1.0
        preview_parts = [
            table_name,
            domain,
            str(table.get("use_when") or table_columns.get("purpose") or ""),
            " ".join(table.get("keywords", [])[:8]),
        ]
        tables[table_name] = {
            "domain": domain,
            "scope_token": scope_token,
            "norm": round(norm, 4),
            "tokens": {token: round(weight, 3) for token, weight in top_tokens.items()},
            "text_preview": " | ".join(part for part in preview_parts if part)[:280],
        }

    return {
        "version": 1,
        "source": [
            "src/data_agent/data_catalog/tables_metadata.json",
            "src/data_agent/data_catalog/tables_columns.json",
            "src/data_agent/data_catalog/scope_aliases.json",
        ],
        "scoring": "weighted lexical semantic tokens; no external embeddings",
        "table_count": len(tables),
        "max_tokens_per_table": max_tokens_per_table,
        "tables": tables,
    }


def main() -> int:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    columns_catalog = json.loads(COLUMNS_PATH.read_text(encoding="utf-8"))
    scope_aliases = (
        json.loads(SCOPE_ALIASES_PATH.read_text(encoding="utf-8"))
        if SCOPE_ALIASES_PATH.exists()
        else {"scopes": {}}
    )
    payload = build_index(metadata, columns_catalog, scope_aliases)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")
    print(f"tables: {payload['table_count']}, max_tokens_per_table: {payload['max_tokens_per_table']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
