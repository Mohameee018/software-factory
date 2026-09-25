from pathlib import Path
from factory.config import Settings
from factory.database import Database
from factory.orchestrator import Orchestrator
from factory.models import WorkflowState
from factory.providers.base import LLMResponse, AIProvider
from factory.agents import PlannerAgent, AnalyzerAgent, DeveloperAgent, ReviewerAgent, UIUXAgent, UIUXReviewerAgent, UIUXAgent, UIUXReviewerAgent, ReleaseAgent
from factory.adapters import registry
from factory.adapters.base import ProjectAdapter

class LocalPythonAdapter(ProjectAdapter):
    name='local-python'
    def detect_project(self,w): return (Path(w)/'pyproject.toml').exists()
    def install_dependencies(self): return 'python -m pytest --version'
    def format(self): return 'python -m compileall .'
    def analyze(self): return 'python -m compileall .'
    def test(self): return 'python -m pytest -q'
    def build(self): return 'python -m compileall .'
    def validate_environment(self): return 'python --version'


class DeterministicE2EProvider(AIProvider):
    def __init__(self): self.review_calls=0
    def generate(self, system, prompt, *, timeout=None): return LLMResponse('', 'e2e')
    def generate_json(self, system, prompt, schema, *, timeout=None, images=None):
        if 'Design professional' in system:
            return {'design_summary':'Test design.','design_system':'Simple responsive design.','screens':['Home'],'user_flow':'Open to action.','html_preview':'<html><body><h1>Test</h1></body></html>'}
        if 'Planner Agent' in system or 'natural-language request' in system:
            return {'PRD':'# PRD\nBuild a local sample.','MVP':'# MVP\nPassing tests.','ARCHITECTURE':'# Architecture\nSimple Python package.','REQUIREMENTS':'# Requirements\n- Python project','TASKS':'# Tasks\n- Build sample project','ACCEPTANCE_CRITERIA':'# Acceptance\n- Tests pass','RISKS':'# Risks\n- None known'}
        if 'Analyzer Agent' in system:
            return {'contradictions':[],'missing_requirements':[],'ambiguities':[],'missing_acceptance_criteria':[],'technical_risks':[],'security_risks':[],'dependency_issues':[],'blocking':False,'summary':'Analysis passed.'}
        if 'Compare the implemented application' in system:
            return {'findings':[],'summary':'UI/UX review passed.'}
        if 'Review actual generated' in system:
            self.review_calls += 1
            if self.review_calls == 1:
                return {'findings':[{'severity':'MEDIUM','category':'maintainability','file':'app.py','line':1,'description':'Add a module docstring.','evidence':'No module docstring.','suggested_fix':'Add a short module docstring.'}],'summary':'One review finding.'}
            return {'findings':[],'summary':'Review passed.'}
        if 'software developer' in system:
            if 'Fix code review findings' in prompt or 'Fix UI/UX review findings' in prompt:
                return {'actions':[{'op':'write','path':'app.py','content':'"""Sample application."""\n\nVALUE = 1\n'}],'summary':'Applied review fix.'}
            if 'TEST/IMPLEMENTATION FAILURE' in prompt:
                return {'actions':[{'op':'write','path':'test_app.py','content':'def test_value():\n    assert 1 == 1\n'}],'summary':'Fixed the failing test.'}
            return {'actions':[{'op':'write','path':'pyproject.toml','content':'[project]\nname="sample"\nversion="0.1.0"\nrequires-python=">=3.11"\n[tool.pytest.ini_options]\ntestpaths=["."]\n'}, {'op':'write','path':'app.py','content':'VALUE = 1\n'}, {'op':'write','path':'test_app.py','content':'def test_value():\n    assert 1 == 2\n'}],'summary':'Created intentionally failing sample.'}
        return {}

