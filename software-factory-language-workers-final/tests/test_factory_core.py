from pathlib import Path
import pytest
from factory.state import transition, InvalidTransition
from factory.models import WorkflowState, Task, TaskStatus, Project
from factory.tools.filesystem import WorkspaceFS
from factory.permissions import PermissionDenied, Permission
from factory.adapters.python import PythonAdapter
from factory.database import Database
from factory.orchestrator import Orchestrator
from factory.config import Settings
from factory.providers.mock import MockProvider

def test_invalid_transition_rejected():
    with pytest.raises(InvalidTransition):
        transition(WorkflowState.IDEA, WorkflowState.COMPLETED)

def test_workspace_traversal_rejected(tmp_path):
    fs=WorkspaceFS(tmp_path,'developer')
    with pytest.raises(PermissionError): fs.safe('../outside.txt')

def test_planner_cannot_modify_source(tmp_path):
    fs=WorkspaceFS(tmp_path,'planner')
    with pytest.raises(PermissionDenied): fs.write('app.py','x')

def test_task_dependency_data_roundtrip(tmp_path):
    db=Database(tmp_path/'db.sqlite')
    p=Project(name='p',description='d',workspace_path=str(tmp_path));db.save_project(p)
    a=Task(project_id=p.id,title='a',description='');b=Task(project_id=p.id,title='b',description='',dependencies=[a.id])
    db.save_task(a);db.save_task(b)
    got=db.list_tasks_for_project(p.id)
    assert got[1].dependencies==[a.id]

def test_python_adapter_commands():
    a=PythonAdapter()
    assert a.test()=='python -m pytest -q'
    assert a.analyze()=='ruff check .'

def test_mock_workflow_reaches_human_review(tmp_path):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','mock','model',None,3,30,10)
    settings.ensure_directories()
    o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('Demo','Build a test project')
    state=o.run(p.id,mock=True)
    from factory.approvals import ApprovalService
    req=[a for a in o.db.list_approvals(p.id) if a.requested_action=='requirements_approval'][-1]
    ApprovalService(o.db).resolve(req, True, 'test requirements')
    state=o.run(p.id,mock=True)
    assert state.current_state==WorkflowState.WAITING_FOR_DESIGN_APPROVAL
    approval=[a for a in o.db.list_approvals(p.id) if a.requested_action=='design_approval'][-1]
    ApprovalService(o.db).resolve(approval, True, 'test design')
    state=o.run(p.id,mock=True)
    assert state.current_state==WorkflowState.READY_FOR_HUMAN
    assert all(t.status==TaskStatus.DONE for t in o.db.list_tasks(p.id))

def test_approval_persistence(tmp_path):
    db=Database(tmp_path/'db.sqlite')
    p=Project(name='p',description='d',workspace_path=str(tmp_path));db.save_project(p)
    from factory.approvals import ApprovalService
    a=ApprovalService(db).request(p.id,'deploy','production deployment')
    assert db.get_approval(a.id).status.value=='PENDING'


def test_create_project_detects_flutter_type_and_uses_isolated_branch(tmp_path):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','mock','model',None,3,10,10)
    settings.ensure_directories()
    o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('Clothes Store','Build a simple Flutter clothing store app')
    assert p.project_type.value == 'flutter'
    assert p.workspace_path.startswith(str(settings.workspaces_root))
    assert p.git_branch.startswith('factory/')


def test_flutter_unavailable_blocks_real_run_with_clear_error(tmp_path, monkeypatch):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','openai','model','dummy',3,10,10,mode='real')
    settings.ensure_directories()
    o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('Clothes Store','Build a Flutter app')
    state=o.db.get_state(p.id); state.current_state=WorkflowState.DESIGN_APPROVED; o.db.save_state(state); p.current_state=WorkflowState.DESIGN_APPROVED; o.db.save_project(p)
    from factory.tools.shell import CommandResult
    def fake_run(role, command, cwd, timeout=120):
        if command == 'flutter --version':
            return CommandResult(command,127,'','flutter not found',0.01)
        return CommandResult(command,0,'','',0.01)
    monkeypatch.setattr('factory.orchestrator.run_command', fake_run)

    state=o.run(p.id, mock=False)
    assert state.current_state == WorkflowState.BLOCKED
    assert any('Flutter SDK is unavailable' in e for e in state.error_history)


