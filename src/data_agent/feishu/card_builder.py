from __future__ import annotations

import json
from numbers import Number
from typing import Any

from data_agent.visualization.formatting import format_metric_value


COLUMN_LABEL_MAX = 18


def _summary_element(summary: str) -> list[dict]:
    if not summary:
        return []
    text = summary.strip()
    return [{"tag": "markdown", "content": f"> {text}"}]


def _is_single_numeric_value(
    table_rows: list[dict[str, Any]] | None, columns: list[str] | None
) -> tuple[Any, str] | None:
    if not table_rows or not columns or len(table_rows) != 1 or len(columns) != 1:
        return None
    column = columns[0]
    value = table_rows[0].get(column)
    if isinstance(value, Number) and not isinstance(value, bool):
        return value, column
    return None


def build_result_card(
    title: str,
    summary: str,
    table_markdown: str,
    image_key: str | None = None,
    sql: str | None = None,
    query_id: str | None = None,
    table_rows: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    table_max_rows: int = 10,
) -> dict:
    elements: list[dict] = []

    elements.extend(_summary_element(summary))
    if summary:
        elements.append({"tag": "hr"})

    single = _is_single_numeric_value(table_rows, columns)
    if single is not None:
        value, column = single
        elements.append(
            {"tag": "markdown", "content": f"# {format_metric_value(value, column)}"}
        )
    else:
        if image_key:
            elements.append(
                {
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {"tag": "plain_text", "content": "数据图表"},
                    "mode": "fit_horizontal",
                }
            )

        if table_rows is not None and columns:
            elements.extend(build_table_elements(table_rows, columns, max_rows=table_max_rows))
        else:
            elements.append({"tag": "markdown", "content": f"```text\n{table_markdown}\n```"})

    actions = [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "看趋势图"},
            "type": "default",
            "value": {"action": "show_trend", "query_id": query_id},
        },
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "下钻明细"},
            "type": "default",
            "value": {"action": "drill_down", "query_id": query_id},
        },
    ]
    if sql:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看 SQL"},
                "type": "default",
                "value": {"action": "show_sql", "sql": sql, "query_id": query_id},
            }
        )

    feedback_actions = _build_feedback_actions(query_id)

    elements.append({"tag": "hr"})
    elements.append({"tag": "action", "actions": actions})
    elements.extend(_feedback_block(feedback_actions))

    header: dict[str, Any] = {
        "title": {"tag": "plain_text", "content": title[:80]},
        "template": "blue",
    }
    subtitle = _meta_subtitle(table_rows, columns)
    if subtitle:
        header["subtitle"] = {"tag": "plain_text", "content": subtitle}

    return {
        "config": {"wide_screen_mode": True},
        "header": header,
        "elements": elements,
    }


def build_empty_result_card(
    title: str,
    summary: str = "",
    sql: str | None = None,
    query_id: str | None = None,
) -> dict:
    elements: list[dict] = []

    elements.extend(_summary_element(summary))
    if summary:
        elements.append({"tag": "hr"})

    elements.append(
        {
            "tag": "markdown",
            "content": "**该口径下未查到数据。** 可尝试调整时间范围、ASIN/SKU 或换一种问法。",
        }
    )

    actions: list[dict] = []
    if sql:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看 SQL"},
                "type": "default",
                "value": {"action": "show_sql", "sql": sql, "query_id": query_id},
            }
        )

    elements.append({"tag": "hr"})
    if actions:
        elements.append({"tag": "action", "actions": actions})
    elements.extend(_feedback_block(_build_feedback_actions(query_id)))

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": (title or "查询结果")[:80]},
            "template": "grey",
        },
        "elements": elements,
    }


def _build_feedback_actions(query_id: str | None) -> list[dict]:
    return [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "准确"},
            "type": "primary",
            "value": {"action": "feedback", "feedback": "accurate", "query_id": query_id},
        },
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "口径不对"},
            "type": "default",
            "value": {"action": "feedback", "feedback": "wrong_metric", "query_id": query_id},
        },
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "没查到我想要的"},
            "type": "default",
            "value": {"action": "feedback", "feedback": "not_what_i_wanted", "query_id": query_id},
        },
    ]


