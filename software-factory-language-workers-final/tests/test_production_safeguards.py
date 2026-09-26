from factory.company_os import get_contract, select_team
from factory.budget import BudgetManager
from factory.artifacts import record_artifacts
from factory.database import Database
from factory.models import Project


class S:
    max_agent_runs=2
    max_project_seconds=0


def test_dynamic_company_roles():
    team=select_team("Large Flutter app with API, cloud deployment and documentation")
    assert "techlead" in team
    assert "devops" in team
    assert "writer" in team
    assert "uiux" in team
    assert "handoff" in team
    assert get_contract("devops").role=="devops"


def test_budget_stops_after_agent_limit(tmp_path):
    db=Database(tmp_path/"factory.db")
    p=Project(name="Budget",description="x",workspace_path=str(tmp_path/"p"))
    db.save_project(p)
    db.agent_result(p.id, __import__("factory.models",fromlist=["AgentResult"]).AgentResult(success=True,agent_name="x"))
    db.agent_result(p.id, __import__("factory.models",fromlist=["AgentResult"]).AgentResult(success=True,agent_name="y"))
    assert not BudgetManager(db,S).allowed(p.id)


def test_artifact_manifest_versions(tmp_path):
    root=tmp_path/"p"; (root/"docs").mkdir(parents=True)
    db=Database(tmp_path/"factory.db")
    p=Project(name="Artifacts",description="x",workspace_path=str(root))
    db.save_project(p)
    f=root/"docs"/"A.txt"; f.write_text("one",encoding="utf-8")
    record_artifacts(str(root),p.id,db,["docs/A.txt"])
    f.write_text("two",encoding="utf-8")
    record_artifacts(str(root),p.id,db,["docs/A.txt"])
    import json
    manifest=json.loads((root/"docs"/"ARTIFACT_MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest["artifacts"]["docs/A.txt"]["versions"])==2


def test_job_lease_recovery_and_project_exclusion(tmp_path):
    db=Database(tmp_path/"factory.db")
    p1=Project(name="One",description="x",workspace_path=str(tmp_path/"one")); p2=Project(name="Two",description="x",workspace_path=str(tmp_path/"two"))
    db.save_project(p1); db.save_project(p2)
    j1=db.enqueue_job(p1.id,priority=50); j2=db.enqueue_job(p1.id,priority=100); j3=db.enqueue_job(p2.id,priority=10)
    claimed=db.claim_job("w1")
    assert claimed and claimed.project_id==p1.id
    next_job=db.claim_job("w2")
    assert next_job and next_job.project_id==p2.id