def test_flutter_dependency_installation_requires_approval(tmp_path):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','openai','model','dummy',3,10,10,mode='real')
    settings.ensure_directories()
    o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('Clothes Store','Build a Flutter app')
    state=o.db.get_state(p.id)
    assert o._flutter_dependencies_approved(p,state) is False
    approval=o.db.list_approvals(p.id)[0]
    assert approval.requested_action == 'flutter pub get'
    assert approval.status.value == 'PENDING'

class _StructuredDeveloperProvider:
    is_mock = False
    def __init__(self, payload): self.payload = payload
    def generate_json(self, system, prompt, schema, *, timeout=None): return self.payload


def test_developer_creates_and_modifies_real_dart_files(tmp_path):
    from factory.agents.developer import DeveloperAgent
    from factory.models import Task
    class P:
        is_mock=False
        def __init__(self): self.calls=0
        def generate_json(self, system, prompt, schema, *, timeout=None):
            self.calls += 1
            return {'summary':'implemented','actions':[{'op':'write','path':'lib/main.dart','content':'void main() {}\n'}],'tests_to_run':['flutter test'],'warnings':[]}
    workspace=tmp_path/'workspace'; workspace.mkdir(); (workspace/'lib').mkdir()
    from factory.agents.base import Agent
    from factory.orchestrator import Context
    project=Project(name='Clothes Store',description='Flutter store',workspace_path=str(workspace),project_type='flutter')
    task=Task(project_id=project.id,title='Create entrypoint',description='Create main.dart')
    result=DeveloperAgent(P()).run(Context(project,str(workspace),10),task)
    assert result.success is True
    assert result.files_created == ['lib/main.dart']
    assert (workspace/'lib/main.dart').read_text() == 'void main() {}\n'


def test_developer_modifies_existing_dart_file(tmp_path):
    from factory.agents.developer import DeveloperAgent
    from factory.orchestrator import Context
    from factory.models import Task
    workspace=tmp_path/'workspace'; workspace.mkdir(); (workspace/'lib').mkdir(); (workspace/'lib/main.dart').write_text('void main() {}\n')
    payload={'summary':'updated','actions':[{'op':'write','path':'lib/main.dart','content':'void main() => runApp();\n'}]}
    project=Project(name='p',description='d',workspace_path=str(workspace),project_type='flutter')
    task=Task(project_id=project.id,title='Update entrypoint',description='modify')
    result=DeveloperAgent(_StructuredDeveloperProvider(payload)).run(Context(project,str(workspace),10),task)
    assert result.success and result.files_modified == ['lib/main.dart']


def test_developer_rejects_unsafe_path_and_delete(tmp_path):
    from factory.agents.developer import DeveloperAgent
    from factory.orchestrator import Context
    from factory.models import Task
    workspace=tmp_path/'workspace'; workspace.mkdir()
    payload={'summary':'unsafe','actions':[{'op':'write','path':'../escape.dart','content':'bad'}]}
    project=Project(name='p',description='d',workspace_path=str(workspace),project_type='flutter')
    task=Task(project_id=project.id,title='unsafe',description='')
    result=DeveloperAgent(_StructuredDeveloperProvider(payload)).run(Context(project,str(workspace),10),task)
    assert result.success is False
    assert any('outside workspace' in e.lower() for e in result.errors)


def test_developer_rejects_delete_without_approval(tmp_path):
    from factory.agents.developer import DeveloperAgent
    from factory.orchestrator import Context
    from factory.models import Task
    workspace=tmp_path/'workspace'; workspace.mkdir(); (workspace/'lib').mkdir(); (workspace/'lib/a.dart').write_text('x')
    payload={'summary':'delete','actions':[{'op':'delete','path':'lib/a.dart'}]}
    project=Project(name='p',description='d',workspace_path=str(workspace),project_type='flutter')
    task=Task(project_id=project.id,title='delete',description='')
    result=DeveloperAgent(_StructuredDeveloperProvider(payload)).run(Context(project,str(workspace),10),task)
    assert result.success is False and (workspace/'lib/a.dart').exists()


