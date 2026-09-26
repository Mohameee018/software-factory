from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from factory.models import WorkflowEvent

@dataclass(frozen=True)
class Budget:
    max_agent_runs: int = 250
    max_project_seconds: int = 0
    max_agent_runs_by_role: dict[str, int] | None = None

class BudgetManager:
    def __init__(self, db, settings):
        self.db = db
        self.budget = Budget(
            int(getattr(settings, "max_agent_runs", 250)),
            int(getattr(settings, "max_project_seconds", 0)),
            getattr(settings, "max_agent_runs_by_role", None),
        )

    def used_agent_runs(self, project_id):
        with self.db.conn() as c:
            return int(c.execute(
                "SELECT COUNT(*) FROM agent_runs WHERE project_id=?", (project_id,)
            ).fetchone()[0])

    def role_agent_runs(self, project_id, role):
        with self.db.conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM agent_runs WHERE project_id=? AND agent_name=?", (project_id, role)).fetchone()[0])

    def allowed_role(self, project_id, role):
        limits = self.budget.max_agent_runs_by_role or {}
        limit = int(limits.get(role, 0))
        return limit <= 0 or self.role_agent_runs(project_id, role) < limit

    def project_seconds(self, project_id):
        project = self.db.get_project(project_id)
        if not project or self.budget.max_project_seconds <= 0:
            return 0
        return max(0, int((datetime.now(timezone.utc) - project.created_at).total_seconds()))

    def allowed(self, project_id):
        if self.budget.max_agent_runs > 0 and self.used_agent_runs(project_id) >= self.budget.max_agent_runs:
            return False
        if self.budget.max_project_seconds > 0 and self.project_seconds(project_id) >= self.budget.max_project_seconds:
            return False
        return True

    def check_role_or_event(self, project_id, role):
        if self.allowed_role(project_id, role) and self.allowed(project_id):
            return True
        self.db.event(WorkflowEvent(project_id=project_id, event_type="AGENT_BUDGET_EXHAUSTED", details={"agent": role, "role_limit": (self.budget.max_agent_runs_by_role or {}).get(role, 0), "role_used": self.role_agent_runs(project_id, role), "global_used": self.used_agent_runs(project_id)}))
        return False

    def check_or_event(self, project_id):
        if self.allowed(project_id):
            return True
        self.db.event(WorkflowEvent(
            project_id=project_id,
            event_type="BUDGET_EXHAUSTED",
            details={
                "max_agent_runs": self.budget.max_agent_runs,
                "max_project_seconds": self.budget.max_project_seconds,
                "used_agent_runs": self.used_agent_runs(project_id),
                "project_seconds": self.project_seconds(project_id),
            },
        ))
        return False
