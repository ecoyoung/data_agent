"""Build Data Catalog JSON from intermediate_amazon_* PostgreSQL objects.

The intermediate views are the canonical multi-brand Amazon reporting layer.
This script reads only PostgreSQL system catalogs and writes the structured
catalog files used by prompt_builder and sql_checker.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_agent.agent.sql_executor import get_connection


CATALOG_DIR = SRC / "data_agent" / "data_catalog"
METADATA_PATH = CATALOG_DIR / "tables_metadata.json"
TABLES_COLUMNS_PATH = CATALOG_DIR / "tables_columns.json"
ALLOWED_COLUMNS_PATH = CATALOG_DIR / "allowed_columns.json"

FAMILY_PATTERNS: list[tuple[str, str, str, list[str], str]] = [
    (
        r"^intermediate_amazon_1p_orders",
        "1p_orders",
        "1P orders",
        ["1p", "vendor", "订单", "orders"],
        "1P/Vendor 订单数据，用于 Vendor 订单、销售和时间汇总。",
    ),
    (
        r"^intermediate_amazon_3p_orders",
        "orders",
        "3P order summary",
        ["3p", "seller", "订单", "orders", "销售额", "销量", "tacos"],
        "3P/Seller 订单汇总，用于订单销售额、销量、SKU/ASIN 表现。",
    ),
    (
        r"^intermediate_amazon_3p_sales_and_traffic",
        "business_report",
        "Business Report",
        ["business report", "sessions", "page views", "转化率", "流量"],
        "Business Report ASIN 销售与流量，用于 Sessions、Page Views、转化率和 BR 销售。",
    ),
    (
        r"^intermediate_amazon_ams_campaigns_placement",
        "ams_placement",
        "AMS placement report",
        ["广告位", "placement", "top of search", "ams", "sp", "sb"],
        "AMS 广告位表现，用于 top of search、placement、广告位花费和销售。",
    ),
    (
        r"^intermediate_amazon_ams_campaigns",
        "ams_campaigns",
        "AMS campaign report",
        ["广告", "campaign", "ams", "sp", "sb", "花费", "acos", "roas", "tacos"],
        "AMS campaign 汇总，用于广告花费、销售、ACoS、ROAS 和 Campaign 维度分析。",
    ),
    (
        r"^intermediate_amazon_ams_search_term|^intermediate_amazon_search_term",
        "ams_search_terms",
        "AMS search term report",
        ["搜索词", "search term", "关键词", "ams", "sp", "sb"],
        "AMS 搜索词表现，用于搜索词花费、销售、转化和无效花费分析。",
    ),
    (
        r"^intermediate_amazon_ams_targeting",
        "ams_targeting",
        "AMS targeting report",
        ["targeting", "投放词", "关键词", "asin targeting", "ams"],
        "AMS targeting 表现，用于投放词、关键词、ASIN 定向表现分析。",
    ),
    (
        r"^intermediate_amazon_ams_advertised_product|^intermediate_amazon_ads_sp_sd_advertised",
        "ams_advertised_product",
        "AMS advertised product report",
        ["advertised product", "asin", "sku", "广告商品", "ams", "sp", "sd"],
        "AMS advertised product ASIN/SKU 粒度表现，用于广告商品花费、销售和转化。",
    ),
    (
        r"^intermediate_amazon_ams_audience|^intermediate_amazon_ads_ad_campaign|^intermediate_amazon_ads_dsp_campaign_ad",
        "ads_audience_campaign",
        "Ads audience/campaign report",
        ["audience", "受众", "campaign", "广告"],
        "广告受众或 Campaign 补充报表，用于受众和活动表现分析。",
    ),
    (
        r"^intermediate_amazon_dsp_",
        "dsp",
        "DSP report",
        ["dsp", "programmatic", "展示广告", "漏斗", "audience", "product"],
        "Amazon DSP 中间表，用于 DSP 花费、展示、点击、购买、ROAS、漏斗和商品分析。",
    ),
    (
        r"^intermediate_amazon_fba_returns",
        "returns",
        "FBA returns",
        ["退货", "return", "fba", "退货原因"],
        "FBA 退货汇总，用于退货数量、原因、状态和 SKU/ASIN 退货排行。",
    ),
    (
        r"^intermediate_amazon_fba_inventory_days",
        "inventory_days",
        "FBA inventory days",
        ["库存", "inventory", "days of supply", "补货"],
        "FBA 库存天数/覆盖相关中间表，用于库存覆盖和补货风险。",
    ),
]

DATE_FIELD_PRIORITY = (
    "report_date",
    "return_date",
    "snapshot_date",
    "purchase_date",
    "shipment_date",
    "date",
    "order_date",
    "report_month",
)
IDENTITY_COLUMNS = {
    "report_date",
    "return_date",
    "snapshot_date",
    "purchase_date",
    "shipment_date",
    "date",
    "year",
    "quarter",
    "month",
    "brand",
    "customer",
    "customer_name",
    "country",
    "country_code",
    "profile_name",
    "model",
    "report_type",
    "ams_type",
    "ads_type",
    "ad_type",
    "vcc",
}
BUSINESS_KEY_HINTS = (
    "asin",
    "sku",
    "campaign_id",
    "campaign_name",
    "ad_group_name",
    "search_term",
    "targeting",
    "order_id",
    "order_name",
    "profile_name",
)


def fetch_catalog_rows() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    n.nspname AS schema_name,
                    c.relname AS table_name,
                    CASE c.relkind
                        WHEN 'r' THEN 'table'
                        WHEN 'p' THEN 'partitioned table'
                        WHEN 'v' THEN 'view'
                        WHEN 'm' THEN 'materialized view'
                        WHEN 'f' THEN 'foreign table'
                        ELSE c.relkind::text
                    END AS object_type,
                    pg_catalog.has_table_privilege(c.oid, 'SELECT') AS can_select,
                    CASE WHEN c.reltuples >= 0 THEN c.reltuples::bigint ELSE NULL END AS estimated_rows
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND n.nspname = 'public'
                  AND c.relname LIKE 'intermediate_amazon\\_%%' ESCAPE '\\'
                ORDER BY c.relname;
                """
            )
            tables = list(cur.fetchall())

            cur.execute(
                """
                SELECT
                    c.relname AS table_name,
                    a.attnum AS ordinal_position,
                    a.attname AS column_name,
                    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
                WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND n.nspname = 'public'
                  AND c.relname LIKE 'intermediate_amazon\\_%%' ESCAPE '\\'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY c.relname, a.attnum;
                """
            )
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in cur.fetchall():
                grouped.setdefault(row["table_name"], []).append(row)
            return tables, grouped
    finally:
        conn.close()


