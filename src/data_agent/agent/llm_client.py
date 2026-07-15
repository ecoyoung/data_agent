from __future__ import annotations

import re

from openai import APITimeoutError, OpenAI

from data_agent.config import get_settings


SQL_BLOCK_RE = re.compile(r"```sql\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)

LLM_TIMEOUT_SECONDS = 60


class LLMTimeoutError(TimeoutError):
    """Raised when the LLM call exceeds LLM_TIMEOUT_SECONDS."""


def chat(messages: list[dict]) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        return "DeepSeek API Key 未配置。请先在 `.env` 中设置 DEEPSEEK_API_KEY。"

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        timeout=LLM_TIMEOUT_SECONDS,
    )
    try:
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            temperature=0.1,
            max_tokens=settings.llm_max_tokens,
        )
    except APITimeoutError as exc:
        raise LLMTimeoutError(
            f"DeepSeek 调用超过 {LLM_TIMEOUT_SECONDS}s 未响应"
        ) from exc
    return response.choices[0].message.content or ""


def extract_sql(text: str) -> str | None:
    match = SQL_BLOCK_RE.search(text)
    if not match:
        return None
    return match.group(1).strip()


def strip_sql_blocks(text: str) -> str:
    return SQL_BLOCK_RE.sub("", text).strip()


def is_clarification(text: str) -> bool:
    return extract_sql(text) is None and ("?" in text or "？" in text)
