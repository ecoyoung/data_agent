from __future__ import annotations

import ast
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


def _load_legacy_postgres_env() -> dict[str, Any]:
    """Read the existing postgresql.env Python-dict fragment without executing it."""
    path = BASE_DIR / "postgresql.env"
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}

    try:
        parsed = ast.literal_eval("{" + text.rstrip(",") + "}")
    except (SyntaxError, ValueError):
        return {}

    return {
        "pg_host": parsed.get("host"),
        "pg_port": parsed.get("port"),
        "pg_database": parsed.get("database"),
        "pg_user": parsed.get("user"),
        "pg_password": parsed.get("password"),
    }


def _load_dotenv_keys() -> set[str]:
    path = BASE_DIR / ".env"
    if not path.exists():
        return set()

    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _ = stripped.split("=", 1)
        keys.add(key.strip())
    return keys


class Settings(BaseSettings):
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_encrypt_key: str = ""
    feishu_verification_token: str = ""

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_max_tokens: int = Field(default=4000, ge=512, le=8000)

    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = ""
    pg_user: str = ""
    pg_password: str = ""

    app_port: int = 8000
    debug: bool = True
    sql_timeout: int = 30
    max_rows: int = Field(default=500, ge=1, le=5000)
    max_concurrent_queries: int = Field(default=4, ge=1, le=32)
    query_log_db_path: str = str(BASE_DIR / "storage" / "query_logs.sqlite3")

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    dotenv_keys = _load_dotenv_keys()
    legacy = {
        key: value
        for key, value in _load_legacy_postgres_env().items()
        if value is not None
        and os.getenv(key.upper()) is None
        and key.upper() not in dotenv_keys
    }
    return Settings(**legacy)
