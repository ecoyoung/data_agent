import json
from pathlib import Path

from scripts.validate_business_sql_cases import validate_case


CASE_FILE = Path(__file__).resolve().parents[1] / "evals" / "innerbrightness_business_questions.json"


def test_business_sql_cases_are_safe_and_scoped() -> None:
    cases = json.loads(CASE_FILE.read_text(encoding="utf-8"))

    assert len(cases) >= 10
    for case in cases:
        errors = validate_case(case)
        assert errors == [], f"{case['id']}: {errors}"
