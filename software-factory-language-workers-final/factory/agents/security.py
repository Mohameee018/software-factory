import re
from pathlib import Path
from factory.agents.base import Agent
from factory.models import AgentResult
class SecurityAgent(Agent):
 name='Security Reviewer'; role='security'; instructions='Scan source for secrets, traversal, unsafe commands and insecure configuration.'
 def run(self,context,task=None):
  patterns=[re.compile(r'(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*[\"\'][^\"\']{8,}[\"\']')]
  hits=[]
  for p in Path(context.workspace).rglob('*'):
   if p.is_file() and '.git' not in p.parts:
    try:t=p.read_text(encoding='utf-8',errors='ignore')
    except Exception:continue
    for pat in patterns:
     if pat.search(t):hits.append(str(p.relative_to(context.workspace)))
  report=Path(context.workspace)/'docs'/'SECURITY_REVIEW.md'; report.parent.mkdir(parents=True,exist_ok=True)
  if hits:
   report.write_text('# Security Review\\n\\nFAIL\\n\\n'+ '\\n'.join(hits),encoding='utf-8')
   return AgentResult(success=False,agent_name=self.name,summary='Potential hard-coded secrets detected.',errors=hits,next_action='fix',files_created=['docs/SECURITY_REVIEW.md'],completion_evidence=['docs/SECURITY_REVIEW.md'])
  report.write_text('# Security Review\\n\\nPASS\\n\\nNo obvious hard-coded secrets were detected by the configured scan.',encoding='utf-8')
  return AgentResult(success=True,agent_name=self.name,summary='Security scan completed with no obvious hard-coded secrets.',next_action='ready',files_created=['docs/SECURITY_REVIEW.md'],completion_evidence=['docs/SECURITY_REVIEW.md'])
