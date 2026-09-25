from __future__ import annotations
import threading
import time
from pathlib import Path
from factory.database import Database
from factory.models import Project, ProjectType, WorkflowState, Task, TaskStatus, ApprovalRequest, Severity
from factory.queue import PersistentJobQueue, FactoryWorker, JobStatus


def make_project(db, tmp_path):
    p=Project(name='Cloud',description='test',project_type=ProjectType.PYTHON,workspace_path=str(tmp_path/'p'))
    Path(p.workspace_path).mkdir(parents=True)
    db.save_project(p)
    db.save_state(__import__('factory.models',fromlist=['FactoryState']).FactoryState(project_id=p.id,project_name=p.name,project_type=p.project_type,current_state=p.current_state,workspace_path=p.workspace_path))
    return p


def test_job_persists_and_claims_once(tmp_path):
    db=Database(tmp_path/'factory.db'); p=make_project(db,tmp_path)
    q=PersistentJobQueue(db)
    jid=q.enqueue(p.id,priority=99)
    assert db.list_jobs(p.id)[0][0] == jid
    claimed=[]
    def claim(): claimed.append(q.claim('w'))
    a=threading.Thread(target=claim); b=threading.Thread(target=claim); a.start(); b.start(); a.join(); b.join()
    assert sum(x is not None for x in claimed) == 1
    assert db.list_jobs(p.id)[0][3] == JobStatus.RUNNING.value


def test_restart_recovery_requeues_running_job(tmp_path):
    db=Database(tmp_path/'factory.db'); p=make_project(db,tmp_path); q=PersistentJobQueue(db)
    jid=q.enqueue(p.id); assert q.claim('dead-worker')
    db.recover_jobs()
    row=db.list_jobs(p.id)[0]
    assert row[3] in {JobStatus.RETRYING.value, JobStatus.PENDING.value}
    assert row[10] == 'recovered'


def test_approval_survives_restart(tmp_path):
    db=Database(tmp_path/'factory.db'); p=make_project(db,tmp_path)
    a=ApprovalRequest(project_id=p.id,requested_action='pip install x',reason='dependency',risk_level=Severity.MEDIUM)
    db.approval(a)
    db2=Database(tmp_path/'factory.db')
    assert db2.get_approval(a.id).status.value == 'PENDING'


def test_multiple_projects_have_isolated_jobs_and_workspaces(tmp_path):
    db=Database(tmp_path/'factory.db'); p1=make_project(db,tmp_path/'a'); p2=make_project(db,tmp_path/'b'); q=PersistentJobQueue(db)
    j1=q.enqueue(p1.id); j2=q.enqueue(p2.id)
    assert {r[1] for r in db.list_jobs()} == {p1.id,p2.id}
    assert p1.workspace_path != p2.workspace_path


def test_active_project_persists_by_telegram_user(tmp_path):
    db=Database(tmp_path/'factory.db'); p=make_project(db,tmp_path)
    db.set_active_project(123,p.id)
    db2=Database(tmp_path/'factory.db')
    assert db2.get_active_project(123)==p.id


def test_cancel_project_cancels_pending_jobs(tmp_path):
    db=Database(tmp_path/'factory.db'); p=make_project(db,tmp_path); q=PersistentJobQueue(db)
    q.enqueue(p.id); q.cancel_project(p.id)
    assert db.list_jobs(p.id)[0][3] == JobStatus.CANCELLED.value


def test_worker_executes_queued_job(tmp_path):
    db=Database(tmp_path/'factory.db'); p=make_project(db,tmp_path); q=PersistentJobQueue(db)
    q.enqueue(p.id)
    class FakeOrchestrator:
        def __init__(self): self.db=db; self.settings=type('S',(),{'job_max_retries':5})()
        def run(self,*args,**kwargs):
            return type('State',(),{'current_state':WorkflowState.COMPLETED})()
    w=FactoryWorker(FakeOrchestrator(),q,poll_interval=.01)
    assert w.run_once() is True
    assert db.list_jobs(p.id)[0][3] == JobStatus.COMPLETED.value
