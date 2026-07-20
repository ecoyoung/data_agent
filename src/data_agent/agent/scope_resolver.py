from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal


CATALOG_DIR = Path(__file__).resolve().parents[1] / "data_catalog"

MARKET_ALIASES = {
    "US": ("us", "u.s.", "usa", "u.s.a.", "united states", "america", "美国"),
    "CA": ("ca", "canada", "加拿大"),
    "UK": ("uk", "u.k.", "united kingdom", "英国"),
    "EU": ("eu", "europe", "欧洲", "欧盟"),
}


@dataclass(frozen=True)
class ScopeResolution:
    status: Literal["none", "resolved", "ambiguous"]
    matched_alias: str = ""
    market: str | None = None
    scopes: tuple[str, ...] = ()
    tables: tuple[str, ...] = ()
    question: str = ""
    reason: str = ""

    @property
    def resolved(self) -> bool:
        return self.status == "resolved"

    @property
    def ambiguous(self) -> bool:
        return self.status == "ambiguous"


@lru_cache
def load_scope_aliases() -> dict[str, Any]:
    path = CATALOG_DIR / "scope_aliases.json"
    if not path.exists():
        return {"scopes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_scope(user_text: str, history: list[dict] | None = None) -> ScopeResolution:
    text = _normalize(_contextual_text(user_text, history or []))
    if not text:
        return ScopeResolution("none")

    matches = _matching_scopes(text)
    if not matches:
        return ScopeResolution("none")

    best_len = max(len(alias) for alias, _scope in matches)
    best_matches = [(alias, scope) for alias, scope in matches if len(alias) == best_len]
    matched_alias = sorted({alias for alias, _scope in best_matches}, key=lambda value: (-len(value), value))[0]
    scopes = sorted({scope for _alias, scope in best_matches})

    market = _detect_market(text)
    if market:
        market_scopes = [
            scope
            for scope in scopes
            if str(_scope(scope).get("market") or "").upper() == market
        ]
        if market_scopes:
            return _resolved(matched_alias, market, market_scopes)

    if len(scopes) == 1:
        return _resolved(matched_alias, market, scopes)

    markets = sorted({str(_scope(scope).get("market") or "ALL") for scope in scopes})
    market_options = ", ".join(markets)
    return ScopeResolution(
        "ambiguous",
        matched_alias=matched_alias,
        market=market,
        scopes=tuple(scopes),
        tables=tuple(_tables_for_scopes(scopes)),
        question=(
            f"“{matched_alias}”对应多个可查询范围（{market_options}）。"
            "请确认要查哪个市场/店铺，例如 US、CA，还是整体范围。"
        ),
        reason="ambiguous_scope_alias",
    )


def _resolved(matched_alias: str, market: str | None, scopes: list[str]) -> ScopeResolution:
    tables = _tables_for_scopes(scopes)
    return ScopeResolution(
        "resolved",
        matched_alias=matched_alias,
        market=market,
        scopes=tuple(sorted(scopes)),
        tables=tuple(tables),
        reason="resolved_scope_alias",
    )


def _contextual_text(user_text: str, history: list[dict]) -> str:
    if not history:
        return user_text
    context = "\n".join(
        str(item.get("content", ""))
        for item in history[-4:]
        if item.get("role") in {"user", "assistant"}
    )
    return f"{context}\n{user_text}".strip()


def _scope(scope: str) -> dict[str, Any]:
    return load_scope_aliases().get("scopes", {}).get(scope, {})


def _matching_scopes(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for scope, item in load_scope_aliases().get("scopes", {}).items():
        for alias in item.get("aliases", []):
            alias_text = _normalize(str(alias))
            if alias_text and _alias_in_text(alias_text, text):
                matches.append((alias_text, str(scope)))
    return matches


def _tables_for_scopes(scopes: list[str]) -> list[str]:
    tables: list[str] = []
    for scope in sorted(scopes):
        domains = _scope(scope).get("domains") or {}
        for domain_tables in domains.values():
            for table in domain_tables:
                if table not in tables:
                    tables.append(str(table))
    return tables


def _detect_market(text: str) -> str | None:
    for market, aliases in MARKET_ALIASES.items():
        for alias in aliases:
            if _alias_in_text(_normalize(alias), text):
                return market
    return None


def _alias_in_text(alias: str, text: str) -> bool:
    if not alias:
        return False
    if len(alias) <= 3 and re.fullmatch(r"[a-z0-9]+", alias):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text))
    return alias in text


def _normalize(text: str) -> str:
    normalized = text.replace("_", " ").replace("-", " ").lower()
    normalized = re.sub(r"<at[^>]*>.*?</at>", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
