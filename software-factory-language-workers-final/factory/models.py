from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field

def now(): return datetime.now(timezone.utc)
def new_id(prefix): return f"{prefix}_{uuid.uuid4().hex[:12]}"
class WorkflowState(str, Enum):
    IDEA='IDEA'; DESIGNING='DESIGNING'; WAITING_FOR_DESIGN_APPROVAL='WAITING_FOR_DESIGN_APPROVAL'; DESIGN_APPROVED='DESIGN_APPROVED'; PLANNING='PLANNING'; DOCUMENTATION='DOCUMENTATION'; ANALYSIS='ANALYSIS'; TASK_CREATION='TASK_CREATION'; IMPLEMENTATION='IMPLEMENTATION'; TESTING='TESTING'; REVIEWING='REVIEWING'; SECURITY_REVIEW='SECURITY_REVIEW'; FIXING='FIXING'; READY_FOR_HUMAN='READY_FOR_HUMAN'; CHANGES_REQUESTED='CHANGES_REQUESTED'; COMPLETED='COMPLETED'; PAUSED='PAUSED'; BLOCKED='BLOCKED'; FAILED='FAILED'; CANCELLED='CANCELLED'
class ProjectStatus(str, Enum):
    CREATED='CREATED'; PLANNING='PLANNING'; DOCUMENTATION_READY='DOCUMENTATION_READY'; TASKS_READY='TASKS_READY'; IMPLEMENTING='IMPLEMENTING'; TESTING='TESTING'; REVIEWING='REVIEWING'; FIXING='FIXING'; READY_FOR_HUMAN_REVIEW='READY_FOR_HUMAN_REVIEW'; CHANGES_REQUESTED='CHANGES_REQUESTED'; COMPLETED='COMPLETED'; BLOCKED='BLOCKED'; FAILED='FAILED'; PAUSED='PAUSED'
class TaskStatus(str, Enum): PENDING='PENDING'; READY='READY'; IN_PROGRESS='IN_PROGRESS'; BLOCKED='BLOCKED'; TESTING='TESTING'; REVIEW='REVIEW'; FAILED='FAILED'; DONE='DONE'
class Priority(str, Enum): LOW='LOW'; MEDIUM='MEDIUM'; HIGH='HIGH'; CRITICAL='CRITICAL'
TaskPriority=Priority
class Severity(str, Enum): INFO='INFO'; LOW='LOW'; MEDIUM='MEDIUM'; HIGH='HIGH'; CRITICAL='CRITICAL'
class ApprovalStatus(str, Enum): PENDING='PENDING'; APPROVED='APPROVED'; REJECTED='REJECTED'; EXPIRED='EXPIRED'
class ProjectType(str, Enum): UNKNOWN='unknown'; FLUTTER='flutter'; PYTHON='python'; JAVA='java'; TYPESCRIPT='typescript'; REACT='react'; NODE='node'
class RetryPolicy(BaseModel):
    max_retries_per_task:int=5
    escalate_after_repeated_errors:int=2
class ApprovalPolicy(BaseModel):
    require_approval_for_destructive_ops:bool=True
    require_approval_for_dependency_install:bool=True
    require_approval_for_deploy:bool=True
class Project(BaseModel):
    id:str=Field(default_factory=lambda:new_id('proj')); name:str; description:str; status:ProjectStatus=ProjectStatus.CREATED; project_type:ProjectType=ProjectType.UNKNOWN; current_state:WorkflowState=WorkflowState.IDEA; workspace_path:str; repository_path:str|None=None; git_branch:str='main'; acceptance_criteria:list[str]=Field(default_factory=list); retry_policy:RetryPolicy=Field(default_factory=RetryPolicy); approval_policy:ApprovalPolicy=Field(default_factory=ApprovalPolicy); created_at:datetime=Field(default_factory=now); updated_at:datetime=Field(default_factory=now)
