from pathlib import Path

from factory.roles import extract_target, tag_for
from factory.models import WorkflowState
from factory.config import Settings
from factory.database import Database
from factory.orchestrator import Orchestrator


def test_employee_tags():
    assert extract_target("#DEV fix login")[0] == "#DEV"
    assert extract_target("#uiux adjust spacing")[1] == "adjust spacing"
    assert tag_for("UI/UX Designer Agent") == "#UIUX"


def test_all_directive_shared_context(tmp_path):
    settings = Settings(db_path=tmp_path / "factory.db", workspaces_root=tmp_path / "workspaces", log_level="INFO", provider="mock", model="mock", api_key=None, mode="mock")
    settings.ensure_directories()
    o = Orchestrator(Database(settings.db_path), settings)
    p = o.create_project("Tags", "Build a Python app")
    target = Path(p.workspace_path) / "docs" / "TEAM_CONTEXT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("## #ALL directive\nUse the shared architecture.\n", encoding="utf-8")
    assert "#ALL directive" in target.read_text(encoding="utf-8")


def test_release_package_excludes_secrets_and_metadata(tmp_path):
    settings = Settings(db_path=tmp_path / "factory.db", workspaces_root=tmp_path / "workspaces", log_level="INFO", provider="mock", model="mock", api_key=None, mode="mock")
    settings.ensure_directories()
    o = Orchestrator(Database(settings.db_path), settings)
    p = o.create_project("Release", "Build a Python app")
    root = Path(p.workspace_path)
    (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=do-not-ship\n", encoding="utf-8")
    (root / ".git" / "config").write_text("git metadata\n", encoding="utf-8")
    result = o.agents["release"].run(__import__("factory.orchestrator", fromlist=["Context"]).Context(p, p.workspace_path, 30))
    assert result.success
    import zipfile
    with zipfile.ZipFile(root / result.detailed_output["package"]) as archive:
        names = set(archive.namelist())
    assert "app.py" in names
    assert ".env" not in names
    assert ".git/config" not in names
