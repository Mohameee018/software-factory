from factory.agents.base import Agent
class ManagerAgent(Agent):
 name='Agent Manager'; role='manager'; instructions='Coordinate specialized agents through the orchestrator.'
 def run(self,context,task=None): raise NotImplementedError('Manager does not execute workflow directly')
