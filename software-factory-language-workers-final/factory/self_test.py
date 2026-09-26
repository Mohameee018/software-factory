from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from factory.approvals import ApprovalService
from factory.config import Settings
from factory.database import Database
from factory.models import ProjectType, WorkflowState
from factory.orchestrator import Orchestrator


def _telegram_intake_smoke() -> None:
    """Exercise the real Telegram handler without contacting Telegram's network."""
    from factory.integrations.telegram.handlers import TelegramHandlers

    class Message:
        def __init__(self):
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append(str(text))

    class Project:
        id = "self-test-project"
        name = "Self Test"
        description = ""
        workspace_path = ""
        project_type = ProjectType.UNKNOWN

    class Service:
        def __init__(self):
            self.created = None

        def create_project(self, name, description, project_type=None):
            p = Project()
            p.description = description
            self.created = p
            return p

        def set_state(self, project, state):
            project.current_state = state

    class Context:
        args = ["Build", "a", "Flutter", "Tasbeeh", "app"]
        user_data = {}

    update = type(
        "Update",
        (),
        {"effective_message": Message(), "effective_user": type("User", (), {"id": 1})()},
    )()
    service = Service()

    # The handler's normal /new path invokes requirements only when a workspace
    # exists. Keeping this synthetic project workspace-less isolates Telegram
    # intake, routing, and project-type detection from the AI/network layer.
    asyncio.run(TelegramHandlers(service).new(update, Context()))

    assert service.created is not None
    assert service.created.project_type == ProjectType.FLUTTER
    assert Context.user_data["active_project_id"] == service.created.id
    assert update.effective_message.replies


def _workflow_smoke(root: Path) -> None:
    """Run the real orchestrator through the mock workflow and approvals."""
    settings = Settings(
        root / "factory.db",
        root / "workspaces",
        "INFO",
        "mock",
        "self-test",
        None,
        3,
        30,
        30,
        mode="mock",
        github_enabled=False,
        github_auto_sync=False,
    )
    settings.ensure_directories()
    orchestrator = Orchestrator(Database(settings.db_path), settings)

    project = orchestrator.create_project(
        "Self Test Flutter App",
        "Build a simple Flutter Tasbeeh counter app",
    )
    assert project.project_type == ProjectType.FLUTTER

    # Start from the design-approved boundary so the self-test exercises the
    # implementation/QA/review/security/final-gate path without needing an LLM.
    project.current_state = WorkflowState.DESIGNING
    orchestrator.db.save_project(project)
    state = orchestrator.db.get_state(project.id)
    state.current_state = WorkflowState.DESIGNING
    orchestrator.db.save_state(state)

    state = orchestrator.run(project.id, mock=True)
    assert state.current_state == WorkflowState.WAITING_FOR_DESIGN_APPROVAL, state.error_history

    # The mock run can request a design approval at the normal human boundary.
    design = [
        a for a in orchestrator.db.list_approvals(project.id)
        if a.requested_action == "design_approval"
    ][-1]
    ApprovalService(orchestrator.db).resolve(design, True, "self-test")
    state = orchestrator.run(project.id, mock=True)
    assert state.current_state == WorkflowState.READY_FOR_HUMAN, state.error_history

    final = [
        a for a in orchestrator.db.list_approvals(project.id)
        if a.requested_action == "final_approval"
    ][-1]
    ApprovalService(orchestrator.db).resolve(final, True, "self-test final approval")
    state = orchestrator.run(project.id, mock=True)
    assert state.current_state == WorkflowState.COMPLETED, state.error_history


def run_self_test() -> dict[str, str]:
    """Run deterministic factory smoke tests and return named results."""
    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="factory-self-test-") as tmp:
        root = Path(tmp)
        _telegram_intake_smoke()
        results["telegram_intake"] = "PASS"
        _workflow_smoke(root)
        results["mock_workflow"] = "PASS"
    return results


if __name__ == "__main__":
    for name, result in run_self_test().items():
        print(f"{name}: {result}")
    print("SELF-TEST: PASS")
