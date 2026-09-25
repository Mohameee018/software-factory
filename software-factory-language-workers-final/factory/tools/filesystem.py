from __future__ import annotations
from pathlib import Path
from factory.permissions import Permission,check
class WorkspaceFS:
 def __init__(self,workspace,role): self.workspace=Path(workspace).resolve();self.role=role;self.workspace.mkdir(parents=True,exist_ok=True)
 def safe(self,relative):
  p=(self.workspace/relative).resolve()
  if p!=self.workspace and self.workspace not in p.parents:raise PermissionError(f'Path outside workspace: {relative}')
  return p
 def read(self,relative): check(self.role,Permission.READ_DOCS if str(relative).replace('\\','/').startswith('docs/') else Permission.READ_SOURCE);return self.safe(relative).read_text(encoding='utf-8')
 def write(self,relative,text):
  rel=str(relative).replace('\\','/');check(self.role,Permission.WRITE_DOCS if rel.startswith('docs/') else Permission.MODIFY_SOURCE if self.role=='developer' else Permission.CREATE_FILES);p=self.safe(rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8');return str(p.relative_to(self.workspace))
 def exists(self,relative):return self.safe(relative).exists()
 def list_files(self):return [str(p.relative_to(self.workspace)) for p in self.workspace.rglob('*') if p.is_file()]
 def delete(self,relative):check(self.role,Permission.DELETE_FILES);p=self.safe(relative);p.unlink()
