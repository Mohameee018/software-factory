from __future__ import annotations
from pathlib import Path
from factory.agents.base import Agent
from factory.models import AgentResult

class AuditorAgent(Agent):
    """Independent evidence auditor; it does not create implementation work."""
    name='AI Auditor'
    role='auditor'
    instructions=(
        'Act as an independent quality auditor. Do not redesign or implement anything. '
        'Inspect the project evidence and determine whether the delivered work is internally consistent, '
        'traceable, tested, reviewed, and ready for human approval. Treat missing evidence as a failure. '
        'Return JSON with blocking, findings, missing_evidence, traceability_ok, tests_ok, reviews_ok, summary.'
    )
    SCHEMA={
        'type':'object',
        'properties':{
            'blocking':{'type':'boolean'},
            'findings':{'type':'array'},
            'missing_evidence':{'type':'array'},
            'traceability_ok':{'type':'boolean'},
            'tests_ok':{'type':'boolean'},
            'reviews_ok':{'type':'boolean'},
            'summary':{'type':'string'}
        },
        'required':['blocking','findings','missing_evidence','traceability_ok','tests_ok','reviews_ok','summary']
    }
    def __init__(self, provider):
        self.provider=provider

    def run(self, context, task=None):
        root=Path(context.workspace); docs=root/'docs'
        required=[
            'PRD.md','REQUIREMENTS.md','ACCEPTANCE_CRITERIA.md','ARCHITECTURE.md',
            'TASKS.md','TRACEABILITY.md','TEST_REPORT.md','CODE_REVIEW.md',
            'UX_REVIEW.md','SECURITY_REVIEW.md','TEAM.md'
        ]
        missing=[f'docs/{p}' for p in required if not (docs/p).exists()]
        evidence=[]
        for p in required:
            f=docs/p
            if f.exists():
                evidence.append(f'### {p}\n{f.read_text(encoding="utf-8",errors="ignore")[:12000]}')
        if missing:
            data={'blocking':True,'findings':[f'Missing required evidence: {x}' for x in missing],
                  'missing_evidence':missing,'traceability_ok':False,'tests_ok':False,'reviews_ok':False,
                  'summary':'Audit failed because required evidence is missing.'}
        else:
            try:
                data=self.provider.generate_json(self.instructions,'\n\n'.join(evidence),self.SCHEMA,timeout=context.timeout)
            except Exception as exc:
                detail=str(exc).strip() or f'{type(exc).__name__}: auditor provider failed'
                return AgentResult(success=False,agent_name=self.name,summary=f'Audit failed: {detail[:700]}',errors=[detail],next_action='fix')
            if getattr(self.provider,'is_mock',False):
                data={'blocking':False,'findings':[],'missing_evidence':[],'traceability_ok':True,'tests_ok':True,'reviews_ok':True,'summary':'Mock audit passed.'}
        (docs/'AUDIT_REPORT.md').write_text(
            '# Independent AI Audit\n\n'+str(data)+'\n',encoding='utf-8'
        )
        blocking=bool(data.get('blocking'))
        return AgentResult(
            success=not blocking, agent_name=self.name,
            summary=data.get('summary','Audit completed.'),
            detailed_output=data, files_created=['docs/AUDIT_REPORT.md'],
            next_action='ready' if not blocking else 'fix',
            errors=['Independent audit found blocking issues'] if blocking else [],
            completion_evidence=['docs/AUDIT_REPORT.md']
        )