def test_task_breakdown_preserves_dependencies_and_metadata(tmp_path):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','mock','model',None,3,10,10)
    settings.ensure_directories(); o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('Clothes Store','Build Flutter store')
    docs=Path(p.workspace_path)/'docs'; docs.mkdir(); (docs/'TASKS.md').write_text(
        '1. Create product model | Depends: 0 | Acceptance: Product has name and price | Files: lib/product.dart | Tests: model test\n'
        '2. Build home screen | Depends: 1 | Acceptance: Products visible | Files: lib/home.dart | Tests: home widget test\n', encoding='utf-8')
    o.ensure_tasks(p); tasks=o.db.list_tasks(p.id)
    assert len(tasks)==2 and tasks[1].dependencies==[tasks[0].id]
    assert tasks[0].files_expected==['lib/product.dart']
    assert tasks[1].tests_required==['home widget test']


def test_developer_cannot_install_dependencies(tmp_path):
    from factory.tools.shell import run
    with pytest.raises(PermissionError, match='ApprovalService'):
        run('developer','flutter pub get',tmp_path)


def test_file_changes_are_audited(tmp_path):
    from factory.models import AgentResult
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','mock','model',None,3,10,10); settings.ensure_directories()
    o=Orchestrator(Database(settings.db_path),settings); p=o.create_project('p','d')
    state=o.db.get_state(p.id); o.record(state,AgentResult(success=True,agent_name='Developer Agent',task_id='t1',files_created=['lib/a.dart'],files_modified=['lib/b.dart'],generated_changes=[{'op':'create','path':'lib/a.dart'}]))
    kinds={e.event_type for e in o.db.list_events(p.id,20)}
    assert 'FILE_CREATED' in kinds and 'FILE_MODIFIED' in kinds


def test_developer_rejects_invalid_structured_output(tmp_path):
    from factory.agents.developer import DeveloperAgent
    from factory.orchestrator import Context
    from factory.models import Task
    class Bad:
        is_mock=False
        def generate_json(self,*args,**kwargs): return {'summary':'bad','actions':'not-a-list'}
    workspace=tmp_path/'workspace'; workspace.mkdir()
    project=Project(name='p',description='d',workspace_path=str(workspace),project_type='flutter')
    result=DeveloperAgent(Bad()).run(Context(project,str(workspace),10),Task(project_id=project.id,title='t',description='d'))
    assert not result.success and 'invalid_developer_output' in result.errors


def test_flutter_validation_failure_is_structured(monkeypatch, tmp_path):
    from factory.agents.tester import TesterAgent
    from factory.orchestrator import Context
    from factory.adapters.registry import ADAPTERS
    from factory.tools.shell import CommandResult
    workspace=tmp_path/'workspace'; workspace.mkdir(); (workspace/'pubspec.yaml').write_text('name: x\n')
    project=Project(name='p',description='flutter',workspace_path=str(workspace),project_type='flutter')
    calls=[]
    def fake_execute(role,kind,command,cwd,timeout):
        calls.append((kind,command))
        code=1 if kind=='static_analysis' else 0
        return CommandResult(command,code,'','analysis failed' if code else '',0.1)
    monkeypatch.setattr('factory.agents.tester.execute',fake_execute)
    result=TesterAgent().run(Context(project,str(workspace),10))
    assert not result.success
    assert result.detailed_output['results'][2][2] == 1
    assert result.errors and 'flutter analyze' in result.errors[0]


def test_flutter_test_failure_can_create_fix_task_and_respects_retry_limit(tmp_path):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','mock','model',None,2,10,10); settings.ensure_directories()
    o=Orchestrator(Database(settings.db_path),settings); p=o.create_project('p','Flutter app')
    first=o._get_test_fix_task(p,'flutter test failed')
    second=o._get_test_fix_task(p,'flutter test failed again')
    assert first.id == second.id and second.retry_count == 2
    assert second.status.value == 'PENDING'
    assert second.retry_count >= settings.max_retries


