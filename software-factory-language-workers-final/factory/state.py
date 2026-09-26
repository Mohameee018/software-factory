from __future__ import annotations
from factory.models import WorkflowState
class InvalidTransition(ValueError): pass
TRANSITIONS={
 WorkflowState.IDEA:{WorkflowState.REQUIREMENTS_GATHERING,WorkflowState.DESIGNING,WorkflowState.BLOCKED,WorkflowState.CANCELLED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.REQUIREMENTS_GATHERING:{WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},\n WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL:{WorkflowState.REQUIREMENTS_GATHERING,WorkflowState.DESIGNING,WorkflowState.CANCELLED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},\n WorkflowState.DESIGNING:{WorkflowState.WAITING_FOR_DESIGN_APPROVAL,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.WAITING_FOR_DESIGN_APPROVAL:{WorkflowState.DESIGNING,WorkflowState.DESIGN_APPROVED,WorkflowState.CANCELLED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.DESIGN_APPROVED:{WorkflowState.PLANNING,WorkflowState.BLOCKED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.PLANNING:{WorkflowState.DOCUMENTATION,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.DOCUMENTATION:{WorkflowState.ANALYSIS,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.ANALYSIS:{WorkflowState.ARCHITECTURE,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.ARCHITECTURE:{WorkflowState.TASK_CREATION,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.TASK_CREATION:{WorkflowState.PLANNING,WorkflowState.IMPLEMENTATION,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.IMPLEMENTATION:{WorkflowState.TESTING,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.TESTING:{WorkflowState.REVIEWING,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.REVIEWING:{WorkflowState.UX_REVIEW,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.UX_REVIEW:{WorkflowState.SECURITY_REVIEW,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.SECURITY_REVIEW:{WorkflowState.READY_FOR_HUMAN,WorkflowState.FIXING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.FIXING:{WorkflowState.IMPLEMENTATION,WorkflowState.TESTING,WorkflowState.REVIEWING,WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.READY_FOR_HUMAN:{WorkflowState.CHANGES_REQUESTED,WorkflowState.COMPLETED,WorkflowState.CANCELLED,WorkflowState.PAUSED},
 WorkflowState.CHANGES_REQUESTED:{WorkflowState.TASK_CREATION,WorkflowState.BLOCKED,WorkflowState.PAUSED,WorkflowState.WAITING_FOR_QUOTA},
 WorkflowState.BLOCKED:{WorkflowState.PLANNING,WorkflowState.TASK_CREATION,WorkflowState.IMPLEMENTATION,WorkflowState.FIXING,WorkflowState.CANCELLED,WorkflowState.PAUSED},
 WorkflowState.FAILED:{WorkflowState.PLANNING,WorkflowState.CANCELLED,WorkflowState.PAUSED},
 WorkflowState.PAUSED:{WorkflowState.IDEA,WorkflowState.REQUIREMENTS_GATHERING,WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL,WorkflowState.DESIGNING,WorkflowState.WAITING_FOR_DESIGN_APPROVAL,WorkflowState.DESIGN_APPROVED,WorkflowState.PLANNING,WorkflowState.DOCUMENTATION,WorkflowState.ANALYSIS,WorkflowState.ARCHITECTURE,WorkflowState.TASK_CREATION,WorkflowState.IMPLEMENTATION,WorkflowState.TESTING,WorkflowState.REVIEWING,WorkflowState.SECURITY_REVIEW,WorkflowState.FIXING,WorkflowState.READY_FOR_HUMAN,WorkflowState.BLOCKED,WorkflowState.CANCELLED},
 WorkflowState.WAITING_FOR_QUOTA:{WorkflowState.IDEA,WorkflowState.REQUIREMENTS_GATHERING,WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL,WorkflowState.DESIGNING,WorkflowState.WAITING_FOR_DESIGN_APPROVAL,WorkflowState.DESIGN_APPROVED,WorkflowState.PLANNING,WorkflowState.DOCUMENTATION,WorkflowState.ANALYSIS,WorkflowState.ARCHITECTURE,WorkflowState.TASK_CREATION,WorkflowState.IMPLEMENTATION,WorkflowState.TESTING,WorkflowState.REVIEWING,WorkflowState.UX_REVIEW,WorkflowState.SECURITY_REVIEW,WorkflowState.FIXING,WorkflowState.READY_FOR_HUMAN,WorkflowState.BLOCKED,WorkflowState.CANCELLED},
 WorkflowState.COMPLETED:set(), WorkflowState.CANCELLED:set()
}
def can_transition(a,b): return b in TRANSITIONS.get(a,set())
def transition(a,b):
 if not can_transition(a,b): raise InvalidTransition(f'Invalid workflow transition: {a.value} -> {b.value}')
 return b
