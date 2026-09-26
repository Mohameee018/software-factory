from types import SimpleNamespace
from pathlib import Path

from factory.models import ProjectType, WorkflowState
from factory.project_manager import ProjectManager


class FakeDB:
    def __init__(self):
        self.projects = {}
        self.active = {}
    def get_active_project(self, user_id):
        return self.active.get(user_id)
    def get_project(self, project_id):
        return self.projects.get(project_id)
    def get_state(self, project_id):
        return SimpleNamespace(timestamps={"last_agent": "2026-09-26T17:00:00+00:00"})
    def list_events(self, project_id, limit):
        return []


class FakeService:
    def __init__(self):
        self.db = FakeDB()
        self.settings = SimpleNamespace(ai_timeout=10)
        self.model_router = SimpleNamespace()
        self.project = SimpleNamespace(
            id="proj_test", name="Tasbeeh", project_type=ProjectType.FLUTTER,
            current_state=WorkflowState.WAITING_FOR_DESIGN_APPROVAL,
        )
        self.db.projects[self.project.id] = self.project
        self.db.active[123] = self.project.id


def test_manager_routes_artifact_question_without_ai_call():
    service = FakeService()
    manager = ProjectManager(service)

    result = manager.route(123, "فين الصورة؟")

    assert result["intent"] == "artifact"


def test_manager_routes_status_question_without_ai_call():
    service = FakeService()
    manager = ProjectManager(service)

    result = manager.route(123, "وصلتوا لأيه؟")

    assert result["intent"] == "status"


def test_manager_status_reflects_waiting_state():
    service = FakeService()
    manager = ProjectManager(service)

    message = manager.status_message(service.project)

    assert "WAITING_FOR_DESIGN_APPROVAL" in message
    assert "مستني قرار منك" in message


def test_manager_routes_approval_ack_as_approve():
    service = FakeService()
    service.project.current_state = WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL
    manager = ProjectManager(service)

    result = manager.route(123, "تمام")

    assert result["intent"] == "approve"