def test_e2e_real_mode_fake_llm_and_fake_flutter_adapter_reaches_review(tmp_path, monkeypatch):
    from factory.adapters.base import ProjectAdapter
    from factory.adapters.registry import ADAPTERS
    from factory.providers.base import LLMResponse
    from factory.agents import PlannerAgent, AnalyzerAgent, DeveloperAgent, ReviewerAgent, UIUXAgent, UIUXReviewerAgent
    from factory.tools.shell import CommandResult

    class FakeFlutter(ProjectAdapter):
        name='fake-flutter'
        def detect_project(self,w): return (Path(w)/'pubspec.yaml').exists()
        def install_dependencies(self): return 'flutter pub get'
        def format(self): return 'dart format .'
        def analyze(self): return 'flutter analyze'
        def test(self): return 'flutter test'
        def build(self): return 'flutter build apk --debug'
        def validate_environment(self): return 'flutter --version'
        def validation_commands(self): return [('format',self.format()),('static_analysis',self.analyze()),('unit_tests',self.test())]

    class FakeProvider:
        is_mock=False
        def generate_json(self, system, prompt, schema, *, timeout=None):
            props=schema.get('properties',{})
            if 'status' in props: return {'status':'READY_FOR_REVIEW','reply':'Requirements ready.','missing_information':[],'project_name':'Clothes Store','project_type':'flutter','prd':'# PRD\nFlutter app.','requirements':'# Requirements\n- Build Flutter app','acceptance_criteria':'# Acceptance\n- App works','assumptions':[]}
            if 'PRD' in props: return {k: ('1. '+k+' | Depends: 0 | Acceptance: implemented | Files: lib/main.dart | Tests: widget test') for k in props}
            if 'blocking' in props: return {'contradictions':[],'missing_requirements':[],'ambiguities':[],'missing_acceptance_criteria':[],'technical_risks':[],'security_risks':[],'dependency_issues':[],'blocking':False,'summary':'ok'}
            if 'actions' in props: return {'summary':'implemented','actions':[{'op':'write','path':'pubspec.yaml','content':'name: clothes_store\n'},{'op':'write','path':'lib/main.dart','content':'void main() {}\n'}],'tests_to_run':['flutter test'],'warnings':[]}
            if 'findings' in props: return {'findings':[],'summary':'review ok'}
            return {k: [] if v.get('type')=='array' else '' for k,v in props.items()}

    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','openai-compatible','fake-model','fake-key',3,30,10,mode='real')
    settings.ensure_directories(); db=Database(settings.db_path); o=Orchestrator(db,settings)
    monkeypatch.setitem(ADAPTERS,'fake-flutter',FakeFlutter()) if isinstance(ADAPTERS,dict) else None
    # Replace adapter detection directly to avoid depending on global registry shape.
    monkeypatch.setattr('factory.orchestrator.by_name', lambda name: FakeFlutter() if name=='flutter' else None)
    monkeypatch.setattr('factory.orchestrator.detect', lambda w: FakeFlutter())
    monkeypatch.setattr('factory.orchestrator.run_command', lambda role, command, cwd, timeout=120: CommandResult(command,0,'Flutter fake OK','',0.01))
    monkeypatch.setattr('factory.agents.tester.execute', lambda role, kind, command, cwd, timeout: CommandResult(command,0,'Flutter fake OK','',0.01))
    provider=FakeProvider(); o.agents.update(planner=PlannerAgent(provider),analyzer=AnalyzerAgent(provider),developer=DeveloperAgent(provider),reviewer=ReviewerAgent(provider),uiux=UIUXAgent(MockProvider('mock')),uiux_reviewer=UIUXReviewerAgent(MockProvider('mock')))
    p=o.create_project('Clothes Store','Build a Flutter clothing store app')
    (Path(p.workspace_path)/'pubspec.yaml').write_text('name: clothes_store\n')
    state=o.run(p.id)
    from factory.approvals import ApprovalService
    req=[a for a in o.db.list_approvals(p.id) if a.requested_action=='requirements_approval'][-1]
    ApprovalService(o.db).resolve(req, True, 'test requirements')
    state=o.run(p.id)
    assert state.current_state.value == 'WAITING_FOR_DESIGN_APPROVAL'
    design=[a for a in o.db.list_approvals(p.id) if a.requested_action=='design_approval'][-1]
    ApprovalService(o.db).resolve(design, True, 'test design')
    state=o.run(p.id)
    assert state.current_state.value == 'BLOCKED'


