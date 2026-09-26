from pathlib import Path
from factory.company_os import get_contract, select_team
from factory.traceability import write_report

def test_company_os_selects_dynamic_team():
    team=select_team("Flutter mobile app with web dashboard and authentication", "flutter")
    assert "manager" in team
    assert "architect" in team
    assert "uiux" in team
    assert "security" in team
    assert get_contract("developer").role=="developer"

def test_traceability_requires_every_requirement_to_map(tmp_path):
    docs=tmp_path/"docs"; docs.mkdir()
    (docs/"REQUIREMENTS.md").write_text("# Requirements\n- User authentication must support email login\n- Orders must support variants\n")
    (docs/"PRD.md").write_text("# PRD\n- authentication\n- variants\n")
    (docs/"ACCEPTANCE_CRITERIA.md").write_text("# Acceptance\n- login works\n")
    (docs/"TASKS.md").write_text("1. Implement email authentication | acceptance: login works\n2. Implement product variants and order variants\n")
    report=write_report(str(tmp_path))
    assert report.complete
    assert not report.unmapped
    assert (docs/"TRACEABILITY.md").exists()
