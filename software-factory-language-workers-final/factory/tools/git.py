from __future__ import annotations
from pathlib import Path
from factory.tools.shell import run
def init_repo(workspace):
 r=run('developer','git init',workspace); return r

def status(workspace): return run('developer','git status --short',workspace)
def commit(workspace,message): return run('developer',f'git add .',workspace), run('developer',f'git commit -m "{message.replace(chr(34),chr(39))}"',workspace)
def branch(workspace,name): return run('developer',f'git checkout -b {name}',workspace)
