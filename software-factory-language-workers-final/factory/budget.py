from __future__ import annotations
from dataclasses import dataclass
from factory.models import WorkflowEvent
@dataclass(frozen=True)
class Budget:
    max_agent_runs:int=250
    max_project_seconds:int=0
class BudgetManager:
    def __init__(self,db,settings):
        self.db=db; self.budget=Budget(int(getattr(settings,'max_agent_runs',250)),int(getattr(settings,'max_project_seconds',0)))
    def used_agent_runs(self,project_id):
        with self.db.conn() as c:return int(c.execute("SELECT COUNT(*) FROM agent_runs WHERE project_id=?",(project_id,)).fetchone()[0])
    def allowed(self,project_id):
        return self.budget.max_agent_runs<=0 or self.used_agent_runs(project_id)<self.budget.max_agent_runs
    def check_or_event(self,project_id):
        if self.allowed(project_id): return True
        self.db.event(WorkflowEvent(project_id=project_id,event_type='BUDGET_EXHAUSTED',details={'max_agent_runs':self.budget.max_agent_runs}))
        return False
