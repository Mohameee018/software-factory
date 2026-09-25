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
  if hits:return AgentResult(success=False,agent_name=self.name,summary='Potential hard-coded secrets detected.',errors=hits,next_action='fix')
  return AgentResult(success=True,agent_name=self.name,summary='Security scan completed with no obvious hard-coded secrets.',next_action='ready')
