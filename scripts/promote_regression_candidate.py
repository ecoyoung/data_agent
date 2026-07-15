from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_agent.agent.sql_checker import validate_business_sql
from data_agent.agent.sql_executor import validate_sql


DEFAULT_CANDIDATES = ROOT / "evals" / "query_log_regression_candidates.json"
DEFAULT_EVALS = ROOT / "evals" / "innerbrightness_business_questions.json"


def load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def write_json_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql or "").strip()


def default_case_id(candidate: dict[str, Any]) -> str:
    base = candidate.get("id") or candidate.get("source_query_id") or "candidate"
    base = re.sub(r"[^a-zA-Z0-9]+", "_", str(base).lower()).strip("_")
    return f"promoted_{base[:72]}"


def find_candidate(candidates: list[dict[str, Any]], candidate_id: str) -> dict[str, Any]:
    for candidate in candidates:
        if candidate.get("id") == candidate_id:
            return candidate
    raise ValueError(f"candidate not found: {candidate_id}")


def split_terms(values: list[str]) -> list[str]:
    terms: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in terms:
            terms.append(item)
    return terms


def build_case(
    candidate: dict[str, Any],
    *,
    case_id: str | None = None,
    sql_override: str | None = None,
    required_terms: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
    status: str = "ready",
) -> dict[str, Any]:
    sql = normalize_sql(sql_override if sql_override is not None else candidate.get("sql", ""))
    case = {
        "id": case_id or default_case_id(candidate),
        "status": status,
        "question": candidate.get("user_text") or "",
        "expected_sql": sql,
        "expected_tables": candidate.get("expected_tables") or [],
        "required_terms": required_terms if required_terms is not None else candidate.get("required_terms_suggestion", []),
        "forbidden_terms": forbidden_terms if forbidden_terms is not None else candidate.get("forbidden_terms_suggestion", []),
        "source_candidate_id": candidate.get("id"),
        "source_query_id": candidate.get("source_query_id"),
    }
    expected_row_count = candidate.get("expected_row_count")
    if expected_row_count is not None:
        case["expected_row_count"] = expected_row_count
    return case


def validate_promoted_case(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sql = case.get("expected_sql") or ""
    normalized = normalize_sql(sql).lower()

    valid, error = validate_sql(sql)
    if not valid:
        errors.append(f"invalid SQL safety check: {error}")

    valid, error = validate_business_sql(sql)
    if not valid:
        errors.append(f"invalid SQL business check: {error}")

    if not case.get("question"):
        errors.append("missing question")

    if not re.search(r"\b(date|purchase_date|report_date|snapshot_date|return_date|report_month)\b", normalized):
        errors.append("missing recognizable date filter")

    for table in case.get("expected_tables", []):
        if table.lower() not in normalized:
            errors.append(f"missing expected table: {table}")

    for term in case.get("required_terms", []):
        if term and term.lower() not in normalized:
            errors.append(f"missing required term: {term}")

    for term in case.get("forbidden_terms", []):
        if term and term.lower() in normalized:
            errors.append(f"contains forbidden term: {term}")

    return errors


def duplicate_errors(case: dict[str, Any], existing_cases: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    case_id = case.get("id")
    source_candidate_id = case.get("source_candidate_id")
    source_query_id = case.get("source_query_id")
    for existing in existing_cases:
        if existing.get("id") == case_id:
            errors.append(f"case id already exists: {case_id}")
        if source_candidate_id and existing.get("source_candidate_id") == source_candidate_id:
            errors.append(f"candidate already promoted: {source_candidate_id}")
        if source_query_id and existing.get("source_query_id") == source_query_id:
            errors.append(f"source query already promoted: {source_query_id}")
    return errors


def promote_candidate(
    *,
    candidate_id: str,
    candidates_path: Path,
    evals_path: Path,
    case_id: str | None = None,
    sql_override: str | None = None,
    required_terms: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
    confirm: bool = False,
    confirm_reviewed: bool = False,
) -> tuple[dict[str, Any], list[str], bool]:
    candidates = load_json_list(candidates_path)
    existing_cases = load_json_list(evals_path)
    candidate = find_candidate(candidates, candidate_id)

    if candidate.get("needs_human_review") and not confirm_reviewed:
        return {}, ["candidate needs human review; pass --confirm-reviewed after review"], False
    if candidate.get("promoted"):
        return {}, [f"candidate already promoted: {candidate_id}"], False

    case = build_case(
        candidate,
        case_id=case_id,
        sql_override=sql_override,
        required_terms=required_terms,
        forbidden_terms=forbidden_terms,
    )
    errors = validate_promoted_case(case)
    errors.extend(duplicate_errors(case, existing_cases))
    if errors or not confirm:
        return case, errors, False

    existing_cases.append(case)
    for item in candidates:
        if item.get("id") == candidate_id:
            item["promoted"] = True
            item["promoted_at"] = datetime.now(timezone.utc).isoformat()
            item["promoted_case_id"] = case["id"]
            item["needs_human_review"] = False
            break
    write_json_list(evals_path, existing_cases)
    write_json_list(candidates_path, candidates)
    return case, [], True


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a query-log regression candidate into formal evals.")
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--evals", default=str(DEFAULT_EVALS))
    parser.add_argument("--case-id")
    parser.add_argument("--sql")
    parser.add_argument("--sql-file")
    parser.add_argument("--required-term", action="append", default=[])
    parser.add_argument("--forbidden-term", action="append", default=[])
    parser.add_argument("--confirm", action="store_true", help="Actually write files. Omit for dry-run.")
    parser.add_argument("--confirm-reviewed", action="store_true", help="Confirm this candidate has been reviewed by a human.")
    args = parser.parse_args()

    if args.sql and args.sql_file:
        print("--sql and --sql-file are mutually exclusive", file=sys.stderr)
        return 2
    sql_override = args.sql
    if args.sql_file:
        sql_override = Path(args.sql_file).read_text(encoding="utf-8").strip()

    required = split_terms(args.required_term) or None
    forbidden = split_terms(args.forbidden_term) or None
    try:
        case, errors, wrote = promote_candidate(
            candidate_id=args.candidate_id,
            candidates_path=Path(args.candidates),
            evals_path=Path(args.evals),
            case_id=args.case_id,
            sql_override=sql_override,
            required_terms=required,
            forbidden_terms=forbidden,
            confirm=args.confirm,
            confirm_reviewed=args.confirm_reviewed,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if case:
        print(json.dumps(case, ensure_ascii=False, indent=2))
    if errors:
        print("errors:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("promoted" if wrote else "dry-run ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
