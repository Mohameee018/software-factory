from __future__ import annotations

from pathlib import Path

from factory.database import Database
from factory.models import Project, ProjectStatus, Task, TaskPriority, TaskStatus


def make_db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


def test_save_and_get_project(tmp_path):
    db = make_db(tmp_path)
    project = Project(name="Demo", description="A demo project", workspace_path=str(tmp_path))
    db.save_project(project)

    fetched = db.get_project(project.id)
    assert fetched is not None
    assert fetched.id == project.id
    assert fetched.name == "Demo"
    assert fetched.status == ProjectStatus.CREATED


def test_get_missing_project_returns_none(tmp_path):
    db = make_db(tmp_path)
    assert db.get_project("does-not-exist") is None


def test_update_existing_project(tmp_path):
    db = make_db(tmp_path)
    project = Project(name="Demo", description="x", workspace_path=str(tmp_path))
    db.save_project(project)

    project.status = ProjectStatus.PLANNING
    db.save_project(project)

    fetched = db.get_project(project.id)
    assert fetched.status == ProjectStatus.PLANNING


def test_list_projects_ordering(tmp_path):
    db = make_db(tmp_path)
    p1 = Project(name="First", description="x", workspace_path=str(tmp_path))
    p2 = Project(name="Second", description="x", workspace_path=str(tmp_path))
    db.save_project(p1)
    db.save_project(p2)

    projects = db.list_projects()
    assert len(projects) == 2
    ids = {p.id for p in projects}
    assert ids == {p1.id, p2.id}


def test_save_and_get_task(tmp_path):
    db = make_db(tmp_path)
    project = Project(name="Demo", description="x", workspace_path=str(tmp_path))
    db.save_project(project)

    task = Task(
        project_id=project.id,
        title="Set up repo",
        description="Init git and pyproject",
        priority=TaskPriority.HIGH,
    )
    db.save_task(task)

    fetched = db.get_task(task.id)
    assert fetched is not None
    assert fetched.title == "Set up repo"
    assert fetched.status == TaskStatus.PENDING
    assert fetched.priority == TaskPriority.HIGH


def test_list_tasks_for_project(tmp_path):
    db = make_db(tmp_path)
    project = Project(name="Demo", description="x", workspace_path=str(tmp_path))
    db.save_project(project)

    t1 = Task(project_id=project.id, title="Task 1", description="")
    t2 = Task(project_id=project.id, title="Task 2", description="")
    db.save_task(t1)
    db.save_task(t2)

    other_project = Project(name="Other", description="x", workspace_path=str(tmp_path))
    db.save_project(other_project)
    other_task = Task(project_id=other_project.id, title="Other task", description="")
    db.save_task(other_task)

    tasks = db.list_tasks_for_project(project.id)
    assert len(tasks) == 2
    assert {t.id for t in tasks} == {t1.id, t2.id}


def test_task_status_update_persists(tmp_path):
    db = make_db(tmp_path)
    project = Project(name="Demo", description="x", workspace_path=str(tmp_path))
    db.save_project(project)
    task = Task(project_id=project.id, title="Task", description="")
    db.save_task(task)

    task.status = TaskStatus.DONE
    task.retry_count = 2
    db.save_task(task)

    fetched = db.get_task(task.id)
    assert fetched.status == TaskStatus.DONE
    assert fetched.retry_count == 2
