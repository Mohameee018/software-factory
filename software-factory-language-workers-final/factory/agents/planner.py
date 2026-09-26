from __future__ import annotations
from pathlib import Path
from factory.agents.base import Agent
from factory.models import AgentResult

DOCS=('PRD','MVP','ARCHITECTURE','REQUIREMENTS','TASKS','ACCEPTANCE_CRITERIA','RISKS')
SCHEMA={'type':'object','properties':{k:{'type':'string'} for k in DOCS},'required':list(DOCS)}
class PlannerAgent(Agent):
    name='Planner Agent'; role='planner'; instructions='Turn a natural-language request into complete, traceable project documentation. Never invent critical requirements; surface ambiguity explicitly.'
    def __init__(self,provider): self.provider=provider
    def run(self,context,task=None):
        w=Path(context.workspace); d=w/'docs'; d.mkdir(parents=True,exist_ok=True)
        team_context=(w/'docs'/'TEAM_CONTEXT.md').read_text(encoding='utf-8',errors='ignore') if (w/'docs'/'TEAM_CONTEXT.md').exists() else 'No direct team directives yet.'; client_source=(w/'docs'/'CLIENT_CONVERSATION.md').read_text(encoding='utf-8',errors='ignore') if (w/'docs'/'CLIENT_CONVERSATION.md').exists() else context.project.description
        prompt=f'''SOURCE OF TRUTH — CLIENT CONVERSATION:\n{client_source[-30000:]}\n\nPROJECT INTAKE:\n{context.project.description}\n\nShared team context:\n{team_context[-12000:]}\n\nProduce PRD, MVP, ARCHITECTURE, REQUIREMENTS, TASKS, ACCEPTANCE_CRITERIA and RISKS. Preserve unknowns as explicit AMBIGUITY items. Do not invent credentials, integrations, legal constraints, or acceptance criteria not implied by the request. CRITICAL: every document must describe the same product/domain as the CLIENT CONVERSATION. Never substitute a generic workflow/project-management product for the client's actual product. If the client says Flutter, preserve Flutter.
For TASKS, create small executable tasks in dependency order. Prefer one numbered task per line using this format: `1. Task title | Depends: 0 | Acceptance: criterion; criterion | Files: path.dart, path_test.dart | Tests: test description`. Use `Depends: 0` for no dependency. Tasks must be specific enough for a Developer Agent to implement without inventing product behavior.'''
        try:data=self.provider.generate_json(self.instructions,prompt,SCHEMA,timeout=context.timeout)
        except Exception as e:return AgentResult(success=False,agent_name=self.name,summary='Planning failed.',errors=[str(e)],next_action='fix')
        if getattr(self.provider,'is_mock',False):
            data={
                'PRD':'# Product Requirements\n\n'+context.project.description,
                'MVP':'# MVP\n\nCore requested journey.',
                'ARCHITECTURE':'# Architecture\n\nModular project architecture.',
                'REQUIREMENTS':'# Requirements\n\n- '+context.project.description,
                'TASKS':'# Tasks\n\n- Implement requested functionality: '+context.project.description+' | Depends: 0 | Acceptance: requested functionality works | Files: app/main | Tests: automated tests\n- Add automated tests for the requested functionality | Depends: 1 | Acceptance: tests pass | Files: tests | Tests: automated tests',
                'ACCEPTANCE_CRITERIA':'# Acceptance Criteria\n\n- Project reaches the human review gate.',
                'RISKS':'# Risks\n\n- External dependencies may be unavailable.'
            }
        created=[]
        for n in DOCS:
            value=data.get(n,'')
            if not value:return AgentResult(success=False,agent_name=self.name,summary=f'Missing {n}.',errors=[f'planner_missing_{n}'],next_action='fix')
            p=d/f'{n}.md';p.write_text(str(value),encoding='utf-8');created.append(str(p.relative_to(w)))
        context.project.acceptance_criteria=[x.strip('- ').strip() for x in str(data['ACCEPTANCE_CRITERIA']).splitlines() if x.strip() and not x.startswith('#')]
        return AgentResult(success=True,agent_name=self.name,summary='Generated validated project documentation.',detailed_output={'documents':DOCS},files_created=created,next_action='analyze',completion_evidence=created)
