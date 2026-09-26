from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import time
import os
import re
from factory.models import *
from factory.state import transition
from factory.database import Database
from factory.agents import RequirementsAgent, ManagerAgent, PlannerAgent, AnalyzerAgent, ArchitectAgent, DeveloperAgent, TesterAgent, ReviewerAgent, SecurityAgent, ReleaseAgent, UIUXAgent, UIUXReviewerAgent, AuditorAgent
from factory.approvals import ApprovalService
from factory.adapters.registry import detect, by_name
from factory.project_detection import detect_project_type
from factory.tools.shell import run as run_command
from factory.tools.git import init_repo
from factory.providers.registry import build_provider
from factory.providers.mock import MockProvider
from factory.providers.router import ModelRouter
from factory.gates import verify
from factory.company_os import get_contract, select_team
from factory.traceability import write_report
from factory.project_memory import update_project_memory
from factory.handoffs import create_handoff
from factory.github import GitHubProjectPublisher
from factory.gitflow import GitFlow
from factory.budget import BudgetManager
from factory.artifacts import record_artifacts
from factory.employee_os import role_for_task, sync_task_file

@dataclass
class Context:
    project: Project
    workspace: str
    timeout: int

class Orchestrator:
    def __init__(self, db, settings, notifier=None):
        self.db, self.settings, self.notifier = db, settings, notifier
        self.github = GitHubProjectPublisher(settings)
        self.gitflow = GitFlow(settings)
        self.job_queue = None
        self.budget = BudgetManager(db, settings)
        provider = build_provider(settings)
        self.model_router = ModelRouter(settings, notifier, db=db)
        self.agents = {
            'requirements': RequirementsAgent(self.model_router.for_role('requirements')), 'manager': ManagerAgent(self.model_router.for_role('manager')), 'planner': PlannerAgent(self.model_router.for_role('planner')), 'analyzer': AnalyzerAgent(self.model_router.for_role('analyzer')), 'architect': ArchitectAgent(self.model_router.for_role('architect')),
            'developer': DeveloperAgent(self.model_router.for_role('developer')), 'tester': TesterAgent(),
            'reviewer': ReviewerAgent(self.model_router.for_role('reviewer')), 'uiux_reviewer': UIUXReviewerAgent(self.model_router.for_role('uiux_reviewer')), 'security': SecurityAgent(), 'release': ReleaseAgent(), 'uiux': UIUXAgent(self.model_router.for_role('uiux')), 'auditor': AuditorAgent(self.model_router.for_role('auditor'))
        }

    def _agent_budget_allowed(self, project_id, role):
        return self.budget.check_role_or_event(project_id, role)

    def run_agent(self, role, ctx):
        self.model_router.set_project_context(ctx.project.id)
        if not self._agent_budget_allowed(ctx.project.id, role):
            return AgentResult(success=False, agent_name=role, errors=[f"Agent budget exhausted for role: {role}"], summary="Agent role budget exhausted.")
        agent = self.agents[role]
        # Feed durable factory-learning lessons into every AI role. This lets the
        # supervisor improve prompts/behavior over time without changing project truth.
        try:
            learning_path = Path(self.settings.workspaces_root) / '.factory' / 'FACTORY_LEARNING.md'
            learning = learning_path.read_text(encoding='utf-8', errors='ignore')[-12000:] if learning_path.exists() else ''
            base_instructions = getattr(agent, 'instructions', '')
            if learning and not getattr(agent, '_factory_learning_loaded', False):
                agent.instructions = (
                    base_instructions
                    + '\n\nFACTORY LEARNING — durable operational lessons from previous audits. '
                    + 'Use these as process guidance, never as project requirements:\n'
                    + learning
                )
                agent._factory_learning_loaded = True
        except Exception:
            pass
        result = agent.run(ctx)
        # Requirements can confirm the platform/domain after discovery. Persist it
        # before the workflow advances so later stages never see stale UNKNOWN.
        if role == 'requirements' and result.success:
            self.db.save_project(ctx.project)
            st = self.db.get_state(ctx.project.id)
            if st:
                st.project_type = ctx.project.project_type
                self.db.save_state(st)
        return result

    def provider_info(self):
        configured = bool(self.model_router.specs_for('planner'))
        return {'provider': self.settings.provider, 'model': self.settings.model, 'configured': configured, 'mock': self.settings.mode in ('mock','dry-run')}

    def authorized(self, update):
        uid = update.effective_user.id if update.effective_user else None
        cid = update.effective_chat.id if update.effective_chat else None
        users, chats = self.settings.telegram_allowed_user_ids, self.settings.telegram_allowed_chat_ids
        # Explicit opt-in public mode for deployments without an allowlist.
        if not users and not chats:
            return os.getenv('TELEGRAM_ALLOW_ALL', 'false').strip().lower() in {'1','true','yes','on'}
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
        github_details = None
        if self.github.enabled:
            try:
                github_details = self.github.publish_new_project(w, name, pid, description)
                self.db.event(WorkflowEvent(project_id=p.id, event_type='GITHUB_REPOSITORY_CREATED', details=github_details or {}))
            except Exception as exc:
                # GitHub publishing must never destroy local project creation.
                self.db.event(WorkflowEvent(project_id=p.id, event_type='GITHUB_PUBLISH_FAILED', details={'error': str(exc)[:2000]}))
        self.db.event(WorkflowEvent(project_id=p.id, event_type='PROJECT_CREATED', state=p.current_state.value, details={'project_type': detected_type.value, 'git_branch': branch_name, 'branch_created': branch_result.exit_code == 0, 'github_repo': (github_details or {}).get('full_name')}))
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
        existing = self.db.list_tasks(p.id)
        if existing:
            # Keep the filesystem employee inbox synchronized with durable DB truth.
            for task in existing:
                try:
                    task.assigned_agent = role_for_task(task.title, task.assigned_agent)
                    self.db.save_task(task)
                    sync_task_file(p.workspace_path, task)
                except Exception:
                    pass
            return
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
            t=Task(project_id=p.id,title=title,description=title,priority=Priority.HIGH,assigned_agent=role_for_task(title, 'developer'),dependencies=dep_ids,acceptance_criteria=meta.get('acceptance_criteria',[]),files_expected=meta.get('files_expected',[]),tests_required=meta.get('tests_required',[]))
            self.db.save_task(t)
            sync_task_file(p.workspace_path, t); self.db.event(WorkflowEvent(project_id=p.id,event_type='TASK_CREATED',task_id=t.id,details={'dependencies':dep_ids,'acceptance_criteria':t.acceptance_criteria,'files_expected':t.files_expected,'tests_required':t.tests_required})); created.append(t)

    def next_task(self,p):
        tasks=self.db.list_tasks(p.id); done={t.id for t in tasks if t.status==TaskStatus.DONE}
        for t in tasks:
            if t.status in (TaskStatus.PENDING,TaskStatus.READY) and all(d in done for d in t.dependencies): return t
        return None

    def _add_fix_task(self,p,title,description,priority=Priority.HIGH):
        t=Task(project_id=p.id,title=title,description=description,priority=priority,assigned_agent=role_for_task(title, 'developer'))
        self.db.save_task(t)
        sync_task_file(p.workspace_path, t); self.db.event(WorkflowEvent(project_id=p.id,event_type='FIX_TASK_CREATED',task_id=t.id)); return t

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
            elif p.project_type == ProjectType.UNKNOWN:
                # Backfill legacy projects created before intake detection was persisted.
                # Never let an old UNKNOWN value survive a retry when the client description
                # clearly identifies the stack (for example, Flutter).
                try:
                    detected = detect_project_type(p.description, p.workspace_path)
                    if detected != ProjectType.UNKNOWN:
                        p.project_type = detected
                        p.updated_at = datetime.now(timezone.utc)
                        self.db.save_project(p)
                        state = self.db.get_state(pid)
                        if state:
                            state.project_type = detected
                            self.db.save_state(state)
                except Exception:
                    pass
                self.set_state(p, WorkflowState.IDEA)
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


    def _pause_for_quota(self, p, r, state):
        marker = next((x for x in (r.errors or []) if 'AI_QUOTA_EXHAUSTED' in str(x)), None)
        if not marker:
            return False
        match = re.search(r'resume_at=([^ ]+)', str(marker))
        resume_at = match.group(1) if match else datetime.now(timezone.utc).isoformat()
        state.paused_from = p.current_state
        state.quota_resume_at = resume_at
        state.error_history.append(str(marker))
        self.db.save_state(state)
        self.set_state(p, WorkflowState.WAITING_FOR_QUOTA)
        if self.notifier:
            try:
                role = getattr(r, 'agent_name', 'AI Agent')
                models = str(marker).split('models=',1)[-1]
                self.notifier._send('⏸️ <b>'+role+'</b> كل الموديلات المتاحة استنفدت الـQuota.\n🤖 Tried: <code>'+models+'</code>\n🕘 الاستئناف التلقائي: <code>'+resume_at+'</code>\n💾 المشروع محفوظ وسيكمل من نفس المرحلة.')
            except Exception:
                pass
        return True

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
        if not self.budget.check_or_event(pid):
            state.error_history.append('Project AI agent-run budget exhausted.')
            self.db.save_state(state)
            self.set_state(p, WorkflowState.WAITING_FOR_QUOTA)
            return state
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
            p=self.db.get_project(pid); state=self.db.get_state(pid) or state
            if p.current_state == WorkflowState.WAITING_FOR_QUOTA:
                resume_raw = state.quota_resume_at
                try:
                    due = bool(resume_raw) and datetime.fromisoformat(resume_raw) <= datetime.now(datetime.fromisoformat(resume_raw).tzinfo or timezone.utc)
                except Exception:
                    due = True
                if not due:
                    return state
                resume_state = state.paused_from or WorkflowState.IDEA
                state.quota_resume_at = None; state.paused_from = None; self.db.save_state(state)
                self.set_state(p, resume_state)
                p=self.db.get_project(pid)
                if self.notifier:
                    try:self.notifier._send('🟢 <b>#FACTORY</b> Quota window reached — استئناف المشروع من <code>'+resume_state.value+'</code>.')
                    except Exception:pass
            state.iteration_count+=1; self.db.save_state(state); s=p.current_state
            if s==WorkflowState.IDEA:
                self.set_state(p,WorkflowState.REQUIREMENTS_GATHERING); continue
            if s==WorkflowState.REQUIREMENTS_GATHERING:
                self.notifier.agent_started(p, 'Requirements Specialist', 'بيجمع المتطلبات معاك بشكل حواري وبيسأل حسب السياق') if self.notifier else None
                r=self.run_agent('requirements', ctx); self.record(state,r)
                if self._pause_for_quota(p,r,state): continue
                if r.success and r.next_action=='ask_client':
                    if self.notifier:
                        try:self.notifier._send(f'💬 <b>#REQUIREMENTS</b> {r.summary}')
                        except Exception:pass
                    return state
                if r.success:
                    approval=ApprovalService(self.db).request(p.id,'requirements_approval','PRD, requirements and acceptance criteria are ready. Review and approve them before the Manager starts planning.',Severity.MEDIUM,files=['docs/PRD.md','docs/REQUIREMENTS.md','docs/ACCEPTANCE_CRITERIA.md'])
                    state.approvals.append(approval.id); state.stage_evidence[WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL.value]=list(r.completion_evidence); self.db.save_state(state)
                    if self.notifier:
                        try:
                            self.notifier._send(f'📋 <b>#REQUIREMENTS</b> {r.summary}\nراجع الملفات، ولو تمام اكتب <b>تمام</b>.')
                            self.notifier.send_requirements_package(p)
                        except Exception:pass
                    self.set_state(p,WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL)
                else:
                    state.error_history.extend(r.errors[-3:]); self.db.save_state(state); self.set_state(p,WorkflowState.BLOCKED)
                continue
            if s==WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL:
                approvals=[a for a in self.db.list_approvals(p.id) if a.requested_action=='requirements_approval']
                latest=approvals[-1] if approvals else None
                if latest and latest.status==ApprovalStatus.APPROVED:
                    self.set_state(p,WorkflowState.DESIGNING)
                elif latest and latest.status==ApprovalStatus.REJECTED:
                    self.set_state(p,WorkflowState.REQUIREMENTS_GATHERING)
                else:
                    return state
                continue
            if s==WorkflowState.DESIGNING:
                self.notifier.agent_started(p, 'UI/UX Designer Agent', 'بدأ تحديد الشاشات والـ user flow والـ design system') if self.notifier else None
                r=self.run_agent('uiux', ctx); self.record(state,r)
                if self._pause_for_quota(p,r,state): continue
                if r.success:
                    gate_errors=verify(WorkflowState.WAITING_FOR_DESIGN_APPROVAL,p.workspace_path,r)
                    if gate_errors:
                        r.success=False; r.errors.extend(gate_errors); state.gate_failures.extend(gate_errors); state.error_history.extend(gate_errors); self.db.save_state(state)
                    else:
                        approval=ApprovalService(self.db).request(p.id,'design_approval','UI/UX design is ready. Approve the design before implementation.',Severity.MEDIUM,files=['docs/DESIGN.md','docs/design/preview.html'])
                        state.approvals.append(approval.id); state.stage_evidence[WorkflowState.WAITING_FOR_DESIGN_APPROVAL.value]=list(r.files_created); self.db.save_state(state)
                        if self.notifier:
                            try:self.notifier.design_ready(p,approval,r)
                            except Exception:pass
                        self.set_state(p,WorkflowState.WAITING_FOR_DESIGN_APPROVAL)
                else:
                    # Provider outages/throttling are transient. The HTTP provider
                    # already retries inside one request; this bounded workflow-level
                    # retry survives short-lived incidents without blocking the project.
                    errors = r.errors[-3:] or ['UI/UX design failed.']
                    state.error_history.extend(errors)
                    retry_key = 'uiux_provider'
                    retry_count = state.retry_counts.get(retry_key, 0)
                    text_errors = ' '.join(errors).upper()
                    transient = any(x in text_errors for x in (
                        'AI PROVIDER HTTP 408', 'AI PROVIDER HTTP 409',
                        'AI PROVIDER HTTP 429', 'AI PROVIDER HTTP 500',
                        'AI PROVIDER HTTP 502', 'AI PROVIDER HTTP 503',
                        'AI PROVIDER HTTP 504', 'CONNECTION ERROR', 'TIMEOUT'
                    ))
                    permanent = any(x in text_errors for x in (
                        'AI PROVIDER HTTP 400', 'AI PROVIDER HTTP 401',
                        'AI PROVIDER HTTP 403', 'AI PROVIDER HTTP 404',
                        'NOT_FOUND', 'NO LONGER AVAILABLE'
                    ))
                    if transient and not permanent and retry_count < 3:
                        retry_count += 1
                        state.retry_counts[retry_key] = retry_count
                        self.db.save_state(state)
                        delay = {1: 5, 2: 15, 3: 30}[retry_count]
                        if self.notifier:
                            try: self.notifier._send(
                                f'🔁 <b>#UIUX</b> مزود الـAI مشغول أو غير متاح مؤقتًا. '
                                f'هحاول تاني ({retry_count}/3) بعد {delay} ثانية.'
                            )
                            except Exception: pass
                        time.sleep(delay)
                        self.set_state(p,WorkflowState.DESIGNING)
                    else:
                        if self.notifier:
                            try: self.notifier._send(
                                '⛔ <b>#UIUX</b> التصميم متوقف بعد استنفاد المحاولات المؤقتة.'
                                if transient else
                                '⛔ <b>#UIUX</b> التصميم متوقف بسبب خطأ دائم في إعداد مزود الـAI.'
                            )
                            except Exception: pass
                        self.set_state(p,WorkflowState.BLOCKED)
                continue
            if s==WorkflowState.WAITING_FOR_DESIGN_APPROVAL:
                approvals=[a for a in self.db.list_approvals(p.id) if a.requested_action=='design_approval']; latest=approvals[-1] if approvals else None
                if latest and latest.status==ApprovalStatus.APPROVED:self.set_state(p,WorkflowState.DESIGN_APPROVED)
                elif latest and latest.status==ApprovalStatus.REJECTED:self.set_state(p,WorkflowState.DESIGNING)
                else:return state
                continue
            if s==WorkflowState.DESIGN_APPROVED:
                if p.project_type == ProjectType.FLUTTER and not effective_mock:
                    if not self._prepare_flutter_project(p, state):
                        self.set_state(p, WorkflowState.BLOCKED)
                        continue
                self.set_state(p,WorkflowState.PLANNING); continue
            if s==WorkflowState.PLANNING:
                self.notifier.agent_started(p, 'Planner Agent', 'بدأ تحليل المتطلبات وتحويلها إلى خطة تنفيذ') if self.notifier else None
                r=self.run_agent('planner', ctx); self.record(state,r)
                if self._pause_for_quota(p,r,state): continue
                self.set_state(p,WorkflowState.DOCUMENTATION if r.success else WorkflowState.BLOCKED); continue
            if s==WorkflowState.DOCUMENTATION:
                gate_errors=verify(WorkflowState.DOCUMENTATION,p.workspace_path)
                if gate_errors:
                    state.gate_failures.extend(gate_errors); state.error_history.extend(gate_errors); self.db.save_state(state); self.set_state(p,WorkflowState.BLOCKED)
                else: self.set_state(p,WorkflowState.ANALYSIS)
                continue
            if s==WorkflowState.ANALYSIS:
                self.notifier.agent_started(p, 'Analyzer Agent', 'بدأ تحليل الـ architecture والمتطلبات التقنية') if self.notifier else None
                r=self.run_agent('analyzer', ctx); self.record(state,r)
                if self._pause_for_quota(p,r,state): continue
                if r.success:
                    state.retry_counts.pop('analyzer_provider', None)
                    state.retry_counts.pop('analysis_correction', None)
                    self.db.save_state(state)
                    self.set_state(p,WorkflowState.ARCHITECTURE)
                else:
                    cycle=state.retry_counts.get('analysis_correction',0)
                    findings=(r.detailed_output or {}) if isinstance(r.detailed_output,dict) else {}
                    blocking_items=[]
                    for key in ('contradictions','missing_requirements','missing_acceptance_criteria','dependency_issues','technical_risks','security_risks','domain_misalignment'):
                        vals=findings.get(key,[]) or []
                        blocking_items.extend(vals if isinstance(vals,list) else [vals])
                    if blocking_items and cycle < 3:
                        state.retry_counts['analysis_correction']=cycle+1
                        state.error_history.extend([f'Analyzer correction cycle {cycle+1}: {x}' for x in blocking_items[:10]])
                        self.db.save_state(state)
                        if self.notifier:
                            try:self.notifier._send(f'🔧 <b>#ANALYZER</b> لقى {len(blocking_items)} ملاحظات مؤثرة. بدء corrective planning pass ({cycle+1}/3) بدل إيقاف المشروع.')
                            except Exception:pass
                        pr=self.run_agent('planner', ctx); self.record(state,pr)
                        if self._pause_for_quota(p,pr,state): continue
                        if pr.success:
                            continue
                        errors = pr.errors[-3:] or ['Corrective planning pass failed.']
                        self.set_state(p,WorkflowState.BLOCKED)
                    else:
                        errors = r.errors[-3:] or ['Analysis failed.']
                    state.error_history.extend(errors)
                    retry_key = 'analyzer_provider'
                    retry_count = state.retry_counts.get(retry_key, 0)
                    text_errors = ' '.join(errors).upper()
                    transient = any(x in text_errors for x in (
                        'AI PROVIDER HTTP 408', 'AI PROVIDER HTTP 409',
                        'AI PROVIDER HTTP 429', 'AI PROVIDER HTTP 500',
                        'AI PROVIDER HTTP 502', 'AI PROVIDER HTTP 503',
                        'AI PROVIDER HTTP 504', 'AI PROVIDER CONNECTION ERROR',
                        'TIMEOUT', 'TEMPORARILY UNAVAILABLE', 'HIGH DEMAND',
                    ))
                    permanent = any(x in text_errors for x in (
                        'AI PROVIDER HTTP 400', 'AI PROVIDER HTTP 401',
                        'AI PROVIDER HTTP 403', 'AI PROVIDER HTTP 404',
                        'NOT_FOUND', 'NO LONGER AVAILABLE', 'API KEY IS REQUIRED',
                        'AI MODEL IS REQUIRED', 'AI BASE URL IS REQUIRED',
                    ))
                    if transient and not permanent and retry_count < 3:
                        delays = (5, 15, 30)
                        delay = delays[retry_count]
                        state.retry_counts[retry_key] = retry_count + 1
                        self.db.save_state(state)
                        if self.notifier:
                            try:
                                self.notifier._send(
                                    f'🔁 <b>#FACTORY</b> مزود الـAI مشغول أو غير متاح مؤقتًا. '
                                    f'هحاول تحليل المتطلبات تاني ({retry_count + 1}/3) بعد {delay} ثانية.'
                                )
                            except Exception:
                                pass
                        time.sleep(delay)
                        continue
                    self.set_state(p,WorkflowState.BLOCKED)
                continue
            if s==WorkflowState.ARCHITECTURE:
                self.notifier.agent_started(p, 'Architect Agent', 'بدأ تحويل المتطلبات والتصميم المعتمد إلى معمارية قابلة للتنفيذ') if self.notifier else None
                r=self.run_agent('architect', ctx); self.record(state,r)
                if self._pause_for_quota(p,r,state): continue
                gate_errors=verify(WorkflowState.ARCHITECTURE,p.workspace_path,r)
                if r.success and not gate_errors:
                    state.stage_evidence[WorkflowState.ARCHITECTURE.value]=list(r.completion_evidence or r.files_created); self.db.save_state(state); self.set_state(p,WorkflowState.TASK_CREATION)
                else:
                    errs=gate_errors or r.errors or ['Architecture gate failed.']; state.gate_failures.extend(errs); state.error_history.extend(errs); self.db.save_state(state); self.set_state(p,WorkflowState.BLOCKED)
                continue
            if s==WorkflowState.TASK_CREATION:
                self.ensure_tasks(p)
                trace=write_report(p.workspace_path)
                if not trace.complete:
                    msg=f'Traceability incomplete: {len(trace.unmapped)} unmapped requirements.'
                    state.error_history.append(msg)
                    cycle=state.retry_counts.get('traceability_correction',0)
                    if cycle < 3:
                        state.retry_counts['traceability_correction']=cycle+1
                        self.db.save_state(state)
                        if self.notifier:
                            try:self.notifier._send('🔗 <b>#TRACEABILITY</b> في requirements لسه مش مربوطة بمهام. corrective planning pass قبل التنفيذ.')
                            except Exception:pass
                        pr=self.run_agent('planner', ctx); self.record(state,pr)
                        if self._pause_for_quota(p,pr,state): continue
                        if pr.success: continue
                    self.db.save_state(state)
                    self.set_state(p,WorkflowState.BLOCKED); continue
                self.notifier.agent_started(p, 'Manager Agent', 'بيتحقق إن كل requirement متغطية وبيوزع المهام والـskills تلقائيًا') if self.notifier else None
                mr=self.run_agent('manager', ctx); self.record(state,mr)
                if self._pause_for_quota(p,mr,state): continue
                if mr.success:
                    assignments=(mr.detailed_output or {}).get('assignments',[]) if isinstance(mr.detailed_output,dict) else []
                    tasks=self.db.list_tasks(p.id)
                    req_path=Path(p.workspace_path)/'docs'/'REQUIREMENTS.md'
                    req_text=req_path.read_text(encoding='utf-8',errors='ignore') if req_path.exists() else p.description
                    team=select_team(req_text,p.project_type.value)
                    contract_path=Path(p.workspace_path)/'docs'/'TEAM.md'
                    contract_path.write_text('# Dynamic Project Team\n\n'+'\n'.join(
                        f'- #{role.upper()} — {get_contract(role).title}: {get_contract(role).mission}' for role in team
                    )+'\n',encoding='utf-8')
                    state.stage_evidence['TASK_CREATION']=['docs/TASKS.md','docs/TRACEABILITY.md','docs/TEAM.md','docs/MANAGER_PLAN.md']
                    self.db.save_state(state)
                    for a in assignments:
                        try:
                            n=int(a.get('task_number',0))
                            if 1 <= n <= len(tasks):
                                t=tasks[n-1]
                                t.assigned_agent=str(a.get('role') or t.assigned_agent or 'developer').lower()
                                t.skills=list(a.get('skills') or [])
                                self.db.save_task(t)
                                sync_task_file(p.workspace_path, t)
                                self.db.event(WorkflowEvent(project_id=p.id,event_type='TASK_ASSIGNED',task_id=t.id,details={'role':t.assigned_agent,'skills':t.skills}))
                        except Exception:
                            pass
                    self.set_state(p,WorkflowState.IMPLEMENTATION)
                else:
                    errs=mr.errors[-8:] or ['Manager rejected the task plan.']
                    state.error_history.extend(errs); state.gate_failures.extend(errs); self.db.save_state(state)
                    if self.notifier:
                        try:self.notifier._send('🛑 <b>#MANAGER</b> رفض خطة التنفيذ وطلب إعادة التخطيط:\n'+'\n'.join('• '+x for x in errs))
                        except Exception:pass
                    self.set_state(p,WorkflowState.PLANNING)
                continue
            if s==WorkflowState.IMPLEMENTATION:
                t=self.next_task(p)
                if not t: self.set_state(p,WorkflowState.TESTING); continue
                t.status=TaskStatus.IN_PROGRESS; t.updated_at=datetime.now(timezone.utc); t.failure_reason=self._feedback_for_task(p,t); self.db.save_task(t); sync_task_file(p.workspace_path, t)
                if effective_mock:
                    r=AgentResult(success=True,agent_name='Developer Agent',task_id=t.id,summary='Mock implementation.',next_action='test')
                else:
                    self.notifier.agent_started(p, 'Developer Agent', f'بدأ تنفيذ المهمة: {t.title}') if self.notifier else None
                    r=self.agents['developer'].run(ctx,t)
                self.record(state,r)
                gate_errors=[] if effective_mock else verify(WorkflowState.IMPLEMENTATION,p.workspace_path,r,t)
                if gate_errors:
                    r.success=False; r.errors.extend(gate_errors); state.gate_failures.extend(gate_errors); state.error_history.extend(gate_errors)
                if self._pause_for_quota(p,r,state):
                    t.status=TaskStatus.PENDING; self.db.save_task(t); continue
                if r.success:
                    t.status=TaskStatus.DONE; t.completed_at=datetime.now(timezone.utc); t.failure_reason=None
                else:
                    t.retry_count+=1; t.status=TaskStatus.PENDING if t.retry_count < self.settings.max_retries else TaskStatus.FAILED; t.failure_reason='\n'.join(r.errors)
                    state.error_history.extend(r.errors[-5:])
                self.db.save_task(t)
                try:
                    sync_task_file(p.workspace_path, t, evidence=list(r.completion_evidence or r.tests_run or []))
                except Exception:
                    pass
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
                    qa_report=Path(p.workspace_path)/'docs'/'TEST_REPORT.md'
                    qa_report.parent.mkdir(parents=True,exist_ok=True)
                    qa_report.write_text('# QA Test Report\\n\\nPASS\\n\\nMock validation evidence generated by the factory test harness.\\n',encoding='utf-8')
                    r=AgentResult(success=True,agent_name='Test / QA Agent',summary='Mock QA.',next_action='review',files_created=['docs/TEST_REPORT.md'],completion_evidence=['docs/TEST_REPORT.md'],tests_run=['mock_validation'])
                elif p.project_type == ProjectType.FLUTTER and not self._flutter_dependencies_approved(p, state):
                    self.set_state(p, WorkflowState.BLOCKED)
                    continue
                else:
                    self.notifier.agent_started(p, 'Test / QA Agent', 'بدأ تشغيل الاختبارات والتحقق من الوظائف') if self.notifier else None
                    r=self.run_agent('tester', ctx)
                self.record(state,r)
                gate_errors=[] if effective_mock else verify(WorkflowState.TESTING,p.workspace_path,r)
                if gate_errors:
                    r.success=False; r.errors.extend(gate_errors); state.gate_failures.extend(gate_errors); state.error_history.extend(gate_errors); self.db.save_state(state)
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
                if effective_mock:
                    review_report=Path(p.workspace_path)/'docs'/'CODE_REVIEW.md'
                    review_report.parent.mkdir(parents=True,exist_ok=True)
                    review_report.write_text('# Code Review Report\\n\\nMock code review passed.\\n',encoding='utf-8')
                    r=AgentResult(success=True,agent_name='Code Reviewer',summary='Mock review.',next_action='security',files_created=['docs/CODE_REVIEW.md'],completion_evidence=['docs/CODE_REVIEW.md'])
                else:
                    self.notifier.agent_started(p, 'Code Reviewer', 'بدأ مراجعة الكود والجودة والمخاطر') if self.notifier else None
                    r=self.run_agent('reviewer', ctx)
                self.record(state,r)
                gate_errors=verify(WorkflowState.REVIEWING,p.workspace_path,r)
                if gate_errors:
                    r.success=False; r.errors.extend(gate_errors); state.gate_failures.extend(gate_errors); state.error_history.extend(gate_errors); self.db.save_state(state)
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
                    ux_report=Path(p.workspace_path)/'docs'/'UX_REVIEW.md'
                    ux_report.parent.mkdir(parents=True,exist_ok=True)
                    ux_report.write_text('# UI/UX Review Report\\n\\nMock UI/UX review passed.\\n',encoding='utf-8')
                    r=AgentResult(success=True,agent_name='UI/UX Reviewer',summary='Mock UI/UX review passed.',next_action='security',files_created=['docs/UX_REVIEW.md'],completion_evidence=['docs/UX_REVIEW.md'])
                else:
                    self.notifier.agent_started(p, 'UI/UX Reviewer', 'بدأ مقارنة التنفيذ بالتصميم المعتمد') if self.notifier else None
                    r=self.run_agent('uiux_reviewer', ctx)
                self.record(state,r)
                gate_errors=verify(WorkflowState.UX_REVIEW,p.workspace_path,r)
                if gate_errors:
                    r.success=False; r.errors.extend(gate_errors); state.gate_failures.extend(gate_errors); state.error_history.extend(gate_errors); self.db.save_state(state)
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
                if effective_mock:
                    security_report=Path(p.workspace_path)/'docs'/'SECURITY_REVIEW.md'
                    security_report.parent.mkdir(parents=True,exist_ok=True)
                    security_report.write_text('# Security Review\\n\\nPASS\\n\\nMock security review passed.\\n',encoding='utf-8')
                    r=AgentResult(success=True,agent_name='Security Reviewer',summary='Mock security review.',next_action='ready',files_created=['docs/SECURITY_REVIEW.md'],completion_evidence=['docs/SECURITY_REVIEW.md'])
                else:
                    self.notifier.agent_started(p, 'Security Reviewer', 'بدأ فحص الأمان والثغرات') if self.notifier else None
                    r=self.run_agent('security', ctx)
                self.record(state,r)
                gate_errors=verify(WorkflowState.SECURITY_REVIEW,p.workspace_path,r)
                if gate_errors:
                    r.success=False; r.errors.extend(gate_errors); state.gate_failures.extend(gate_errors); state.error_history.extend(gate_errors); self.db.save_state(state)
                if not r.success:
                    approval=ApprovalService(self.db).request(p.id,'Resolve security finding before continuing','Security reviewer reported a blocking security condition.',Severity.CRITICAL,files=r.errors)
                    state.approvals.append(approval.id); self.db.save_state(state)
                    if self.notifier:
                        try:self.notifier.approval_requested(approval)
                        except Exception:pass
                    self.set_state(p,WorkflowState.BLOCKED)
                    continue
                # Independent audit is deliberately outside the security/reviewer agents.
                ar=self.run_agent('auditor', ctx) if not effective_mock else AgentResult(success=True,agent_name='AI Auditor',summary='Mock audit passed.',next_action='ready',completion_evidence=[])
                self.record(state,ar)
                if ar.success:
                    self.set_state(p,WorkflowState.READY_FOR_HUMAN)
                else:
                    errs=ar.errors[-8:] or ['Independent AI Auditor found blocking issues.']
                    state.error_history.extend(errs); state.gate_failures.extend(errs); self.db.save_state(state)
                    t=self._add_fix_task(p,'Fix independent audit findings','\n'.join(errs))
                    self.set_state(p,WorkflowState.BLOCKED if t.retry_count>=self.settings.max_retries else WorkflowState.FIXING)
                continue
            if s==WorkflowState.FIXING: self.set_state(p,WorkflowState.IMPLEMENTATION if self.next_task(p) else WorkflowState.TESTING); continue
            if s==WorkflowState.READY_FOR_HUMAN:
                final_gate=verify(WorkflowState.READY_FOR_HUMAN,p.workspace_path)
                if final_gate:
                    state.gate_failures.extend(final_gate); state.error_history.extend(final_gate); self.db.save_state(state); self.set_state(p,WorkflowState.BLOCKED); continue
                approvals=[a for a in self.db.list_approvals(p.id) if a.requested_action=='final_approval']
                latest=approvals[-1] if approvals else None
                if latest is None:
                    if self.github.enabled:
                        try:
                            repo=self.github.repo_info(p.workspace_path)
                            if repo:
                                pushed=self.gitflow.commit_and_push(p.workspace_path, p.git_branch, "chore(factory): prepare human review")
                                pr=self.gitflow.create_or_get_pull_request(repo["full_name"], p.git_branch, "main", f"Factory review: {p.name}", "Automated draft PR prepared after Final Gate passed. Human approval is still required.")
                                self.db.event(WorkflowEvent(project_id=p.id,event_type='GITHUB_PR_READY',details={'repository':repo['full_name'],'branch':p.git_branch,'pr':pr,'push':pushed}))
                        except Exception as exc:
                            self.db.event(WorkflowEvent(project_id=p.id,event_type='GITHUB_PR_FAILED',details={'error':str(exc)[:2000]}))
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
                    # Final approval unlocks deterministic release packaging.
                    r=self.run_agent('release', ctx)
                    self.record(state,r)
                    if r.success:
                        self.set_state(p,WorkflowState.COMPLETED)
                        if self.notifier:
                            try:self.notifier.release_ready(p,r)
                            except Exception:pass
                        return self.db.get_state(pid) or state
                    state.error_history.extend(r.errors[-5:])
                    self.db.save_state(state)
                    self.set_state(p,WorkflowState.BLOCKED)
                    return self.db.get_state(pid) or state
                if latest.status==ApprovalStatus.REJECTED:
                    feedback = latest.response or 'Final approval was rejected. Human changes are required before release.'
                    t = self._add_fix_task(p, 'Final human change request', feedback)
                    self.set_state(p, WorkflowState.CHANGES_REQUESTED)
                    self.set_state(p, WorkflowState.TASK_CREATION)
                    return self.db.get_state(pid) or state
                return state
            if s in (WorkflowState.BLOCKED,WorkflowState.FAILED,WorkflowState.COMPLETED,WorkflowState.CANCELLED,WorkflowState.PAUSED): return state
        self.set_state(p,WorkflowState.BLOCKED); state.error_history.append('MAX_WORKFLOW_ITERATIONS reached'); self.db.save_state(state); return state

    def record(self,state,r):
        role_map={'Requirements Specialist':'requirements','Manager Agent':'manager','Planner Agent':'planner','Analyzer Agent':'analyzer','Architect Agent':'architect','Developer Agent':'developer','Code Reviewer':'reviewer','UI/UX Reviewer':'uiux_reviewer','UI/UX Designer Agent':'uiux'}
        role=role_map.get(r.agent_name)
        router=getattr(getattr(self,'agents',{}).get(role),'provider',None) if role else None
        if router and getattr(router,'last_model',None):
            data=r.detailed_output if isinstance(r.detailed_output,dict) else {}
            data=dict(data); data['model_used']=router.last_model; data['models_attempted']=list(router.last_attempts)
            r.detailed_output=data
        self.db.agent_result(state.project_id,r); state.agent_results.append(r.agent_name)
        if r.completion_evidence:
            state.generated_artifacts.extend(x for x in r.completion_evidence if x not in state.generated_artifacts)
            state.stage_evidence[r.agent_name]=list(r.completion_evidence)
        if self.notifier:
            try: self.notifier.agent_result(self.db.get_project(state.project_id), r)
            except Exception: pass
        try:
            summary = r.summary or r.agent_name
            update_project_memory(
                state.workspace_path, state.project_id, state.current_state.value, summary,
                [f"agent:{r.agent_name}", f"next:{r.next_action or 'none'}"]
            )
            if r.handoff and isinstance(r.handoff, dict):
                h=r.handoff
                create_handoff(
                    state.workspace_path, state.project_id,
                    str(h.get("from_role") or r.agent_name),
                    str(h.get("to_role") or r.next_action or "manager"),
                    str(h.get("purpose") or summary),
                    list(h.get("inputs") or []),
                    list(h.get("outputs") or r.completion_evidence or []),
                    list(h.get("acceptance_checks") or [])
                )
        except Exception:
            pass
        for path in r.files_created:
            self.db.event(WorkflowEvent(project_id=state.project_id,event_type='FILE_CREATED',task_id=r.task_id,details={'path':path,'agent':r.agent_name}))
        for path in r.files_modified:
            self.db.event(WorkflowEvent(project_id=state.project_id,event_type='FILE_MODIFIED',task_id=r.task_id,details={'path':path,'agent':r.agent_name}))
        for path in r.files_deleted:
            self.db.event(WorkflowEvent(project_id=state.project_id,event_type='FILE_DELETED',task_id=r.task_id,details={'path':path,'agent':r.agent_name}))
        try:
            record_artifacts(state.workspace_path, state.project_id, self.db, list(dict.fromkeys(r.files_created + r.files_modified + r.completion_evidence)))
        except Exception as exc:
            self.db.event(WorkflowEvent(project_id=state.project_id,event_type='ARTIFACT_MANIFEST_FAILED',task_id=r.task_id,details={'error':str(exc)[:1000]}))
        if self.github.enabled and self.github.auto_sync:
            try:
                sync = self.github.sync(state.workspace_path, f"chore(factory): sync after {r.agent_name}")
                if sync:
                    self.db.event(WorkflowEvent(project_id=state.project_id,event_type='GITHUB_SYNCED',task_id=r.task_id,details={'agent':r.agent_name,'sync':sync}))
            except Exception as exc:
                self.db.event(WorkflowEvent(project_id=state.project_id,event_type='GITHUB_SYNC_FAILED',task_id=r.task_id,details={'agent':r.agent_name,'error':str(exc)[:2000]}))
        if r.agent_name=='Test / QA Agent' and isinstance(r.detailed_output,dict):
            for row in r.detailed_output.get('results',[]):
                try:
                    kind,cmd,exit_code,stdout,stderr,duration=row; tr=TestResult(project_id=state.project_id,kind=kind,command=cmd,exit_code=exit_code,stdout=stdout,stderr=stderr,duration_seconds=duration,passed=exit_code==0); self.db.test_result(tr); state.test_results.append(tr.id)
                except Exception: pass
        state.timestamps['last_agent']=r.timestamp.isoformat(); self.db.save_state(state)
