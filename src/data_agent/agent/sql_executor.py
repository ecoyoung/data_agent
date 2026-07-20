from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from data_agent.agent.sql_checker import referenced_tables
from data_agent.agent.sql_checker import validate_business_sql
from data_agent.agent.sql_repair import repair_sql
from data_agent.config import get_settings


FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "CREATE",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "EXECUTE",
    "CALL",
    "COPY",
}

TOKEN_RE = re.compile(r"\b[A-Z_]+\b")


def _without_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--.*?$", " ", sql, flags=re.MULTILINE)


def validate_sql(sql: str) -> tuple[bool, str]:
    cleaned = _without_comments(sql).strip()
    if not cleaned:
        return False, "SQL 为空"

    if ";" in cleaned.rstrip(";"):
        return False, "不允许一次提交多条 SQL"

    normalized = cleaned.rstrip(";").lstrip("(").strip().upper()
    tokens = set(TOKEN_RE.findall(normalized))
    blocked = sorted(tokens & FORBIDDEN_KEYWORDS)
    if blocked:
        return False, f"SQL 包含禁止操作：{blocked[0]}"

    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return False, "只允许 SELECT / WITH 查询"

    return True, ""


def get_connection():
    settings = get_settings()
    return psycopg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_database,
        user=settings.pg_user,
        password=settings.pg_password,
        connect_timeout=5,
        options=(
            f"-c statement_timeout={settings.sql_timeout * 1000} "
            "-c default_transaction_read_only=on"
        ),
        row_factory=dict_row,
        autocommit=True,
    )


def _select_permission_error(conn, sql: str) -> str | None:
    missing: list[str] = []
    tables = sorted(referenced_tables(sql.lower()))
    if not tables:
        return None

    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                """
                SELECT COALESCE(
                    pg_catalog.has_table_privilege(
                        current_user,
                        pg_catalog.to_regclass(%s),
                        'SELECT'
                    ),
                    false
                ) AS can_select
                """,
                (f"public.{table}",),
            )
            row = cur.fetchone()
            if not row or not row["can_select"]:
                missing.append(table)

    if missing:
        return f"数据库权限不足：当前数据库用户没有 SELECT 权限：{', '.join(missing[:5])}"
    return None


def execute_query(sql: str) -> tuple[list[dict[str, Any]], list[str], str | None]:
    valid, error = validate_sql(sql)
    if not valid:
        return [], [], error

    sql = repair_sql(sql).sql

    valid, error = validate_business_sql(sql)
    if not valid:
        return [], [], f"业务规则校验失败：{error}"

    settings = get_settings()
    conn = None
    try:
        conn = get_connection()
        permission_error = _select_permission_error(conn, sql)
        if permission_error:
            return [], [], permission_error
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchmany(settings.max_rows)
            columns = [desc[0] for desc in cur.description]
            return list(rows), columns, None
    except psycopg.errors.QueryCanceled:
        return [], [], f"查询超时（超过 {settings.sql_timeout} 秒），请缩小时间范围或增加过滤条件"
    except psycopg.Error as exc:
        return [], [], f"数据库错误：{exc}"
    finally:
        if conn is not None:
            conn.close()
