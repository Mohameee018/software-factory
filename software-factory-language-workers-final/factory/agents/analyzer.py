from __future__ import annotations
from pathlib import Path
from factory.agents.base import Agent
from factory.tools.safety import redact_secrets
from factory.models import AgentResult
SCHEMA={'type':'object','properties':{'contradictions':{'type':'array'},'missing_requirements':{'type':'array'},'ambiguities':{'type':'array'},'missing_acceptance_criteria':{'type':'array'},'technical_risks':{'type':'array'},'security_risks':{'type':'array'},'dependency_issues':{'type':'array'},'blocking':{'type':'boolean'},'summary':{'type':'string'}},'required':['contradictions','missing_requirements','ambiguities','missing_acceptance_criteria','technical_risks','security_risks','dependency_issues','blocking','summary']}
class AnalyzerAgent(Agent):
    name='Analyzer Agent'; role='analyzer'; instructions='Inspect generated documentation and identify contradictions, missing or ambiguous requirements, acceptance gaps, technical/security risks, and dependency issues. Be evidence-based.'
    def __init__(self,provider): self.provider=provider
    def run(self,context,task=None):
        d=Path(context.workspace)/'docs'; parts=[]
        for p in d.glob('*.md'):
            parts.append(f'### {p.name}\n{redact_secrets(p.read_text(encoding="utf-8",errors="ignore")[:20000])}')
        try: data=self.provider.generate_json(self.instructions,'\n\n'.join(parts),SCHEMA,timeout=context.timeout)
        except Exception as e:
            detail=str(e).strip() or f'{type(e).__name__}: analysis provider failed'
            return AgentResult(success=False,agent_name=self.name,summary=f'Analysis failed: {detail[:700]}',errors=[detail],next_action='fix')
        if getattr(self.provider,'is_mock',False):
            data={'contradictions':[],'missing_requirements':[],'ambiguities':[],'missing_acceptance_criteria':[],'technical_risks':[],'security_risks':[],'dependency_issues':[],'blocking':False,'summary':'Mock analysis passed.'}
        (d/'ANALYSIS.md').write_text('# Analysis\n\n'+str(data),encoding='utf-8')
        blocking=bool(data.get('blocking'))
        return AgentResult(success=not blocking,agent_name=self.name,summary=data.get('summary','Analysis completed.'),detailed_output=data,files_created=['docs/ANALYSIS.md'],next_action='create_tasks' if not blocking else 'fix',errors=['Blocking analysis findings'] if blocking else [])
