from factory.company_os import get_contract
from factory.skills_registry import discover
from factory.handoffs import create_handoff, list_handoffs
from factory.project_memory import update_project_memory, read_project_memory

def test_contract_and_skill_discovery(tmp_path):
    assert get_contract("manager").role == "manager"
    assert "security" in [s.name for s in discover("Flutter app with authentication and payments")]

def test_project_memory_and_handoff(tmp_path):
    update_project_memory(str(tmp_path), "p1", "PLANNING", "planning complete", ["auth"])
    assert read_project_memory(str(tmp_path))["project_id"] == "p1"
    create_handoff(str(tmp_path), "p1", "manager", "architect", "design architecture",
                   ["REQUIREMENTS.md"], ["ARCHITECTURE.md"], ["coverage"])
    assert len(list_handoffs(str(tmp_path))) == 1
