from __future__ import annotations

from factory.models import Project, ProjectStatus, RetryPolicy, Task, TaskStatus


def test_project_defaults():
    p = Project(name="Demo", description="desc", workspace_path="/tmp/demo")
    assert p.status == ProjectStatus.CREATED
    assert p.id.startswith("proj_")
    assert isinstance(p.retry_policy, RetryPolicy)
    assert p.retry_policy.max_retries_per_task == 5


def test_task_defaults():
    t = Task(project_id="proj_x", title="Do thing", description="desc")
    assert t.status == TaskStatus.PENDING
    assert t.id.startswith("task_")
    assert t.retry_count == 0
    assert t.dependencies == []


def test_project_serialization_roundtrip():
    p = Project(name="Demo", description="desc", workspace_path="/tmp/demo")
    json_str = p.model_dump_json()
    restored = Project.model_validate_json(json_str)
    assert restored == p
