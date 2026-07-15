import json

from scripts.promote_regression_candidate import (
    build_case,
    promote_candidate,
    split_terms,
    validate_promoted_case,
)


def _candidate() -> dict:
    return {
        "id": "cand_1",
        "source_query_id": "q1",
        "user_text": "Brumate 2026年6月份订单销售额数据",
        "sql": (
            "SELECT to_char(report_date, 'YYYY-MM') AS month, SUM(ordered_revenue) AS order_revenue "
            "FROM intermediate_amazon_3p_orders_brumate_view "
            "WHERE report_date >= DATE '2026-06-01' AND report_date < DATE '2026-07-01' "
            "AND country_code = 'US' GROUP BY 1 ORDER BY 1"
        ),
        "expected_tables": ["intermediate_amazon_3p_orders_brumate_view"],
        "required_terms_suggestion": ["ordered_revenue", "GROUP BY 1", "country_code = 'US'"],
        "forbidden_terms_suggestion": ["GROUP BY month"],
        "needs_human_review": True,
    }


def _write_json(path, rows):
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_build_case_from_candidate() -> None:
    case = build_case(_candidate(), case_id="case_1")

    assert case["id"] == "case_1"
    assert case["status"] == "ready"
    assert case["question"] == "Brumate 2026年6月份订单销售额数据"
    assert case["expected_tables"] == ["intermediate_amazon_3p_orders_brumate_view"]
    assert case["source_candidate_id"] == "cand_1"


def test_validate_promoted_case_passes_valid_case() -> None:
    case = build_case(_candidate(), case_id="case_1")

    assert validate_promoted_case(case) == []


def test_split_terms_preserves_sql_function_commas() -> None:
    assert split_terms(["to_char(report_date, 'YYYY-MM')", "ordered_revenue"]) == [
        "to_char(report_date, 'YYYY-MM')",
        "ordered_revenue",
    ]


def test_promote_requires_review_confirmation(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    evals_path = tmp_path / "evals.json"
    _write_json(candidates_path, [_candidate()])
    _write_json(evals_path, [])

    case, errors, wrote = promote_candidate(
        candidate_id="cand_1",
        candidates_path=candidates_path,
        evals_path=evals_path,
        confirm=True,
        confirm_reviewed=False,
    )

    assert case == {}
    assert wrote is False
    assert "needs human review" in errors[0]


def test_promote_dry_run_does_not_write(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    evals_path = tmp_path / "evals.json"
    _write_json(candidates_path, [_candidate()])
    _write_json(evals_path, [])

    case, errors, wrote = promote_candidate(
        candidate_id="cand_1",
        candidates_path=candidates_path,
        evals_path=evals_path,
        case_id="case_1",
        confirm=False,
        confirm_reviewed=True,
    )

    assert errors == []
    assert wrote is False
    assert case["id"] == "case_1"
    assert json.loads(evals_path.read_text(encoding="utf-8")) == []


def test_promote_confirm_writes_case_and_marks_candidate(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    evals_path = tmp_path / "evals.json"
    _write_json(candidates_path, [_candidate()])
    _write_json(evals_path, [])

    case, errors, wrote = promote_candidate(
        candidate_id="cand_1",
        candidates_path=candidates_path,
        evals_path=evals_path,
        case_id="case_1",
        confirm=True,
        confirm_reviewed=True,
    )

    assert errors == []
    assert wrote is True
    assert case["id"] == "case_1"

    evals = json.loads(evals_path.read_text(encoding="utf-8"))
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    assert evals[0]["id"] == "case_1"
    assert candidates[0]["promoted"] is True
    assert candidates[0]["promoted_case_id"] == "case_1"
    assert candidates[0]["needs_human_review"] is False


def test_promote_rejects_duplicate_source_query(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.json"
    evals_path = tmp_path / "evals.json"
    _write_json(candidates_path, [_candidate()])
    _write_json(evals_path, [{"id": "other", "source_query_id": "q1"}])

    _, errors, wrote = promote_candidate(
        candidate_id="cand_1",
        candidates_path=candidates_path,
        evals_path=evals_path,
        confirm=True,
        confirm_reviewed=True,
    )

    assert wrote is False
    assert any("source query already promoted" in error for error in errors)
