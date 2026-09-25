from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import re
from factory.models import *
from factory.state import transition
from factory.database import Database
from factory.agents import PlannerAgent, AnalyzerAgent, DeveloperAgent, TesterAgent, ReviewerAgent, SecurityAgent, ReleaseAgent, UIUXAgent, UIUXReviewerAgent
from factory.approvals import ApprovalService
from factory.adapters.registry import detect, by_name
from factory.project_detection import detect_project_type
from factory.tools.shell import run as run_command
from factory.tools.git import init_repo
from factory.providers.registry import build_provider
from factory.providers.mock import MockProvider

@dataclass
class Context:
    project: Project
    workspace: str
    timeout: int

class Orchestrator:
    def __init__(self, db, settings, notifier=None):
        self.db, self.settings, self.notifier = db, settings, notifier
        self.job_queue = None
        provider = build_provider(settings)
        self.agents = {
            'planner': PlannerAgent(provider), 'analyzer': AnalyzerAgent(provider),
            'developer': DeveloperAgent(provider), 'tester': TesterAgent(),
            'reviewer': ReviewerAgent(provider), 'uiux_reviewer': UIUXReviewerAgent(provider), 'security': SecurityAgent(), 'release': ReleaseAgent(), 'uiux': UIUXAgent(provider)
        }

    def provider_info(self):
        provider = self.agents['planner'].provider
        configured = isinstance(provider, MockProvider) or bool(getattr(provider, 'api_key', None))
        return {'provider': self.settings.provider, 'model': self.settings.model, 'configured': configured, 'mock': isinstance(provider, MockProvider)}

    def authorized(self, update):
        uid = update.effective_user.id if update.effective_user else None
        cid = update.effective_chat.id if update.effective_chat else None
        users, chats = self.settings.telegram_allowed_user_ids, self.settings.telegram_allowed_chat_ids
        if not users and not chats: return False
        return (not users or uid in users) and (not chats or cid in chats)

    def create_project(self, name, description, project_type=None):
        detected_type = detect_project_type(description) if project_type is None or project_type == ProjectType.UNKNOWN else project_type
        pid = new_id('proj'); w = (self.settings.workspaces_root / pid).resolve(); w.mkdir(parents=True, exist_ok=True)
        init_repo(w)
        branch_name = f'factory/{pid}'
        branch_result = run_command('developer', f'git checkout -b {branch_name}', w)
        p = Project(id=pid, name=name, description=description, project_type=detected_type, workspace_path=str(w), repository_path=str(w), git_branch=branch_name)
        self.db.save_project(p)
        self.db.save_state(FactoryState(project_id=p.id, project_name=p.name, project_type=p.project_type, current_state=p.current_state, workspace_path=p.workspace_path, git_branch=branch_name, acceptance_criteria=p.acceptance_criteria))
        self.db.event(WorkflowEvent(project_id=p.id, event_type='PROJECT_CREATED', state=p.current_state.value, details={'project_type': detected_type.value, 'git_branch': branch_name, 'branch_created': branch_result.exit_code == 0}))
        return p

    def _prepare_flutter_project(self, p, state):
        # Validate Flutter and create a new empty Flutter workspace without fetching dependencies.
        adapter = by_name('flutter')
        if not adapter:
            state.error_history.append('Flutter adapter is not available.')
            self.db.save_state(state)
            return False
        for kind, command in (('flutter_environment', adapter.validate_environment()), ('dart_environment', 'dart --version')):
            env = run_command('developer', command, p.workspace_path, self.settings.command_timeout)
            self.db.event(WorkflowEvent(project_id=p.id, event_type='COMMAND_RESULT', details={'kind': kind, 'command': env.command, 'exit_code': env.exit_code, 'stdout': env.stdout, 'stderr': env.stderr, 'duration_seconds': env.duration_seconds}))
            if env.exit_code != 0:
                tool = 'Flutter SDK' if kind == 'flutter_environment' else 'Dart SDK'
                state.error_history.append(f'{tool} is unavailable. Install {tool} and ensure it is on PATH.')
                self.db.save_state(state)
                return False
        pubspec = Path(p.workspace_path) / 'pubspec.yaml'
        if pubspec.exists():
            return True
        files = [x for x in Path(p.workspace_path).rglob('*') if x.is_file() and '.git' not in x.parts]
        if files:
            state.error_history.append('Flutter workspace is not empty and has no pubspec.yaml; refusing to overwrite existing files.')
            self.db.save_state(state)
            return False
        created = run_command('developer', 'flutter create --no-pub .', p.workspace_path, self.settings.command_timeout)
        self.db.event(WorkflowEvent(project_id=p.id, event_type='COMMAND_RESULT', details={'kind': 'flutter_create', 'command': created.command, 'exit_code': created.exit_code, 'stdout': created.stdout, 'stderr': created.stderr, 'duration_seconds': created.duration_seconds}))
        if created.exit_code != 0:
            state.error_history.append(f'Flutter project creation failed: {created.stderr[-4000:]}')
            self.db.save_state(state)
            return False
        return True

    def _flutter_dependencies_approved(self, p, state):
        approvals = self.db.list_approvals(p.id)
        existing = [a for a in approvals if a.requested_action == 'flutter pub get']
        for a in existing:
            if a.status == ApprovalStatus.APPROVED:
                return True
            if a.status == ApprovalStatus.PENDING:
                return False
            if a.status == ApprovalStatus.REJECTED:
                return False
        approval = ApprovalService(self.db).request(p.id, 'flutter pub get', 'Flutter dependency installation is required before real validation.', Severity.MEDIUM)
        state.approvals.append(approval.id); self.db.save_state(state)
        if self.notifier:
            try: self.notifier.approval_requested(approval)
            except Exception: pass
        return False

    def set_state(self, p, state):
        if p.current_state == state: return
        p.current_state = transition(p.current_state, state); p.updated_at = datetime.now(timezone.utc)
        self.db.save_project(p); self.db.event(WorkflowEvent(project_id=p.id, event_type='STATE_CHANGED', state=state.value))
        st = self.db.get_state(p.id)
        if st: st.current_state = state; st.timestamps['updated_at'] = p.updated_at.isoformat(); self.db.save_state(st)
        if self.notifier:
            try: self.notifier.state_changed(p, state.value)
            except Exception: pass

    def ensure_tasks(self, p):
        if self.db.list_tasks(p.id): return
        path = Path(p.workspace_path) / 'docs' / 'TASKS.md'
        candidates=[]
        if path.exists():
            for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
                m=re.match(r'^\s*(?:[-*]|\d+[.)])\s+(.+)$', line)
                if m and len(m.group(1)) > 4: candidates.append(m.group(1).strip())
        parsed=[]
        if path.exists():
            for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
                m=re.match(r'^\s*(?:[-*]|\d+[.)])\s+(.+)$', line)
                if not m or len(m.group(1)) <= 4: continue
                raw=m.group(1).strip()
                parts=[x.strip() for x in raw.split('|')]
                title=parts[0]
                meta={'dependencies':[], 'dependencies_explicit':False, 'acceptance_criteria':[], 'files_expected':[], 'tests_required':[]}
                for part in parts[1:]:
                    key,sep,value=part.partition(':')
                    if not sep: continue
                    key=key.strip().casefold(); value=value.strip()
                    if key in ('depends','dependencies'):
                        meta['dependencies']=[int(x.strip()) for x in re.split(r'[, ]+',value) if x.strip().isdigit()]; meta['dependencies_explicit']=True
                    elif key in ('acceptance','acceptance criteria'):
                        meta['acceptance_criteria']=[x.strip() for x in re.split(r';|,',value) if x.strip()]
                    elif key in ('files','expected files'):
                        meta['files_expected']=[x.strip() for x in re.split(r',|;',value) if x.strip()]
                    elif key in ('tests','tests required'):
                        meta['tests_required']=[x.strip() for x in re.split(r',|;',value) if x.strip()]
                parsed.append((title,meta))
        if not parsed:
            parsed=[('Initialize project structure',{}),('Implement requested functionality',{}),('Add automated tests',{})]
        created=[]
        for i,(title,meta) in enumerate(parsed[:30],1):
            dep_ids=[]
            for dep_num in meta.get('dependencies',[]):
                if 1 <= dep_num <= len(created): dep_ids.append(created[dep_num-1].id)
            if not dep_ids and not meta.get('dependencies_explicit') and i > 1: dep_ids=[created[-1].id]
            t=Task(project_id=p.id,title=title,description=title,priority=Priority.HIGH,assigned_agent='developer',dependencies=dep_ids,acceptance_criteria=meta.get('acceptance_criteria',[]),files_expected=meta.get('files_expected',[]),tests_required=meta.get('tests_required',[]))
            self.db.save_task(t); self.db.event(WorkflowEvent(project_id=p.id,event_type='TASK_CREATED',task_id=t.id,details={'dependencies':dep_ids,'acceptance_criteria':t.acceptance_criteria,'files_expected':t.files_expected,'tests_required':t.tests_required})); created.append(t)

    def next_task(self,p):
        tasks=self.db.list_tasks(p.id); done={t.id for t in tasks if t.status==TaskStatus.DONE}
        for t in tasks:
            if t.status in (TaskStatus.PENDING,TaskStatus.READY) and all(d in done for d in t.dependencies): return t
        return None

    def _add_fix_task(self,p,title,description,priority=Priority.HIGH):
        t=Task(project_id=p.id,title=title,description=description,priority=priority,assigned_agent='developer')
        self.db.save_task(t); self.db.event(WorkflowEvent(project_id=p.id,event_type='FIX_TASK_CREATED',task_id=t.id)); return t

    def _get_review_fix_task(self,p,description):
        candidates=[t for t in self.db.list_tasks(p.id) if t.title=='Fix code review findings']
        t=candidates[-1] if candidates else self._add_fix_task(p,'Fix code review findings',description)
        t.description=description; t.failure_reason=description; t.status=TaskStatus.PENDING
        t.retry_count += 1; t.updated_at=datetime.now(timezone.utc); self.db.save_task(t)
        return t

    def _get_ux_fix_task(self,p,description):
        candidates=[t for t in self.db.list_tasks(p.id) if t.title=='Fix UI/UX review findings']
        t=candidates[-1] if candidates else self._add_fix_task(p,'Fix UI/UX review findings',description)
        t.description=description; t.failure_reason=description; t.status=TaskStatus.PENDING
        t.retry_count += 1; t.updated_at=datetime.now(timezone.utc); self.db.save_task(t)
        return t

    def _get_test_fix_task(self,p,description):
        # Keep one persistent QA-fix task so retry_count remains meaningful across
        # repeated test cycles and unrelated implementation tasks are not consumed.
        candidates=[t for t in self.db.list_tasks(p.id) if t.title=='Fix test failures']
        t=candidates[-1] if candidates else self._add_fix_task(p,'Fix test failures',description)
        t.description=description
        t.failure_reason=description
        t.status=TaskStatus.PENDING
        t.retry_count += 1
        t.updated_at=datetime.now(timezone.utc)
        self.db.save_task(t)
        return t

    def add_feedback(self,pid,feedback):
        self.db.feedback(pid,feedback); st=self.db.get_state(pid)
        if st: st.human_feedback.append(feedback); self.db.save_state(st)
        p=self.db.get_project(pid)
        if not p: raise ValueError('Project not found')
        if p.current_state==WorkflowState.WAITING_FOR_DESIGN_APPROVAL:
            self.set_state(p,WorkflowState.DESIGNING)
            f=Path(p.workspace_path)/'docs'/'DESIGN_FEEDBACK.md'; f.parent.mkdir(parents=True,exist_ok=True); f.open('a',encoding='utf-8').write('\n\n'+feedback+'\n')
            self.db.event(WorkflowEvent(project_id=pid,event_type='DESIGN_FEEDBACK_RECEIVED',details={'feedback':feedback}))
            return None
        t=self._add_fix_task(p,'Human feedback',feedback)
        self.db.event(WorkflowEvent(project_id=pid,event_type='FEEDBACK_RECEIVED',task_id=t.id,details={'feedback':feedback}))
        if p.current_state==WorkflowState.READY_FOR_HUMAN:
            self.set_state(p,WorkflowState.CHANGES_REQUESTED); self.set_state(p,WorkflowState.TASK_CREATION)
        return t

    def retry(self,pid):
        p=self.db.get_project(pid)
        if not p: raise ValueError('Project not found')
        if p.current_state == WorkflowState.BLOCKED:
            approvals=self.db.list_approvals(pid)
            latest_dep=next((a for a in approvals if a.requested_action=='flutter pub get'), None)
            if latest_dep and latest_dep.status == ApprovalStatus.APPROVED:
                self.set_state(p, WorkflowState.TESTING)
            elif latest_dep and latest_dep.status == ApprovalStatus.REJECTED:
                approval=ApprovalService(self.db).request(p.id,'flutter pub get','Flutter dependency installation is required before real validation.',Severity.MEDIUM)
                state=self.db.get_state(pid) or FactoryState(project_id=p.id,project_name=p.name,project_type=p.project_type,current_state=p.current_state,workspace_path=p.workspace_path)
                state.approvals.append(approval.id); self.db.save_state(state)
                if self.notifier:
                    try:self.notifier.approval_requested(approval)
                    except Exception:pass
                return state
            elif any('SDK is unavailable' in e or 'workspace is not empty' in e for e in (self.db.get_state(pid).error_history if self.db.get_state(pid) else [])):
                self.set_state(p, WorkflowState.IDEA)
            else:
                raise RuntimeError('Project is blocked. Resolve the blocking condition or provide feedback before retrying.')
        return self.run(pid)

    def resume(self,pid):
        p=self.db.get_project(pid); st=self.db.get_state(pid)
        if not p:return None
        if p.current_state==WorkflowState.PAUSED:
            target=st.paused_from if st and st.paused_from else WorkflowState.IDEA; self.set_state(p,target)
        return self.run(pid)

    def pause(self,pid):
        p=self.db.get_project(pid); st=self.db.get_state(pid)
        if not p:return
        if p.current_state!=WorkflowState.PAUSED:
            if st: st.paused_from=p.current_state; self.db.save_state(st)
            self.set_state(p,WorkflowState.PAUSED)

    def _feedback_for_task(self,p,task):
        state=self.db.get_state(p.id); parts=[]
        if task.failure_reason: parts.append('TEST/IMPLEMENTATION FAILURE:\n'+task.failure_reason)
        if state and state.error_history: parts.append('RECENT ERRORS:\n'+'\n'.join(state.error_history[-5:]))
        return '\n\n'.join(parts)

    def run(self,pid,dry_run=False,mock=False):
        p=self.db.get_project(pid)
        if not p: raise ValueError('Project not found')
        state=self.db.get_state(pid) or FactoryState(project_id=p.id,project_name=p.name,project_type=p.project_type,current_state=p.current_state,workspace_path=p.workspace_path)
        ctx=Context(p,p.workspace_path,self.settings.command_timeout)
        effective_mock = mock or dry_run or self.settings.mode in ('mock','dry-run') or (self.settings.mode == 'auto' and self.settings.provider == 'mock')
        # Recover tasks left IN_PROGRESS by a process/Telegram interruption.
        # Re-running an unfinished task is safer than silently skipping it.
        recovered=False
        for task in self.db.list_tasks(p.id):
            if task.status == TaskStatus.IN_PROGRESS:
                task.status=TaskStatus.PENDING; task.updated_at=datetime.now(timezone.utc); self.db.save_task(task); recovered=True
                self.db.event(WorkflowEvent(project_id=p.id,event_type='TASK_RECOVERED',task_id=task.id,details={'reason':'workflow restart/interruption'}))
        if recovered and p.current_state in (WorkflowState.TESTING, WorkflowState.REVIEWING, WorkflowState.UX_REVIEW, WorkflowState.SECURITY_REVIEW):
            self.set_state(p, WorkflowState.IMPLEMENTATION)
            p=self.db.get_project(pid)
        if p.current_state == WorkflowState.BLOCKED and p.project_type == ProjectType.FLUTTER and not effective_mock:
            dependency_approvals = [a for a in self.db.list_approvals(p.id) if a.requested_action == 'flutter pub get']
            if dependency_approvals and dependency_approvals[-1].status == ApprovalStatus.APPROVED:
                self.set_state(p, WorkflowState.FIXING)
                self.set_state(p, WorkflowState.TESTING)
                p = self.db.get_project(pid)
        for _ in range(self.settings.max_iterations):
            p=self.db.get_project(pid); state=self.db.get_state(pid) or state; state.iteration_count+=1; self.db.save_state(state); s=p.current_state
            if s==WorkflowState.IDEA:
                self.set_state(p,WorkflowState.DESIGNING); continue
            if s==WorkflowState.DESIGNING:
                r=self.agents['uiux'].run(ctx); self.record(state,r)
                if r.success:
                    approval=ApprovalService(self.db).request(p.id,'design_approval','UI/UX design is ready. Approve the design before implementation.',Severity.MEDIUM,files=['docs/DESIGN.md','docs/design/preview.html'])
                    state.approvals.append(approval.id); self.db.save_state(state)
                    if self.notifier:
                        try:self.notifier.design_ready(p,approval,r)
                        except Exception:pass
                    self.set_state(p,WorkflowState.WAITING_FOR_DESIGN_APPROVAL)
                else:self.set_state(p,WorkflowState.BLOCKED)
                continue
            if s==WorkflowState.WAITING_FOR_DESIGN_APPROVAL:
                approvals=[a for a in self.db.list_approvals(p.id) if a.requested_action=='design_approval']; latest=approvals[-1] if approvals else None
                if latest and latest.status==ApprovalStatus.APPROVED:self.set_state(p,WorkflowState.DESIGN_APPROVED)
                elif latest and latest.status==ApprovalStatus.REJECTED:self.set_state(p,WorkflowState.DESIGNING)
                else:return state
                continue
            if s==WorkflowState.DESIGN_APPROVED:
                self.set_state(p,WorkflowState.PLANNING); continue
            if s==WorkflowState.PLANNING:
                r=self.agents['planner'].run(ctx); self.record(state,r); self.set_state(p,WorkflowState.DOCUMENTATION if r.success else WorkflowState.BLOCKED); continue
            if s==WorkflowState.DOCUMENTATION: self.set_state(p,WorkflowState.ANALYSIS); continue
            if s==WorkflowState.ANALYSIS:
                r=self.agents['analyzer'].run(ctx); self.record(state,r); self.set_state(p,WorkflowState.TASK_CREATION if r.success else WorkflowState.BLOCKED); continue
            if s==WorkflowState.TASK_CREATION: self.ensure_tasks(p); self.set_state(p,WorkflowState.IMPLEMENTATION); continue
            if s==WorkflowState.IMPLEMENTATION:
                t=self.next_task(p)
                if not t: self.set_state(p,WorkflowState.TESTING); continue
                t.status=TaskStatus.IN_PROGRESS; t.updated_at=datetime.now(timezone.utc); t.failure_reason=self._feedback_for_task(p,t); self.db.save_task(t)
                if effective_mock:
                    r=AgentResult(success=True,agent_name='Developer Agent',task_id=t.id,summary='Mock implementation.',next_action='test')
                else:
                    r=self.agents['developer'].run(ctx,t)
                self.record(state,r)
                if r.success:
                    t.status=TaskStatus.DONE; t.completed_at=datetime.now(timezone.utc); t.failure_reason=None
                else:
                    t.retry_count+=1; t.status=TaskStatus.PENDING if t.retry_count < self.settings.max_retries else TaskStatus.FAILED; t.failure_reason='\n'.join(r.errors)
                    state.error_history.extend(r.errors[-5:])
                self.db.save_task(t)
                if r.success:
                    # Re-evaluate the persisted task queue before choosing the next
                    # workflow phase.  A successful implementation must never leave
                    # the run stranded in IMPLEMENTATION once all eligible work is done.
                    if self.next_task(p) is None:
                        self.set_state(p,WorkflowState.TESTING)
                    continue
                self.set_state(p,WorkflowState.BLOCKED if t.retry_count>=self.settings.max_retries else WorkflowState.FIXING); continue
            if s==WorkflowState.TESTING:
                if effective_mock:
                    r=AgentResult(success=True,agent_name='Test / QA Agent',summary='Mock QA.',next_action='review')
                elif p.project_type == ProjectType.FLUTTER and not self._flutter_dependencies_approved(p, state):
                    self.set_state(p, WorkflowState.BLOCKED)
                    continue
                else:
                    r=self.agents['tester'].run(ctx)
                self.record(state,r)
                if r.success: self.set_state(p,WorkflowState.REVIEWING)
                else:
                    # QA failures are corrective work, not ordinary queued work.
                    # Always create a dedicated fix task so unrelated pending tasks
                    # cannot consume the failure and prevent the QA->FIXING loop.
                    failure='\n'.join(r.errors) or 'QA reported a test failure.'
                    t=self._get_test_fix_task(p,failure)
                    state.error_history.extend(r.errors[-10:]); self.db.save_state(state)
                    self.set_state(p,WorkflowState.BLOCKED if t.retry_count>=self.settings.max_retries else WorkflowState.FIXING)
                continue
            if s==WorkflowState.REVIEWING:
                if effective_mock: r=AgentResult(success=True,agent_name='Code Reviewer',summary='Mock review.',next_action='security')
                else: r=self.agents['reviewer'].run(ctx)
                self.record(state,r)
                if r.detailed_output and isinstance(r.detailed_output,dict):
                    for raw in r.detailed_output.get('findings',[]):
                        try:
                            f=ReviewFinding.model_validate(raw); self.db.finding(p.id,f); state.review_findings.append(f.id)
                        except Exception: pass
                    self.db.save_state(state)
                if r.success: self.set_state(p,WorkflowState.UX_REVIEW)
                else:
                    desc='\n'.join(f"{x.get('severity')}: {x.get('file')}:{x.get('line')} {x.get('description')} Evidence: {x.get('evidence')} Fix: {x.get('suggested_fix')}" for x in (r.detailed_output or {}).get('findings',[])) if isinstance(r.detailed_output,dict) else '\n'.join(r.errors)
                    t=self._get_review_fix_task(p,desc)
                    self.set_state(p,WorkflowState.BLOCKED if t.retry_count >= self.settings.max_retries else WorkflowState.FIXING)
                continue
            if s==WorkflowState.UX_REVIEW:
                if effective_mock:
                    r=AgentResult(success=True,agent_name='UI/UX Reviewer',summary='Mock UI/UX review passed.',next_action='security')
                else:
                    r=self.agents['uiux_reviewer'].run(ctx)
                self.record(state,r)
                if r.detailed_output and isinstance(r.detailed_output,dict):
                    for raw in r.detailed_output.get('findings',[]):
                        try:
                            f=ReviewFinding.model_validate(raw); self.db.finding(p.id,f); state.review_findings.append(f.id)
                        except Exception: pass
                    self.db.save_state(state)
                if r.success:
                    self.set_state(p,WorkflowState.SECURITY_REVIEW)
                else:
                    findings=(r.detailed_output or {}).get('findings',[]) if isinstance(r.detailed_output,dict) else []
                    desc='\\n'.join(f"{x.get('severity')}: {x.get('file')}:{x.get('line')} {x.get('description')} Evidence: {x.get('evidence')} Fix: {x.get('suggested_fix')}" for x in findings) or '\\n'.join(r.errors)
                    t=self._get_ux_fix_task(p,desc)
                    self.set_state(p,WorkflowState.BLOCKED if t.retry_count>=self.settings.max_retries else WorkflowState.FIXING)
                continue
            if s==WorkflowState.SECURITY_REVIEW:
                r=AgentResult(success=True,agent_name='Security Reviewer',summary='Mock security review.',next_action='ready') if effective_mock else self.agents['security'].run(ctx)
                self.record(state,r)
                if r.success: self.set_state(p,WorkflowState.READY_FOR_HUMAN)
                else:
                    approval=ApprovalService(self.db).request(p.id,'Resolve security finding before continuing','Security reviewer reported a blocking security condition.',Severity.CRITICAL,files=r.errors)
                    state.approvals.append(approval.id); self.db.save_state(state)
                    if self.notifier:
                        try:self.notifier.approval_requested(approval)
                        except Exception:pass
                    self.set_state(p,WorkflowState.BLOCKED)
                continue
            if s==WorkflowState.FIXING: self.set_state(p,WorkflowState.IMPLEMENTATION if self.next_task(p) else WorkflowState.TESTING); continue
            if s==WorkflowState.READY_FOR_HUMAN:
                approvals=[a for a in self.db.list_approvals(p.id) if a.requested_action=='final_approval']
                latest=approvals[-1] if approvals else None
                if latest is None:
                    approval=ApprovalService(self.db).request(p.id,'final_approval','Implementation, tests, code review, UI/UX review and security review are complete. Final human approval is required for release.',Severity.MEDIUM)
                    state.approvals.append(approval.id); self.db.save_state(state)
                    if self.notifier:
                        try:self.notifier.approval_requested(approval)
                        except Exception:pass
                    if self.notifier:
                        try:self.notifier.ready_summary(p,self.db.list_tasks(p.id))
                        except Exception:pass
                    return state
                if latest.status==ApprovalStatus.APPROVED:
                    self.set_state(p,WorkflowState.COMPLETED)
                    return self.db.get_state(pid) or state
                if latest.status==ApprovalStatus.REJECTED:
                    return state
                return state
            if s in (WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.COMPLETED,WorkflowState.CANCELLED,WorkflowState.PAUSED): return state
        self.set_state(p,WorkflowState.BLOCKED); state.error_history.append('MAX_WORKFLOW_ITERATIONS reached'); self.db.save_state(state); return state

    def record(self,state,r):
        self.db.agent_result(state.project_id,r); state.agent_results.append(r.agent_name)
        if self.notifier:
            try: self.notifier.agent_result(self.db.get_project(state.project_id), r)
            except Exception: pass
        for path in r.files_created:
            self.db.event(WorkflowEvent(project_id=state.project_id,event_type='FILE_CREATED',task_id=r.task_id,details={'path':path,'agent':r.agent_name}))
        for path in r.files_modified:
            self.db.event(WorkflowEvent(project_id=state.project_id,event_type='FILE_MODIFIED',task_id=r.task_id,details={'path':path,'agent':r.agent_name}))
        for path in r.files_deleted:
            self.db.event(WorkflowEvent(project_id=state.project_id,event_type='FILE_DELETED',task_id=r.task_id,details={'path':path,'agent':r.agent_name}))
        if r.agent_name=='Test / QA Agent' and isinstance(r.detailed_output,dict):
            for row in r.detailed_output.get('results',[]):
                try:
                    kind,cmd,exit_code,stdout,stderr,duration=row; tr=TestResult(project_id=state.project_id,kind=kind,command=cmd,exit_code=exit_code,stdout=stdout,stderr=stderr,duration_seconds=duration,passed=exit_code==0); self.db.test_result(tr); state.test_results.append(tr.id)
                except Exception: pass
        state.timestamps['last_agent']=r.timestamp.isoformat(); self.db.save_state(state)
