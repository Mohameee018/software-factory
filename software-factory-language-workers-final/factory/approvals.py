from datetime import datetime, timezone
from factory.models import ApprovalRequest, ApprovalStatus, Severity, WorkflowEvent
class ApprovalService:
    def __init__(self,db): self.db=db
    def request(self,project_id,action,reason,risk=Severity.HIGH,task_id=None,files=None):
        a=ApprovalRequest(project_id=project_id,task_id=task_id,requested_action=action,reason=reason,risk_level=risk,affected_files=files or [])
        self.db.approval(a); self.db.event(WorkflowEvent(project_id=project_id,event_type='APPROVAL_REQUESTED',task_id=task_id,details={'approval_id':a.id})); return a
    def resolve(self,a,approved,response):
        current=self.db.get_approval(a.id)
        if not current: raise ValueError('Approval not found')
        if current.status != ApprovalStatus.PENDING: return current
        current.status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        current.human_response=response; current.resolved_at=datetime.now(timezone.utc); self.db.approval(current)
        self.db.event(WorkflowEvent(project_id=current.project_id,event_type='APPROVAL_RESOLVED',task_id=current.task_id,details={'approval_id':current.id,'approved':approved}))
        return current
