from pathlib import Path
from types import SimpleNamespace

from factory.models import ProjectType
from factory.orchestrator import Orchestrator


def test_flutter_scaffold_preserves_preexisting_factory_docs(tmp_path, monkeypatch):
    workspace = tmp_path / "project"
    workspace.mkdir()
    docs = workspace / "docs"
    docs.mkdir()
    requirements = docs / "REQUIREMENTS.md"
    requirements.write_text("# Requirements\n", encoding="utf-8")

    project = SimpleNamespace(id="proj_test", workspace_path=str(workspace))
    state = SimpleNamespace(error_history=[])

    class FakeDB:
        def event(self, event):
            pass

        def save_state(self, value):
            pass

    fake_db = FakeDB()
    fake_settings = SimpleNamespace(command_timeout=30)

    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.db = fake_db
    orchestrator.settings = fake_settings

    def fake_run_command(role, command, cwd, timeout=None):
        if command == "flutter --version" or command == "dart --version":
            return SimpleNamespace(
                command=command, exit_code=0, stdout="ok", stderr="", duration_seconds=0
            )
        assert command == "flutter create --no-pub app"
        scaffold = Path(cwd) / "app"
        (scaffold / "lib").mkdir(parents=True)
        (scaffold / "pubspec.yaml").write_text("name: generated_app\n", encoding="utf-8")
        (scaffold / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
        return SimpleNamespace(
            command=command, exit_code=0, stdout="created", stderr="", duration_seconds=0
        )

    monkeypatch.setattr("factory.orchestrator.run_command", fake_run_command)

    assert orchestrator._prepare_flutter_project(project, state) is True
    assert requirements.read_text(encoding="utf-8") == "# Requirements\n"
    assert (workspace / "pubspec.yaml").exists()
    assert (workspace / "lib" / "main.dart").exists()
