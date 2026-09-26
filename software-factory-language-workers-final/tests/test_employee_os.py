from pathlib import Path
from types import SimpleNamespace

from factory.employee_os import role_for_task, sync_task_file


def test_role_for_task_prefers_explicit_role():
    assert role_for_task("Fix tests", "developer") == "developer"


def test_role_for_task_routes_test_work_to_tester():
    assert role_for_task("Add regression tests") == "tester"


def test_sync_task_file_writes_employee_inbox(tmp_path: Path):
    task = SimpleNamespace(
        id="task_123", title="Implement feature", description="Build the feature.",
        status="PENDING", assigned_agent="developer", acceptance_criteria=["Feature works"],
        tests_required=["pytest"], files_expected=["factory/example.py"], failure_reason=None,
    )
    path = sync_task_file(tmp_path, task)
    assert path.parent.name == "INBOX"
    text = path.read_text(encoding="utf-8")
    assert "#DEVELOPER" in text
    assert "Feature works" in text
    assert "pytest" in text


def test_task_evidence_is_persisted():
    from factory.models import Task
    task = Task(project_id="p", title="x", description="x")
    task.evidence = ["pytest -q", "tests/test_x.py"]
    assert task.evidence == ["pytest -q", "tests/test_x.py"]


def test_sync_task_file_uses_persisted_evidence(tmp_path: Path):
    task = SimpleNamespace(id="task_456", title="Run QA", description="Run tests.", status="DONE", assigned_agent="tester", acceptance_criteria=[], tests_required=[], files_expected=[], failure_reason=None, evidence=["pytest -q", "docs/TEST_REPORT.md"])
    path = sync_task_file(tmp_path, task)
    text = path.read_text(encoding="utf-8")
    assert "pytest -q" in text
    assert "docs/TEST_REPORT.md" in text
