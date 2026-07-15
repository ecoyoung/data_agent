from __future__ import annotations

from dataclasses import dataclass


TREND_KEYWORDS = ("趋势", "走势", "trend", "daily", "每天", "每日", "按日")
RANKING_KEYWORDS = ("排行", "排名", "top", "最多", "最高", "最低", "最大", "最小", "前")
COMPARISON_KEYWORDS = ("对比", "比较", "同比", "环比", "vs", "versus")
DETAIL_KEYWORDS = ("明细", "列表", "逐条")
SUMMARY_KEYWORDS = ("汇总", "总计", "合计", "总数据", "数据")


@dataclass(frozen=True)
class QueryIntent:
    name: str
    chart_type: str
    table_max_rows: int
    sql_guidance: str


def infer_query_intent(user_text: str) -> QueryIntent:
    text = (user_text or "").lower()

    if any(keyword in text for keyword in TREND_KEYWORDS):
        return QueryIntent(
            name="trend",
            chart_type="line",
            table_max_rows=31,
            sql_guidance=(
                "用户意图是趋势：按日期字段日粒度分组，使用 `report_date`/对应日期字段，"
                "按日期升序返回完整时间序列；不要月汇总成一行。"
            ),
        )

    if any(keyword in text for keyword in RANKING_KEYWORDS):
        return QueryIntent(
            name="ranking",
            chart_type="bar",
            table_max_rows=10,
            sql_guidance=(
                "用户意图是排行：按用户指定维度分组，按核心指标 DESC 排序；"
                "没有明确数量时默认 `LIMIT 20`。"
            ),
        )

    if any(keyword in text for keyword in COMPARISON_KEYWORDS):
        return QueryIntent(
            name="comparison",
            chart_type="bar",
            table_max_rows=20,
            sql_guidance=(
                "用户意图是对比：先把各组数据聚合到相同粒度，再 `UNION ALL` 或 JOIN；"
                "不要把不同粒度明细表直接 JOIN。"
            ),
        )

    if any(keyword in text for keyword in DETAIL_KEYWORDS):
        return QueryIntent(
            name="detail",
            chart_type="table",
            table_max_rows=30,
            sql_guidance=(
                "用户意图是明细：返回用户需要的业务键、日期和指标列；"
                "默认加合理 `LIMIT`，避免无边界明细查询。"
            ),
        )

    if any(keyword in text for keyword in SUMMARY_KEYWORDS):
        return QueryIntent(
            name="summary",
            chart_type="auto",
            table_max_rows=10,
            sql_guidance=(
                "用户意图是汇总：如果时间是整月且未要求趋势/按日，按月或总计聚合；"
                "返回少量汇总行，不要展开日明细。"
            ),
        )

    return QueryIntent(
        name="auto",
        chart_type="auto",
        table_max_rows=10,
        sql_guidance="未识别到特殊展示意图：按问题中的指标、维度和时间范围选择最小必要粒度。",
    )


def render_intent_prompt(user_text: str) -> str:
    intent = infer_query_intent(user_text)
    return (
        "# ===== Query Intent =====\n"
        f"- intent: `{intent.name}`\n"
        f"- preferred_chart: `{intent.chart_type}`\n"
        f"- table_max_rows_hint: `{intent.table_max_rows}`\n"
        f"- SQL 粒度提示: {intent.sql_guidance}"
    )
