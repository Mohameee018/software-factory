from __future__ import annotations
from pathlib import Path
from factory.agents.base import Agent
from factory.models import AgentResult, ReviewFinding, Severity

SCHEMA={'type':'object','properties':{'findings':{'type':'array'},'summary':{'type':'string'}},'required':['findings','summary']}

class UIUXReviewerAgent(Agent):
    name='UI/UX Reviewer'; role='uiux_reviewer'
    instructions='Compare the implemented application with the APPROVED UI/UX design. Check layout, screens, navigation, typography, colors, spacing, responsive behavior, states and user flow. Use concrete evidence from source files. Do not redesign; report implementation mismatches only.'
    def __init__(self,provider): self.provider=provider
    def run(self,context,task=None):
        w=Path(context.workspace); design=w/'docs'/'DESIGN.md'; preview=w/'docs'/'design'/'preview.html'
        if not design.exists():
            return AgentResult(success=False,agent_name=self.name,summary='Approved design document is missing.',errors=['missing_approved_design'],next_action='fix')
        parts=['APPROVED DESIGN:\n'+design.read_text(encoding='utf-8',errors='ignore')[:20000]]
        if preview.exists(): parts.append('DESIGN PREVIEW:\n'+preview.read_text(encoding='utf-8',errors='ignore')[:12000])
        files=[]
        for p in w.rglob('*'):
            if p.is_file() and '.git' not in p.parts and 'docs' not in p.parts and 'build' not in p.parts:
                try: files.append('IMPLEMENTATION FILE '+str(p.relative_to(w))+'\n'+p.read_text(encoding='utf-8',errors='ignore')[:12000])
                except Exception: pass
        parts.append('\n\n'.join(files[:100]))
        prompt='\n\n'.join(parts)
        try:data=self.provider.generate_json(self.instructions,prompt,SCHEMA,timeout=context.timeout)
        except Exception as e:return AgentResult(success=False,agent_name=self.name,summary='UI/UX review failed.',errors=[str(e)],next_action='fix')
        if getattr(self.provider,'is_mock',False):
            data={'findings':[],'summary':'Mock UI/UX review passed.'}
        findings=[]
        for raw in data.get('findings',[]):
            try:
                findings.append(ReviewFinding(severity=Severity(str(raw.get('severity','MEDIUM')).upper()),category=str(raw.get('category','visual_consistency')),file=raw.get('file'),line=raw.get('line'),description=str(raw.get('description','')),evidence=str(raw.get('evidence','')),suggested_fix=str(raw.get('suggested_fix',''))))
            except Exception: pass
        return AgentResult(success=not findings,agent_name=self.name,summary=data.get('summary','UI/UX review completed.'),detailed_output={'findings':[f.model_dump() for f in findings]},next_action='security' if not findings else 'fix')
