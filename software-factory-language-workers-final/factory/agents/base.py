from __future__ import annotations
from abc import ABC,abstractmethod
from factory.models import AgentResult
class Agent(ABC):
 name='base'; role='base'; instructions=''; allowed_tools=[]
 @abstractmethod
 def run(self,context,task=None)->AgentResult: ...