def test_real_orchestrator_e2e_failure_fix_review_fix(tmp_path, monkeypatch):
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','openai','e2e','dummy',3,50,20,mode='real')
    settings.ensure_directories()
    o=Orchestrator(Database(settings.db_path),settings)
    provider=DeterministicE2EProvider()
    o.agents['planner']=PlannerAgent(provider); o.agents['analyzer']=AnalyzerAgent(provider); o.agents['developer']=DeveloperAgent(provider); o.agents['reviewer']=ReviewerAgent(provider); o.agents['uiux']=UIUXAgent(__import__('factory.providers.mock',fromlist=['MockProvider']).MockProvider('mock')); o.agents['uiux_reviewer']=UIUXReviewerAgent(__import__('factory.providers.mock',fromlist=['MockProvider']).MockProvider('mock')); o.agents['release']=ReleaseAgent()
    monkeypatch.setattr(registry, 'ADAPTERS', [LocalPythonAdapter(), *registry.ADAPTERS])
    p=o.create_project('E2E','Build a deterministic Python sample')
    state=o.run(p.id, mock=False)
    assert state.current_state == WorkflowState.WAITING_FOR_DESIGN_APPROVAL
    from factory.approvals import ApprovalService
    approval=[a for a in o.db.list_approvals(p.id) if a.requested_action=='design_approval'][-1]
    ApprovalService(o.db).resolve(approval, True, 'test')
    state=o.run(p.id, mock=False)
    assert state.current_state == WorkflowState.READY_FOR_HUMAN
    final=[a for a in o.db.list_approvals(p.id) if a.requested_action=='final_approval'][-1]
    ApprovalService(o.db).resolve(final, True, 'test final approval')
    state=o.run(p.id, mock=False)
    assert state.current_state == WorkflowState.COMPLETED
    tests=o.db.list_events(p.id, 200)
    assert any(e.event_type == 'STATE_CHANGED' and e.state == 'FIXING' for e in tests)
    assert any('Fix code review findings' in t.title for t in o.db.list_tasks(p.id))
    assert (Path(p.workspace_path)/'app.py').read_text(encoding='utf-8').startswith('"""')
    release=Path(p.workspace_path)/'release'/f'{p.id}-release.zip'
    manifest=Path(p.workspace_path)/'release'/'RELEASE_MANIFEST.json'
    assert release.is_file() and release.stat().st_size > 0
    assert manifest.is_file()

class FakeFlutterAdapter(ProjectAdapter):
    name='fake-flutter'
    def detect_project(self,w): return (Path(w)/'pubspec.yaml').exists()
    def install_dependencies(self): return 'flutter pub get'
    def format(self): return 'dart format .'
    def analyze(self): return 'flutter analyze'
    def test(self): return 'flutter test'
    def build(self): return 'flutter build apk --debug'
    def validate_environment(self): return 'flutter --version'
    def validation_commands(self): return [('dependencies','flutter pub get'),('format','dart format .'),('static_analysis','flutter analyze'),('unit_tests','flutter test'),('build_validation','flutter build apk --debug')]


class ClothesStoreProvider(AIProvider):
    def generate(self, system, prompt, *, timeout=None): return LLMResponse('', 'fake-clothes')
    def generate_json(self, system, prompt, schema, *, timeout=None, images=None):
        if 'Design professional' in system:
            return {'design_summary':'Professional clothing-store mobile UI.','design_system':'Clean responsive retail design with consistent spacing and accessible contrast.','screens':['Home','Categories','Product Details','Cart'],'user_flow':'Browse → details → add to cart → checkout.','html_preview':'<!doctype html><html><body><h1>Clothes Store</h1></body></html>'}
        if 'Planner Agent' in system or 'natural-language request' in system:
            return {
                'PRD':'# Clothes Store\nFlutter local clothing store.',
                'MVP':'# MVP\nBrowse, details, cart.',
                'ARCHITECTURE':'# Architecture\nCore Flutter only.',
                'REQUIREMENTS':'# Requirements\nMen, Women, Kids; local data; no backend.',
                'TASKS':'# Tasks\n1. Build Clothes Store UI | Depends: 0 | Acceptance: Home, categories, details, cart | Files: lib/main.dart, lib/models/product.dart, lib/data/products.dart, lib/screens/home_screen.dart, lib/screens/product_details_screen.dart, lib/screens/cart_screen.dart | Tests: widget tests',
                'ACCEPTANCE_CRITERIA':'# Acceptance\n- Local mock data only\n- Cart total works',
                'RISKS':'# Risks\n- Flutter SDK required.'
            }
        if 'Analyzer Agent' in system:
            return {'contradictions':[],'missing_requirements':[],'ambiguities':[],'missing_acceptance_criteria':[],'technical_risks':[],'security_risks':[],'dependency_issues':[],'blocking':False,'summary':'Analysis passed.'}
        if 'software developer' in system:
            files={
                'lib/main.dart':'import \'package:flutter/material.dart\';\nvoid main() => runApp(const ClothesStoreApp());\nclass ClothesStoreApp extends StatelessWidget { const ClothesStoreApp({super.key}); @override Widget build(BuildContext context) => const MaterialApp(home: Scaffold(body: Text(\'Clothes Store\'))); }\n',
                'lib/models/product.dart':'class Product { final String name; final double price; final String category; const Product(this.name,this.price,this.category); }\n',
                'lib/data/products.dart':'const products = <Map<String,Object>>[{\'name\':\'Basic Tee\',\'price\':29.0,\'category\':\'Men\'}];\n',
                'lib/screens/home_screen.dart':'import \'package:flutter/material.dart\'; class HomeScreen extends StatelessWidget { const HomeScreen({super.key}); @override Widget build(BuildContext c)=>const Scaffold(body: Text(\'Men Women Kids\')); }\n',
                'lib/screens/product_details_screen.dart':'import \'package:flutter/material.dart\'; class ProductDetailsScreen extends StatelessWidget { const ProductDetailsScreen({super.key}); @override Widget build(BuildContext c)=>const Scaffold(body: Text(\'Product Details Add to Cart\')); }\n',
                'lib/screens/cart_screen.dart':'import \'package:flutter/material.dart\'; class CartScreen extends StatelessWidget { const CartScreen({super.key}); @override Widget build(BuildContext c)=>const Scaffold(body: Text(\'Cart Total\')); }\n',
                'test/widget_test.dart':'import \'package:flutter_test/flutter_test.dart\'; void main(){ testWidgets(\'Clothes Store renders\',(tester) async { expect(1,1); }); }\n',
            }
            return {'summary':'Implemented Clothes Store Flutter files.','actions':[{'op':'write','path':p,'content':c} for p,c in files.items()],'tests_to_run':['flutter test'],'warnings':[]}
        if 'Review actual generated' in system:
            return {'findings':[],'summary':'Review passed.'}
        return {}


