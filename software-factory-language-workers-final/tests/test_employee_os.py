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
