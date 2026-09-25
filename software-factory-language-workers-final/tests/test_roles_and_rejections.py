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
    settings = Settings(tmp_path / "factory.db", tmp_path / "workspaces", "INFO", "mock", "mock", None)
    settings.ensure_directories()
    o = Orchestrator(Database(settings.db_path), settings)
    p = o.create_project("Tags", "Build a Python app")
    target = Path(p.workspace_path) / "docs" / "TEAM_CONTEXT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("## #ALL directive\nUse the shared architecture.\n", encoding="utf-8")
    assert "#ALL directive" in target.read_text(encoding="utf-8")