def infer_family(table_name: str) -> tuple[str, str, list[str], str]:
    for pattern, domain, grain, keywords, purpose in FAMILY_PATTERNS:
        if re.search(pattern, table_name):
            return domain, grain, keywords, purpose
    return (
        "amazon_intermediate",
        "Amazon intermediate report",
        ["amazon", "intermediate"],
        "Amazon 中间表，用于多品牌、多店铺报表分析。",
    )


def date_field(columns: list[dict[str, Any]]) -> str | None:
    names = {row["column_name"] for row in columns}
    for candidate in DATE_FIELD_PRIORITY:
        if candidate in names:
            return candidate
    return None


def is_numeric(data_type: str) -> bool:
    text = data_type.lower()
    return any(token in text for token in ("numeric", "integer", "bigint", "double precision", "real"))


def describe_column(column_name: str) -> str:
    replacements = {
        "ams": "AMS",
        "dsp": "DSP",
        "asin": "ASIN",
        "sku": "SKU",
        "roas": "ROAS",
        "acos": "ACoS",
        "ctr": "CTR",
        "cpc": "CPC",
        "cvr": "CVR",
        "dpv": "Detail Page View",
        "ntb": "New-to-brand",
        "atc": "Add to Cart",
    }
    words = [replacements.get(part, part) for part in column_name.split("_")]
    return " ".join(words)


def business_keys(columns: list[dict[str, Any]]) -> list[str]:
    names = [row["column_name"] for row in columns]
    result = [
        name
        for name in names
        if any(hint == name or hint in name for hint in BUSINESS_KEY_HINTS)
    ]
    return result[:8]


def required_filters(columns: list[dict[str, Any]]) -> list[str]:
    names = {row["column_name"] for row in columns}
    return [
        name
        for name in ("country_code", "country", "customer", "customer_name", "brand", "profile_name")
        if name in names
    ][:4]


def default_filter_values(filters: list[str]) -> dict[str, str]:
    values = {
        "country_code": "US",
        "country": "US",
        "profile_name": "US",
    }
    return {field: values[field] for field in filters if field in values}


def date_cast_hint(date: str | None, data_type: str | None) -> str:
    if not date:
        return ""
    lower = (data_type or "").lower()
    if any(token in lower for token in ("text", "character", "varchar", "char")):
        return f"{date}::date（原字段类型为 {data_type}，与 DATE literal 比较时必须 cast）"
    return f"{date}（按字段类型直接比较）"


