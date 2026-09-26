import json
from pathlib import Path

from factory.config import Settings
from factory.database import Database
from factory.dashboard import snapshot
from factory.github import GitHubProjectPublisher
from factory.models import Project
from factory.storage import build_database


def test_storage_selects_postgres_backend(monkeypatch, tmp_path):
    settings = Settings(
        tmp_path / "factory.db",
        tmp_path / "workspaces",
        "INFO",
        "mock",
        "mock",
        None,
        database_url="postgresql://example.invalid/factory",
    )
    class FakePostgres:
        def __init__(self, url):
            self.database_url = url
    import factory.postgres_database
    monkeypatch.setattr(factory.postgres_database, "PostgresDatabase", FakePostgres)
    db = build_database(settings)
    assert isinstance(db, FakePostgres)
    assert db.database_url.startswith("postgresql://")


def test_dashboard_snapshot_exposes_workers_and_budget(tmp_path):
    db = Database(tmp_path / "factory.db")
    p = Project(name="Dashboard", description="test", workspace_path=str(tmp_path / "p"))
    db.save_project(p)
    db.heartbeat("worker:python", {"status": "running", "worker_type": "python"})
    data = snapshot(db)
    assert data["queue_pending"] == 0
    worker = next(w for w in data["workers"] if w["type"] == "python")
    assert worker["details"]["status"] == "running"
    assert data["projects"][0]["budget"]["agent_runs"] == 0


def test_github_project_payload_is_private_by_default(tmp_path):
    settings = Settings(
        tmp_path / "factory.db",
        tmp_path / "workspaces",
        "INFO",
        "mock",
        "mock",
        None,
        github_token="test-token",
        github_owner="owner",
        github_enabled=True,
    )
    publisher = GitHubProjectPublisher(settings)
    captured = {}
    def fake_request(method, url, payload=None):
        captured.update(payload or {})
        return {
            "full_name": "owner/demo-12345678",
            "html_url": "https://github.com/owner/demo-12345678",
            "clone_url": "https://github.com/owner/demo-12345678.git",
            "private": True,
            "default_branch": "main",
        }
    publisher._request = fake_request
    result = publisher.create_private_repo("Demo", "proj-12345678", "test")
    assert captured["private"] is True
    assert result["private"] is True