def _feedback_block(feedback_actions: list[dict]) -> list[dict]:
    """Render feedback behind an overflow (⋯) menu so it stays compact.

    Feishu card schema does not support `collapse`; `overflow` is the supported
    way to tuck secondary actions behind a dropdown. Note: `OptionForm.value`
    must be a JSON-encoded string (a raw object is rejected with
    `cannot unmarshal object into Go struct field OptionForm.value of type
    string`). The card.action.trigger handler already JSON-parses string
    values, so behavior on click is identical to a button.
    """
    return [
        {"tag": "hr"},
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "overflow",
                    "width": "default",
                    "options": [
                        {
                            "text": {"tag": "plain_text", "content": action["text"]["content"]},
                            "value": json.dumps(action["value"], ensure_ascii=False),
                        }
                        for action in feedback_actions
                    ],
                }
            ],
        },
    ]


def _meta_subtitle(
    table_rows: list[dict[str, Any]] | None, columns: list[str] | None
) -> str:
    if not table_rows or not columns:
        return ""
    parts = [f"共 {len(table_rows)} 行", f"{len(columns)} 列"]
    return " · ".join(parts)


def build_table_elements(
    data: list[dict[str, Any]], columns: list[str], max_rows: int = 10, max_columns: int = 6
) -> list[dict]:
    if not data:
        return [{"tag": "markdown", "content": "（无数据）"}]

    visible_columns = columns[:max_columns]
    elements: list[dict] = []

    meta_note = _table_meta_note(data, columns, max_rows, max_columns)
    if meta_note:
        elements.append({"tag": "markdown", "content": meta_note})

    elements.append(
        _build_table_row(
            visible_columns,
            {col: f"**{_format_column_label(col)}**" for col in visible_columns},
        )
    )

    for row in data[:max_rows]:
        elements.append(_build_table_row(visible_columns, row))

    return elements


def _table_meta_note(
    data: list[dict[str, Any]],
    columns: list[str],
    max_rows: int,
    max_columns: int,
) -> str:
    fragments: list[str] = []
    if len(data) > max_rows:
        fragments.append(f"共 {len(data)} 行（展示前 {max_rows} 行）")
    if len(columns) > max_columns:
        fragments.append(f"共 {len(columns)} 列（展示前 {max_columns} 列）")
    if not fragments:
        return ""
    return "> " + " · ".join(fragments)


def build_sql_card(sql: str) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "执行的 SQL"},
            "template": "grey",
        },
        "elements": [{"tag": "markdown", "content": f"```sql\n{sql}\n```"}],
    }


def build_feedback_ack_card(feedback: str) -> dict:
    labels = {
        "accurate": "已记录：结果准确。",
        "wrong_metric": "已记录：口径不对，后续会优先复盘这类问题。",
        "not_what_i_wanted": "已记录：没查到你想要的内容，后续会用于改进 Catalog 和测试集。",
    }
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "反馈已记录"},
            "template": "green" if feedback == "accurate" else "orange",
        },
        "elements": [{"tag": "markdown", "content": labels.get(feedback, "已记录你的反馈。")}],
    }


def build_clarification_card(question: str, session_id: str | None = None) -> dict:
    elements: list[dict] = [
        {"tag": "markdown", "content": question},
        {"tag": "hr"},
        {"tag": "markdown", "content": "请在本话题下方继续回复，或点下方按钮放弃当前问题重新提问。"},
    ]
    if session_id:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "我要重新问"},
                        "type": "default",
                        "value": {"action": "reset_session", "session_id": session_id},
                    }
                ],
            }
        )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "需要确认信息"},
            "template": "orange",
        },
        "elements": elements,
    }


def build_error_card(error_message: str) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "查询遇到问题"},
            "template": "red",
        },
        "elements": [
            {"tag": "markdown", "content": error_message},
            {"tag": "hr"},
            {"tag": "markdown", "content": "请换一种问法，或缩小查询范围。"},
        ],
    }


def build_thinking_card() -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "正在查询"},
            "template": "grey",
        },
        "elements": [{"tag": "markdown", "content": "正在分析问题并生成查询，请稍等。"}],
    }


def _build_table_row(columns: list[str], row: dict[str, Any]) -> dict:
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "default",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [
                    {
                        "tag": "markdown",
                        "content": _format_card_cell(row.get(column, ""), column),
                    }
                ],
            }
            for column in columns
        ],
    }


def _format_card_cell(value: Any, column: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Number):
        return format_metric_value(value, column)
    text = str(value).replace("\n", " ").replace("|", "\\|")
    if len(text) > 80:
        return text[:77] + "..."
    return text


def _format_column_label(column: str) -> str:
    """Column header for the card table. Underscores become spaces for
    readability; the full name is preserved so users can identify the metric
    (Feishu wraps long headers onto multiple lines, which is acceptable)."""
    return column.replace("_", " ")
