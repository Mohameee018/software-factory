from factory.agents.base import Agent
from factory.models import AgentResult
class ReleaseAgent(Agent):
 name='Release Agent'; role='release'; instructions='Prepare release artifacts; deployment always requires human approval.'
 def run(self,context,task=None): return AgentResult(success=True,agent_name=self.name,summary='Release preparation available; deployment is approval-gated.')
