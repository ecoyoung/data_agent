from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CATALOG_DIR = Path(__file__).resolve().parent


@lru_cache
def load_metric_synonyms() -> dict[str, Any]:
    """Load the centralized metric / domain keyword table.

    Used by:
    - ``data_agent.visualization.chart.infer_metric_column`` → ``metrics`` list
    - ``data_agent.agent.prompt_builder._score_table`` → ``table_domains`` list

    Returns an empty dict if the file is missing; callers fall back to
    built-in defaults or simply score zero.
    """
    path = CATALOG_DIR / "metric_synonyms.json"
    if not path.exists():
        return {"metrics": [], "table_domains": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "metrics": data.get("metrics", []),
        "table_domains": data.get("table_domains", []),
    }


@lru_cache
def load_catalog_rules() -> dict[str, Any]:
    path = CATALOG_DIR / "rules.json"
    if not path.exists():
        return {
            "business_rules": [],
            "ask_user_about": [],
            "auto_mappings": [],
            "forbidden_sql": [],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "version": data.get("version", 1),
        "business_rules": data.get("business_rules", []),
        "ask_user_about": data.get("ask_user_about", []),
        "auto_mappings": data.get("auto_mappings", []),
        "forbidden_sql": data.get("forbidden_sql", []),
    }


def render_catalog_rules_for_prompt() -> str:
    rules = load_catalog_rules()
    lines = ["# ===== Data Catalog: structured rules ====="]

    business_rules = rules.get("business_rules", [])
    if business_rules:
        lines.append("\n## business_rule")
        for rule in business_rules:
            prompt = (rule.get("prompt") or rule.get("description") or "").strip()
            if prompt:
                lines.append(f"- `{rule.get('id', '')}`: {prompt}")

    ask_rules = rules.get("ask_user_about", [])
    if ask_rules:
        lines.append("\n## ask_user_about")
        for rule in ask_rules:
            question = (rule.get("question") or "").strip()
            if question:
                lines.append(f"- `{rule.get('id', '')}`: {question}")

    forbidden = rules.get("forbidden_sql", [])
    if forbidden:
        lines.append("\n## forbidden_sql")
        for rule in forbidden:
            message = (rule.get("message") or "").strip()
            if message:
                lines.append(f"- `{rule.get('id', '')}`: {message}")

    return "\n".join(lines)