def render_table_columns(table_name: str, columns: list[dict[str, Any]]) -> dict[str, Any]:
    domain, grain, _, purpose = infer_family(table_name)
    date = date_field(columns)
    keys = business_keys(columns)
    filters = required_filters(columns)
    metric_columns: dict[str, str] = {}
    dimension_columns: dict[str, str] = {}

    for row in columns:
        name = row["column_name"]
        desc = f"{describe_column(name)} ({row['data_type']})"
        if is_numeric(row["data_type"]) and name not in IDENTITY_COLUMNS and name != date:
            metric_columns[name] = desc
        else:
            dimension_columns[name] = desc

    formulas = {
        "acos": "ROUND((SUM(ams_spend) / NULLIF(SUM(ams_sales), 0))::numeric, 4)",
        "roas": "ROUND((SUM(ams_sales) / NULLIF(SUM(ams_spend), 0))::numeric, 4)",
        "ctr": "ROUND((SUM(ams_click) / NULLIF(SUM(ams_impression), 0))::numeric, 4)",
        "cvr": "ROUND((SUM(ams_orders) / NULLIF(SUM(ams_click), 0))::numeric, 4)",
        "tacos": "ROUND((SUM(ams_spend) / NULLIF(SUM(ordered_revenue), 0))::numeric, 4)",
    }
    available_formulas = {
        name: sql
        for name, sql in formulas.items()
        if all(token in {row["column_name"] for row in columns} for token in re.findall(r"\b(?:ams_spend|ams_sales|ams_click|ams_impression|ams_orders|ordered_revenue)\b", sql))
    }

    return {
        "domain": domain,
        "purpose": purpose,
        "grain": grain,
        "date_field": date,
        "date_field_type": next((row["data_type"] for row in columns if row["column_name"] == date), None),
        "date_cast_hint": date_cast_hint(
            date,
            next((row["data_type"] for row in columns if row["column_name"] == date), None),
        ),
        "filter_group": "intermediate_amazon",
        "business_keys": keys,
        "required_filters": filters,
        "default_filter_values": default_filter_values(filters),
        "metric_columns": metric_columns,
        "dimension_columns": dimension_columns,
        "formulas": available_formulas,
        "business_rules": [
            "所有事实查询必须带日期过滤。",
            "优先使用本 intermediate_amazon_ 中间表，不回退到旧 Innerbrightness 专用原始表。",
            "表名中的品牌/店铺 scope token 已经限定业务范围；不要再猜 brand/customer = scope token。只有用户明确给出字段值或 Catalog 提供真实取值时才加 brand/customer 过滤；字符串过滤优先使用 LOWER(field) = LOWER('<value>')。",
            "用户明确问 SP/SD/SB 或 sp+sd/sp+sb 时，必须使用表内真实广告类型字段过滤；本表若有 ams_type 则使用 LOWER(ams_type) IN (...)，不要幻觉 campaign_type。",
        ],
        "example": "",
    }


def build_payloads(
    tables: list[dict[str, Any]], columns_by_table: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    metadata_tables: list[dict[str, Any]] = []
    columns_tables: dict[str, Any] = {}
    allowed_tables: dict[str, list[str]] = {}
    domains = Counter()

    for table in tables:
        name = table["table_name"]
        columns = columns_by_table.get(name, [])
        domain, grain, keywords, purpose = infer_family(name)
        domains[domain] += 1
        date = date_field(columns)
        metadata_tables.append(
            {
                "table": name,
                "domain": domain,
                "doc": "intermediate_amazon.md",
                "select_permission": bool(table["can_select"]),
                "object_type": table["object_type"],
                "estimated_rows": table["estimated_rows"],
                "latest_business_date": None,
                "date_field": date,
                "grain": grain,
                "keywords": keywords + [name.replace("intermediate_amazon_", "").replace("_view", "")],
                "use_when": purpose,
                "avoid_when": "用户明确要求非 Amazon 数据，或需要数据库中不存在的品牌/店铺。",
                "indexed_columns": [],
            }
        )
        columns_tables[name] = render_table_columns(name, columns)
        allowed_tables[name] = [row["column_name"] for row in columns]

    metadata = {
        "generated_from": "PostgreSQL pg_catalog intermediate_amazon_% objects",
        "scope": "All selectable intermediate_amazon_ Amazon reporting objects across brands/stores",
        "default_filters": {
            "intermediate_amazon": "Use explicit brand/customer/country/profile filters only when the user asks for them or the chosen table has those columns."
        },
        "families": dict(sorted(domains.items())),
        "tables": metadata_tables,
    }
    tables_columns = {
        "version": 2,
        "_comment": "Generated by scripts/build_intermediate_catalog.py from intermediate_amazon_% objects.",
        "default_filters": {
            "intermediate_amazon": {
                "country_code": "US",
                "country": "US",
                "profile_name": "US",
            }
        },
        "tables": columns_tables,
    }
    allowed_columns = {"version": 2, "tables": allowed_tables}
    return metadata, tables_columns, allowed_columns


def write_json(path: Path, payload: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        print(f"would write {path}")
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tables, columns_by_table = fetch_catalog_rows()
    metadata, tables_columns, allowed_columns = build_payloads(tables, columns_by_table)
    print(
        f"intermediate objects: {len(tables)}, "
        f"selectable: {sum(1 for t in tables if t['can_select'])}, "
        f"columns: {sum(len(v) for v in columns_by_table.values())}"
    )
    write_json(METADATA_PATH, metadata, args.dry_run)
    write_json(TABLES_COLUMNS_PATH, tables_columns, args.dry_run)
    write_json(ALLOWED_COLUMNS_PATH, allowed_columns, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
