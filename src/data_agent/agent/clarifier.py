from __future__ import annotations

import re
from dataclasses import dataclass

from data_agent.data_catalog import load_catalog_rules


TIME_RE = re.compile(
    r"(\d{4}\s*年\s*\d{1,2}\s*月|\d{4}-\d{1,2}(-\d{1,2})?|"
    r"\d{1,2}\s*月|今天|昨天|前天|本周|上周|本月|上月|最近\s*\d+\s*(天|周|月)|"
    r"近\s*\d+\s*(天|周|月))",
    re.IGNORECASE,
)
ASIN_RE = re.compile(r"\bB0[A-Z0-9]{8}\b", re.IGNORECASE)
SKU_RE = re.compile(r"\bSKU[:：]?\s*[A-Za-z0-9][A-Za-z0-9._-]{2,}\b", re.IGNORECASE)
PRODUCT_REFERENCE_RE = re.compile(
    r"(这个|该)\s*(asin|sku|产品|商品)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Clarification:
    needed: bool
    question: str = ""
    reason: str = ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _context_text(history: list[dict]) -> str:
    return "\n".join(
        str(item.get("content", ""))
        for item in history[-6:]
        if item.get("role") in {"user", "assistant"}
    )


def _has_time(text: str) -> bool:
    return bool(TIME_RE.search(text))


def _has_product_identifier(text: str) -> bool:
    return bool(ASIN_RE.search(text) or SKU_RE.search(text))


def _is_followup(text: str) -> bool:
    return any(token in text for token in ["这个", "继续", "上面", "刚才", "它", "该asin", "该 sku"])


def needs_clarification(user_text: str, history: list[dict] | None = None) -> Clarification:
    history = history or []
    text = _normalize(user_text)
    context = _normalize(_context_text(history))
    combined = f"{context}\n{text}".strip()

    if not text:
        return Clarification(True, "请告诉我你想查询的问题。", "empty_question")

    if _is_followup(text) and context:
        combined = f"{combined}\n{context}"

    if _requires_time(text) and not _has_time(combined):
        rule = _ask_rule("missing_time_range")
        return Clarification(
            True,
            rule.get("question", "请补充查询时间范围，例如 2026年7月、上月、最近7天，或一个具体起止日期。"),
            "missing_time_range",
        )

    if _ambiguous_sales_metric(text, combined):
        return Clarification(
            True,
            "你想看的“销售额”是哪种口径：订单销售额、Business Report 销售额，还是广告归因销售额？",
            "ambiguous_sales_metric",
        )

    if _ambiguous_ad_scope(text, combined):
        rule = _ask_rule("ambiguous_ad_scope")
        return Clarification(
            True,
            rule.get("question", "你想看哪类广告：SP、SB，还是 SP+SB 汇总？"),
            "ambiguous_ad_scope",
        )

    if _ambiguous_inventory_scope(text, combined):
        rule = _ask_rule("ambiguous_inventory_scope")
        return Clarification(
            True,
            rule.get("question", "库存问题请确认口径：可售/不可售库存、库龄/库存健康、补货建议，还是库存覆盖天数？"),
            "ambiguous_inventory_scope",
        )

    if _missing_product_identifier(text, combined):
        return Clarification(
            True,
            "请补充具体 ASIN 或 SKU，这样我才能定位商品表现。",
            "missing_product_identifier",
        )

    return Clarification(False)


def _requires_time(text: str) -> bool:
    rule = _ask_rule("missing_time_range")
    skip_keywords = rule.get("skip_keywords", ["库存", "补货", "库龄", "可售", "不可售"])
    keywords = rule.get(
        "keywords",
        [
            "销售",
            "销售额",
            "销量",
            "订单",
            "sessions",
            "转化",
            "广告",
            "acos",
            "roas",
            "搜索词",
            "花费",
            "退货",
            "订阅",
            "tacos",
            "business report",
        ],
    )
    if any(token in text for token in skip_keywords):
        return False
    return any(token in text for token in keywords)


def _ambiguous_sales_metric(text: str, combined: str) -> bool:
    return False


def _ambiguous_ad_scope(text: str, combined: str) -> bool:
    rule = _ask_rule("ambiguous_ad_scope")
    keywords = rule.get("keywords", ["广告效果", "广告表现", "广告怎么样", "广告"])
    resolved = rule.get(
        "resolved_keywords",
        ["sp", "sb", "sponsored products", "sponsored brands", "sp+sb", "搜索词", "acos", "roas"],
    )
    if not any(token in text for token in keywords):
        return False
    if any(token in combined for token in resolved):
        return False
    return True


def _ambiguous_inventory_scope(text: str, combined: str) -> bool:
    rule = _ask_rule("ambiguous_inventory_scope")
    keywords = rule.get("keywords", ["库存风险", "库存怎么样", "库存情况", "库存有没有风险"])
    resolved = rule.get("resolved_keywords", ["可售", "不可售", "库龄", "库存健康", "补货", "days of supply", "覆盖"])
    if not any(token in text for token in keywords):
        return False
    if any(token in combined for token in resolved):
        return False
    return True


def _missing_product_identifier(text: str, combined: str) -> bool:
    if not PRODUCT_REFERENCE_RE.search(text):
        return False
    return not _has_product_identifier(combined)


def _ask_rule(rule_id: str) -> dict:
    rules = load_catalog_rules().get("ask_user_about", [])
    return next((rule for rule in rules if rule.get("id") == rule_id), {})
