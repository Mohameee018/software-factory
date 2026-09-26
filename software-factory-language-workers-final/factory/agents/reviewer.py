from __future__ import annotations
from pathlib import Path
from factory.agents.base import Agent
from factory.tools.safety import redact_secrets
from factory.models import AgentResult, ReviewFinding, Severity
SCHEMA={'type':'object','properties':{'findings':{'type':'array'},'summary':{'type':'string'}},'required':['findings','summary']}
class ReviewerAgent(Agent):
    name='Code Reviewer'; role='reviewer'; instructions='Review actual generated/modified source code against requirements and acceptance criteria. Do not modify source. Return precise evidence with file and line when possible.'
    def __init__(self,provider): self.provider=provider
    def run(self,context,task=None):
        team_context = ''
        context_file = Path(context.workspace) / 'docs' / 'TEAM_CONTEXT.md'
        if context_file.exists():
            team_context = redact_secrets(context_file.read_text(encoding='utf-8', errors='ignore')[-12000:])
        files=[]
        for p in Path(context.workspace).rglob('*'):
            if p.is_file() and '.git' not in p.parts:
                text=redact_secrets(p.read_text(encoding='utf-8',errors='ignore')[:16000])
                files.append(f'FILE {p.relative_to(context.workspace)}\n{text}')
        prompt='SHARED TEAM CONTEXT:\n'+team_context+'\n\n'+'\n\n'.join(files[:100])
        try:data=self.provider.generate_json(self.instructions,prompt,SCHEMA,timeout=context.timeout)
        except Exception as e:return AgentResult(success=False,agent_name=self.name,errors=[str(e)],next_action='fix')
        findings=[]
        for raw in data.get('findings',[]):
            try:
                f=ReviewFinding(severity=Severity(str(raw.get('severity','MEDIUM')).upper()),category=str(raw.get('category','correctness')),file=raw.get('file'),line=raw.get('line'),description=str(raw.get('description','')),evidence=str(raw.get('evidence','')),suggested_fix=str(raw.get('suggested_fix','')))
                findings.append(f)
            except Exception: continue
        report='# Code Review Report\n\n'+data.get('summary','Review completed.')+'\n\n'+str([f.model_dump() for f in findings])+'\n'
        (Path(context.workspace)/'docs').mkdir(parents=True,exist_ok=True); (Path(context.workspace)/'docs'/'CODE_REVIEW.md').write_text(report,encoding='utf-8')
        return AgentResult(success=not findings,agent_name=self.name,summary=data.get('summary','Review completed.'),detailed_output={'findings':[f.model_dump() for f in findings]},next_action='security' if not findings else 'fix',files_created=['docs/CODE_REVIEW.md'],completion_evidence=['docs/CODE_REVIEW.md'])