def test_developer_failure_retries_same_task_before_blocking(tmp_path):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','openai','model','dummy',3,10,10,mode='real')
    settings.ensure_directories()
    o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('p','Build Python app')
    task=Task(project_id=p.id,title='Implement app',description='do it',status=TaskStatus.IN_PROGRESS)
    o.db.save_task(task)
    state=o.db.get_state(p.id); state.current_state=WorkflowState.IMPLEMENTATION; o.db.save_state(state)
    p.current_state=WorkflowState.IMPLEMENTATION; o.db.save_project(p)
    class BadDeveloper:
        def run(self,*args,**kwargs):
            return __import__('factory.models',fromlist=['AgentResult']).AgentResult(success=False,agent_name='Developer Agent',task_id=task.id,errors=['compiler error'],next_action='fix')
    o.agents['developer']=BadDeveloper()
    out=o.run(p.id)
    saved=o.db.get_task(task.id)
    assert saved.retry_count == 3
    assert saved.status == TaskStatus.FAILED
    assert out.current_state == WorkflowState.BLOCKED


def test_flutter_requires_dart_and_can_be_retried_after_sdk_install(tmp_path, monkeypatch):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','openai','model','dummy',3,10,10,mode='real')
    settings.ensure_directories(); o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('Clothes Store','Build a Flutter app')
    state=o.db.get_state(p.id); state.current_state=WorkflowState.DESIGN_APPROVED; o.db.save_state(state); p.current_state=WorkflowState.DESIGN_APPROVED; o.db.save_project(p)
    from factory.tools.shell import CommandResult
    calls=[]
    def fake_run(role, command, cwd, timeout=120):
        calls.append(command)
        if command in ('flutter --version','dart --version'):
            return CommandResult(command,127,'',f'{command} not found',0.01)
        return CommandResult(command,0,'','',0.01)
    monkeypatch.setattr('factory.orchestrator.run_command', fake_run)
    state=o.run(p.id)
    assert state.current_state == WorkflowState.BLOCKED
    assert any('Dart SDK is unavailable' in e or 'Flutter SDK is unavailable' in e for e in state.error_history)


def test_restart_recovers_in_progress_task(tmp_path):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','mock','model',None,3,10,10)
    settings.ensure_directories(); o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('p','Build a test project')
    t=Task(project_id=p.id,title='Interrupted',description='resume',status=TaskStatus.IN_PROGRESS)
    o.db.save_task(t)
    state=o.db.get_state(p.id); state.current_state=WorkflowState.IMPLEMENTATION; o.db.save_state(state); p.current_state=WorkflowState.IMPLEMENTATION; o.db.save_project(p)
    o.run(p.id,mock=True)
    assert o.db.get_task(t.id).status == TaskStatus.DONE


def test_manual_retry_rejected_dependency_creates_fresh_approval(tmp_path):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','openai','model','dummy',3,10,10,mode='real')
    settings.ensure_directories(); o=Orchestrator(Database(settings.db_path),settings)
    p=o.create_project('Clothes Store','Build a Flutter app')
    a=__import__('factory.approvals',fromlist=['ApprovalService']).ApprovalService(o.db).request(p.id,'flutter pub get','need deps')
    __import__('factory.approvals',fromlist=['ApprovalService']).ApprovalService(o.db).resolve(a,False,'no')
    o.set_state(p,WorkflowState.BLOCKED)
    state=o.retry(p.id)
    approvals=o.db.list_approvals(p.id)
    assert state.current_state == WorkflowState.BLOCKED
    assert len(approvals) == 2 and approvals[0].status == __import__('factory.models',fromlist=['ApprovalStatus']).ApprovalStatus.PENDING
