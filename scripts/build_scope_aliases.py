"""Build brand/store scope aliases from intermediate_amazon_ catalog metadata."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "src" / "data_agent" / "data_catalog"
METADATA_PATH = CATALOG_DIR / "tables_metadata.json"
OUTPUT_JSON = CATALOG_DIR / "scope_aliases.json"
OUTPUT_MD = ROOT / "docs" / "intermediate_amazon_scope_map.md"

MARKET_TOKENS = {"us", "ca", "uk", "eu", "jp", "it", "de", "fr", "au"}
KNOWN_ALIASES = {
    "belliwelli": ["belli welli", "belliwelli"],
    "innerbrightness": ["inner brightness", "innerbrightness", "inner brightness-new", "inner brightness new"],
    "brumate": ["brumate", "bru mate", "brümate"],
    "blueland": ["blueland", "blue land"],
    "perfectbar": ["perfect bar", "perfectbar"],
    "minorfigures": ["minor figures", "minorfigures"],
    "naturalrhythm": ["natural rhythm", "naturalrhythm"],
    "vitalproteinsbv": ["vital proteins", "vital proteins bv", "vitalproteinsbv"],
    "vp_us": ["vp us", "vital proteins us", "vitalproteins us"],
    "vp_eu": ["vp eu", "vital proteins eu", "vitalproteins eu"],
    "beekeepersnaturals": ["beekeeper", "beekeepers naturals", "beekeepersnaturals", "bkn"],
    "beekeepers_us": ["beekeepers us", "beekeeper us"],
    "beekeeper_us": ["beekeeper us", "beekeepers us", "bkn us", "bkn"],
    "beekeeper_ca": ["beekeeper ca", "beekeepers ca", "bkn ca", "bkn"],
    "lider_us": ["lider us", "lider"],
    "lider_ca": ["lider ca"],
    "lider_uk": ["lider uk"],
    "sonoff_us": ["sonoff us", "sonoff"],
    "sonoff_eu": ["sonoff eu"],
    "sonoff3p_us": ["sonoff 3p us", "sonoff3p us"],
    "sonoff3p_eu": ["sonoff 3p eu", "sonoff3p eu"],
}


def normalize_alias(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip().lower()


def split_scope(scope: str) -> tuple[str, str | None]:
    parts = scope.split("_")
    if len(parts) > 1 and parts[-1] in MARKET_TOKENS:
        return "_".join(parts[:-1]), parts[-1].upper()
    return scope, None


def default_aliases(scope: str) -> list[str]:
    base, market = split_scope(scope)
    aliases = {scope, scope.replace("_", " "), base, base.replace("_", " ")}
    if market:
        aliases.add(f"{base.replace('_', ' ')} {market.lower()}")
    aliases.update(KNOWN_ALIASES.get(scope, []))
    aliases.update(KNOWN_ALIASES.get(base, []))
    return sorted({normalize_alias(alias) for alias in aliases if alias})


def build_scope_map(metadata: dict[str, Any]) -> dict[str, Any]:
    scopes: dict[str, dict[str, Any]] = {}
    grouped_tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table in metadata.get("tables", []):
        scope = table.get("scope_token")
        if not scope:
            continue
        grouped_tables[str(scope)].append(table)

    for scope, tables in sorted(grouped_tables.items()):
        base, market = split_scope(scope)
        domains: dict[str, list[str]] = defaultdict(list)
        for table in tables:
            domain = table.get("domain") or "unknown"
            domains[str(domain)].append(str(table.get("table")))

        identity_values: dict[str, set[str]] = defaultdict(set)
        for table in tables:
            for field, values in (table.get("identity_fields") or {}).items():
                for value in values:
                    if value:
                        identity_values[field].add(str(value))

        scopes[scope] = {
            "scope_token": scope,
            "base_scope": base,
            "market": market,
            "aliases": default_aliases(scope),
            "domains": {domain: sorted(names) for domain, names in sorted(domains.items())},
            "identity_values": {
                field: sorted(values) for field, values in sorted(identity_values.items())
            },
            "table_count": len(tables),
        }

    return {
        "version": 1,
        "source": "src/data_agent/data_catalog/tables_metadata.json",
        "scope_count": len(scopes),
        "scopes": scopes,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# intermediate_amazon_ Scope Map",
        "",
        f"Scopes: `{payload['scope_count']}`",
        "",
        "| Scope | Aliases | Market | Tables | Domains |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for scope, item in payload["scopes"].items():
        domains = ", ".join(f"{domain}({len(tables)})" for domain, tables in item["domains"].items())
        aliases = ", ".join(item["aliases"][:8])
        lines.append(
            f"| `{scope}` | {aliases} | {item.get('market') or ''} | {item['table_count']} | {domains} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    payload = build_scope_map(metadata)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(payload), encoding="utf-8")
    print(f"wrote {OUTPUT_JSON}")
    print(f"wrote {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
