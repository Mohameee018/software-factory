from __future__ import annotations
from factory.tools.shell import run

def execute(role,kind,command,cwd,timeout):
 return run(role,command,cwd,timeout)
