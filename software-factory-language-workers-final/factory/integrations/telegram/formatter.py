from __future__ import annotations
from factory.models import Project, WorkflowState, Task

def project_status(p: Project) -> str:
    return (f'📦 <b>{_esc(p.name)}</b>\n'
            f'ID: <code>{p.id}</code>\n'
            f'State: <b>{p.current_state.value}</b>\n'
            f'Type: <code>{p.project_type.value}</code>\n'
            f'Workspace: <code>{_esc(p.workspace_path)}</code>')

def task_lines(tasks: list[Task]) -> str:
    if not tasks: return 'No tasks.'
    return '\n'.join(f'• <code>{t.id}</code> [{t.status.value}] {_esc(t.title)}' for t in tasks[:40])

def _esc(s):
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def approval_text(a):
    files='\n'.join(f'• <code>{_esc(x)}</code>' for x in a.affected_files) or '• None listed'
    return (f'⚠️ <b>HUMAN APPROVAL REQUIRED</b>\n\nAction: {_esc(a.requested_action)}\n'
            f'Reason: {_esc(a.reason)}\nRisk: <b>{a.risk_level.value}</b>\n\nAffected files:\n{files}')
