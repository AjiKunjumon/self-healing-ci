import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_failure_context
import diagnose_failure
import propose_and_apply_patch


TEST_NAMES = [
    "test_calculate_total_applies_tax_once",
    "test_calculate_total_applies_tax_once_for_single_item",
    "test_calculate_total_applies_tax_once_for_large_order",
    "test_validate_phone_number_formats_correctly",
    "test_validate_phone_number_rejects_short_input",
]


@pytest.mark.parametrize("budget", [0, 100, 10000])
def test_context_keeps_all_failures_across_groups_when_source_budget_runs_out(
    tmp_path, monkeypatch, budget
):
    test_file = tmp_path / "tests" / "test_app.py"
    test_file.parent.mkdir()
    test_file.write_text("from app import calculate_total\n" + "#" * 1000)
    (tmp_path / "app.py").write_text("# source\n" * 100)
    failures = [
        {
            "nodeid": f"tests/test_app.py::{name}",
            "outcome": "failed",
            "call": {"crash": {"message": f"failure {index}: " + "x" * 1000}},
        }
        for index, name in enumerate(TEST_NAMES)
    ]
    report_path = tmp_path / "pytest-report.json"
    output_path = tmp_path / "failure-context.json"
    report_path.write_text(json.dumps({"tests": failures}))
    monkeypatch.setattr(build_failure_context, "ROOT", tmp_path)
    monkeypatch.setattr(build_failure_context, "REPORT_PATH", report_path)
    monkeypatch.setattr(build_failure_context, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(build_failure_context, "MAX_CONTEXT_CHARS", budget)
    monkeypatch.setattr(build_failure_context, "coverage_candidates", lambda _nodeid: {})

    build_failure_context.main()

    context = json.loads(output_path.read_text())
    assert [item["test"] for item in context["failed_tests"]] == [
        item["nodeid"] for item in failures
    ]
    assert [item["failure"] for item in context["failed_tests"]] == [
        item["call"]["crash"]["message"] for item in failures
    ]
    assert context["failure_groups"] == [
        {"group_id": "calculate_total", "tests": [
            item["nodeid"] for item in failures[:3]
        ]},
        {"group_id": "validate_phone_number", "tests": [
            item["nodeid"] for item in failures[3:]
        ]},
    ]
    assert context["failure_batch"] == {"selected": 5, "total": 5, "remaining": 0}
    if budget <= 100:
        assert all(not item["candidate_source_files"] for item in context["failed_tests"])


@pytest.fixture
def failed_tests():
    return [
        {
            "test": f"tests/test_app.py::{name}",
            "group_id": "calculate_total" if index < 3 else "validate_phone_number",
            "failure": f"failure {index}",
        }
        for index, name in enumerate(TEST_NAMES)
    ]


def diagnosis_entries(failures):
    return [
        {**item, "root_cause": "cause", "suggested_fix": "fix"}
        for item in failures
    ]


def test_diagnosis_accepts_all_tests_in_any_order(failed_tests):
    diagnose_failure.validate_per_test(
        list(reversed(diagnosis_entries(failed_tests))), failed_tests
    )


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "wrong_group"])
def test_diagnosis_rejects_incomplete_or_unexpected_tests(failed_tests, change):
    entries = diagnosis_entries(failed_tests)
    if change == "missing":
        entries.pop()
    elif change == "duplicate":
        entries[-1] = entries[0]
    elif change == "extra":
        entries.append({**entries[0], "test": "tests/test_app.py::test_extra"})
    else:
        entries[-1] = {**entries[-1], "group_id": "calculate_total"}

    with pytest.raises(SystemExit, match="exactly once"):
        diagnose_failure.validate_per_test(entries, failed_tests)


def test_repair_prompt_contains_every_failure_and_requires_all_groups(failed_tests):
    context = {"failed_tests": failed_tests}

    prompt = propose_and_apply_patch.build_prompt(context, {}, "", "app source")

    assert "every baseline test failure" in prompt
    assert "independent failure groups" in prompt
    assert "single app.py patch" in prompt
    for item in failed_tests:
        assert item["test"] in prompt
