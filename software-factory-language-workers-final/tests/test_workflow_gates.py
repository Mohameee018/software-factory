from pathlib import Path
from factory.gates import verify
from factory.models import AgentResult, Task, WorkflowState

def test_design_gate_requires_preview(tmp_path):
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "DESIGN.md").write_text("design", encoding="utf-8")
    result=AgentResult(success=True, agent_name="UI/UX Designer Agent", files_created=["docs/DESIGN.md"])
    errors=verify(WorkflowState.WAITING_FOR_DESIGN_APPROVAL,str(tmp_path),result)
    assert "missing_design_artifact:docs/design/preview.html" in errors

def test_implementation_gate_requires_evidence(tmp_path):
    task=Task(project_id="p",title="Implement",description="Implement")
    result=AgentResult(success=True,agent_name="Developer Agent",task_id=task.id)
    errors=verify(WorkflowState.IMPLEMENTATION,str(tmp_path),result,task)
    assert "developer_produced_no_file_changes" in errors

def test_final_gate_requires_all_reports(tmp_path):
    required=("DESIGN.md","PRD.md","ARCHITECTURE.md","ACCEPTANCE_CRITERIA.md","TEST_REPORT.md","CODE_REVIEW.md","UX_REVIEW.md","SECURITY_REVIEW.md")
    (tmp_path/"docs").mkdir()
    for name in required:
        (tmp_path/"docs"/name).write_text("ok",encoding="utf-8")
    assert verify(WorkflowState.READY_FOR_HUMAN,str(tmp_path)) == []
