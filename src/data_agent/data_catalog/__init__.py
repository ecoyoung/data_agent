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


@lru_cache
def load_catalog_hints() -> dict[str, Any]:
    path = CATALOG_DIR / "hints.json"
    if not path.exists():
        return {"family_hints": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "version": data.get("version", 1),
        "source": data.get("source", ""),
        "family_hints": data.get("family_hints", []),
    }


@lru_cache
def load_relationships() -> dict[str, Any]:
    path = CATALOG_DIR / "relationships.json"
    if not path.exists():
        return {"relationships": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "version": data.get("version", 1),
        "source": data.get("source", ""),
        "relationships": data.get("relationships", []),
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


def render_catalog_hints_for_prompt(
    user_text: str = "",
    selected_tables: set[str] | None = None,
) -> str:
    hints = load_catalog_hints().get("family_hints", [])
    if not hints:
        return ""

    lines = ["# ===== Data Catalog: intermediate_amazon AI_HINT ====="]
    query = user_text.lower()
    rendered_count = 0
    for hint in hints:
        if user_text or selected_tables is not None:
            triggers = [str(trigger).lower() for trigger in hint.get("triggers", [])]
            prefixes = tuple(str(prefix).lower() for prefix in hint.get("table_prefixes", []))
            triggered = bool(query and any(trigger in query for trigger in triggers))
            table_matched = bool(
                selected_tables
                and prefixes
                and any(str(table).lower().startswith(prefixes) for table in selected_tables)
            )
            if user_text:
                if not triggered:
                    continue
            elif not (triggered or table_matched):
                continue

        lines.append(f"\n## {hint.get('id', '')}")
        description = (hint.get("description") or "").strip()
        if description:
            lines.append(f"- description: {description}")
        prompt = (hint.get("prompt") or "").strip()
        if prompt:
            lines.append(f"- business_rule: {prompt}")
        negatives = [str(item).strip() for item in hint.get("negative_examples", []) if str(item).strip()]
        if negatives:
            lines.append("- negative_examples:")
            for example in negatives[:4]:
                lines.append(f"  - {example}")
        rendered_count += 1
    if rendered_count == 0:
        return ""
    return "\n".join(lines)