def test_clothes_store_end_to_end_with_fake_dependencies(tmp_path, monkeypatch):
    from factory.adapters import registry
    from factory.agents import PlannerAgent, AnalyzerAgent, DeveloperAgent, ReviewerAgent, UIUXAgent, UIUXReviewerAgent
    settings=Settings(tmp_path/'factory.db',tmp_path/'workspaces','INFO','openai-compatible','fake','dummy',3,30,20,mode='real')
    settings.ensure_directories(); o=Orchestrator(Database(settings.db_path),settings)
    provider=ClothesStoreProvider()
    o.agents['planner']=PlannerAgent(provider); o.agents['analyzer']=AnalyzerAgent(provider); o.agents['developer']=DeveloperAgent(provider); o.agents['reviewer']=ReviewerAgent(provider); o.agents['uiux']=UIUXAgent(__import__('factory.providers.mock',fromlist=['MockProvider']).MockProvider('mock')); o.agents['uiux_reviewer']=UIUXReviewerAgent(__import__('factory.providers.mock',fromlist=['MockProvider']).MockProvider('mock'))
    monkeypatch.setattr(registry, 'ADAPTERS', [FakeFlutterAdapter(), *registry.ADAPTERS])
    monkeypatch.setattr(o, '_flutter_dependencies_approved', lambda p, state: True)
    monkeypatch.setattr('factory.orchestrator.run_command', lambda role, command, cwd, timeout=120: __import__('factory.tools.shell',fromlist=['CommandResult']).CommandResult(command,0,'ok','',0.01))
    monkeypatch.setattr('factory.agents.tester.execute', lambda role, kind, command, cwd, timeout: __import__('factory.tools.shell',fromlist=['CommandResult']).CommandResult(command,0,'ok','',0.01))
    p=o.create_project('Clothes Store','Build a Flutter clothing store with Men Women Kids, product details, cart and local mock data.')
    # Simulate Flutter project creation because this test isolates the orchestration contract, not the SDK.
    (Path(p.workspace_path)/'pubspec.yaml').write_text('name: clothes_store\n')
    state=o.run(p.id)
    assert state.current_state == WorkflowState.WAITING_FOR_DESIGN_APPROVAL
    from factory.approvals import ApprovalService
    approval=[a for a in o.db.list_approvals(p.id) if a.requested_action=='design_approval'][-1]
    ApprovalService(o.db).resolve(approval, True, 'test')
    state=o.run(p.id)
    assert state.current_state == WorkflowState.READY_FOR_HUMAN
    final=[a for a in o.db.list_approvals(p.id) if a.requested_action=='final_approval'][-1]
    ApprovalService(o.db).resolve(final, True, 'test final approval')
    state=o.run(p.id)
    assert state.current_state == WorkflowState.COMPLETED
    for rel in ['lib/main.dart','lib/models/product.dart','lib/data/products.dart','lib/screens/home_screen.dart','lib/screens/product_details_screen.dart','lib/screens/cart_screen.dart','test/widget_test.dart']:
        assert (Path(p.workspace_path)/rel).is_file()
