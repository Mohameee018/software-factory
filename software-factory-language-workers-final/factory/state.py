from __future__ import annotations
from factory.models import WorkflowState
class InvalidTransition(ValueError): pass
TRANSITIONS={
 WorkflowState.IDEA:{WorkflowState.PLANNING,WorkflowState.BLOCKED,WorkflowState.CANCELLED,WorkflowState.PAUSED},
 WorkflowState.PLANNING:{WorkflowState.DOCUMENTATION,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.DOCUMENTATION:{WorkflowState.ANALYSIS,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.ANALYSIS:{WorkflowState.TASK_CREATION,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.TASK_CREATION:{WorkflowState.IMPLEMENTATION,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.IMPLEMENTATION:{WorkflowState.TESTING,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.TESTING:{WorkflowState.REVIEWING,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.REVIEWING:{WorkflowState.SECURITY_REVIEW,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.SECURITY_REVIEW:{WorkflowState.READY_FOR_HUMAN,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.FIXING:{WorkflowState.IMPLEMENTATION,WorkflowState.TESTING,WorkflowState.REVIEWING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED},
 WorkflowState.READY_FOR_HUMAN:{WorkflowState.CHANGES_REQUESTED,WorkflowState.COMPLETED,WorkflowState.CANCELLED,WorkflowState.PAUSED},
 WorkflowState.CHANGES_REQUESTED:{WorkflowState.TASK_CREATION,WorkflowState.BLOCKED,WorkflowState.PAUSED},
 WorkflowState.BLOCKED:{WorkflowState.PLANNING,WorkflowState.TASK_CREATION,WorkflowState.IMPLEMENTATION,WorkflowState.FIXING,WorkflowState.CANCELLED,WorkflowState.PAUSED},
 WorkflowState.FAILED:{WorkflowState.PLANNING,WorkflowState.CANCELLED,WorkflowState.PAUSED},
 WorkflowState.PAUSED:{WorkflowState.IDEA,WorkflowState.PLANNING,WorkflowState.DOCUMENTATION,WorkflowState.ANALYSIS,WorkflowState.TASK_CREATION,WorkflowState.IMPLEMENTATION,WorkflowState.TESTING,WorkflowState.REVIEWING,WorkflowState.SECURITY_REVIEW,WorkflowState.FIXING,WorkflowState.READY_FOR_HUMAN,WorkflowState.BLOCKED,WorkflowState.CANCELLED},
 WorkflowState.COMPLETED:set(), WorkflowState.CANCELLED:set()
}
def can_transition(a,b): return b in TRANSITIONS.get(a,set())
def transition(a,b):
 if not can_transition(a,b): raise InvalidTransition(f'Invalid workflow transition: {a.value} -> {b.value}')
 return b