class Task(BaseModel):
    id:str=Field(default_factory=lambda:new_id('task')); project_id:str; title:str; description:str; status:TaskStatus=TaskStatus.PENDING; priority:Priority=Priority.MEDIUM; dependencies:list[str]=Field(default_factory=list); assigned_agent:str|None=None; acceptance_criteria:list[str]=Field(default_factory=list); files_expected:list[str]=Field(default_factory=list); tests_required:list[str]=Field(default_factory=list); retry_count:int=0; created_at:datetime=Field(default_factory=now); updated_at:datetime=Field(default_factory=now); completed_at:datetime|None=None; failure_reason:str|None=None
class AgentResult(BaseModel):
    success:bool; agent_name:str; task_id:str|None=None; summary:str=''; detailed_output:dict[str,Any]|str=Field(default_factory=dict); files_created:list[str]=Field(default_factory=list); files_modified:list[str]=Field(default_factory=list); files_deleted:list[str]=Field(default_factory=list); files_to_create:list[str]=Field(default_factory=list); files_to_modify:list[str]=Field(default_factory=list); files_to_delete:list[str]=Field(default_factory=list); generated_changes:list[dict[str,Any]]=Field(default_factory=list); commands_requested:list[str]=Field(default_factory=list); commands_executed:list[str]=Field(default_factory=list); tests_to_run:list[str]=Field(default_factory=list); tests_run:list[str]=Field(default_factory=list); warnings:list[str]=Field(default_factory=list); errors:list[str]=Field(default_factory=list); next_action:str|None=None; timestamp:datetime=Field(default_factory=now)
class ReviewFinding(BaseModel):
    id:str=Field(default_factory=lambda:new_id('find')); severity:Severity; category:str; file:str|None=None; line:int|None=None; description:str; evidence:str=''; suggested_fix:str=''; status:str='OPEN'
class ApprovalRequest(BaseModel):
    id:str=Field(default_factory=lambda:new_id('appr')); project_id:str; task_id:str|None=None; requested_action:str; reason:str; risk_level:Severity; affected_files:list[str]=Field(default_factory=list); created_at:datetime=Field(default_factory=now); status:ApprovalStatus=ApprovalStatus.PENDING; human_response:str|None=None; resolved_at:datetime|None=None
class TestResult(BaseModel):
    id:str=Field(default_factory=lambda:new_id('test')); project_id:str; kind:str; command:str; exit_code:int; stdout:str=''; stderr:str=''; duration_seconds:float=0; passed:bool=False; timestamp:datetime=Field(default_factory=now)
class WorkflowEvent(BaseModel):
    id:str=Field(default_factory=lambda:new_id('evt')); project_id:str; event_type:str; state:str|None=None; task_id:str|None=None; details:dict[str,Any]=Field(default_factory=dict); timestamp:datetime=Field(default_factory=now)
class FactoryState(BaseModel):
    factory_run_id:str=Field(default_factory=lambda:new_id('run')); project_id:str; project_name:str; project_type:ProjectType; current_state:WorkflowState; current_task:str|None=None; task_queue:list[str]=Field(default_factory=list); completed_tasks:list[str]=Field(default_factory=list); failed_tasks:list[str]=Field(default_factory=list); blocked_tasks:list[str]=Field(default_factory=list); agent_results:list[str]=Field(default_factory=list); test_results:list[str]=Field(default_factory=list); review_findings:list[str]=Field(default_factory=list); security_findings:list[str]=Field(default_factory=list); approvals:list[str]=Field(default_factory=list); retry_counts:dict[str,int]=Field(default_factory=dict); iteration_count:int=0; git_branch:str='main'; workspace_path:str=''; generated_artifacts:list[str]=Field(default_factory=list); timestamps:dict[str,str]=Field(default_factory=dict); error_history:list[str]=Field(default_factory=list); human_feedback:list[str]=Field(default_factory=list); acceptance_criteria:list[str]=[]; paused_from:WorkflowState|None=None
