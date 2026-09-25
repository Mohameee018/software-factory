from factory.models import WorkflowState,AgentResult

def decide_after(result, current, retries, max_retries):
 if not result.success:
  return WorkflowState.FIXING if retries<max_retries else WorkflowState.BLOCKED
 n=result.next_action
 return {'analyze':WorkflowState.ANALYSIS,'create_tasks':WorkflowState.TASK_CREATION,'test':WorkflowState.TESTING,'fix':WorkflowState.FIXING,'review':WorkflowState.REVIEWING,'security':WorkflowState.SECURITY_REVIEW,'ready':WorkflowState.READY_FOR_HUMAN}.get(n,current)
