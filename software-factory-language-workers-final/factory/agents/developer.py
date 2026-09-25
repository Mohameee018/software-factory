from __future__ import annotations
from pathlib import Path
from factory.agents.base import Agent
from factory.tools.safety import redact_secrets
from factory.models import AgentResult
from factory.tools.filesystem import WorkspaceFS
from factory.tools.shell import run

ACTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'summary': {'type': 'string'},
        'actions': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'op': {'type': 'string'},
                    'path': {'type': 'string'},
                    'content': {'type': 'string'},
                    'command': {'type': 'string'},
                },
                'required': ['op'],
            },
        },
        'tests_to_run': {'type': 'array', 'items': {'type': 'string'}},
        'warnings': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['summary', 'actions'],
}

class DeveloperAgent(Agent):
    name='Developer Agent'; role='developer'
    instructions='Act as a real software developer. Inspect the workspace and requirements, then return only structured controlled file/shell actions. Never access paths outside the workspace. Never claim tests passed without execution. Do not delete files; report deletion requests as unsafe.'
    def __init__(self,provider): self.provider=provider

    def _snapshot(self,w):
        fs=WorkspaceFS(w,'developer'); out=[]
        for rel in fs.list_files():
            if rel.startswith('.git/') or rel.startswith('build/'):
                continue
            try: content=fs.read(rel)
            except Exception: continue
            out.append(f'FILE: {rel}\n{content[:12000]}')
        return '\n\n'.join(out[:100])

    def run(self,context,task=None):
        if task is None:return AgentResult(success=False,agent_name=self.name,errors=['task_required'],next_action='fix')
        w=Path(context.workspace).resolve(); fs=WorkspaceFS(w,'developer')
        docs=''
        for rel in ('docs/PRD.md','docs/REQUIREMENTS.md','docs/ARCHITECTURE.md','docs/ACCEPTANCE_CRITERIA.md','docs/ANALYSIS.md'):
            if fs.exists(rel): docs += f'\n### {rel}\n{redact_secrets(fs.read(rel)[:12000])}'
        prompt=f'''Task ID: {task.id}\nTask: {task.title}\nDescription: {task.description}\nAcceptance criteria: {task.acceptance_criteria}\nExpected files: {task.files_expected}\nRequired tests: {task.tests_required}\nPrevious failure: {task.failure_reason or 'none'}\n\nPROJECT DOCUMENTATION:\n{docs}\n\nWORKSPACE SOURCE:\n{self._snapshot(w)}\n\nReturn ONLY structured JSON matching the supplied schema. Use relative workspace paths only. File writes must contain complete file content. Allowed ops are write and run. Delete requests must NOT be emitted. Commands must be safe and compatible with the controlled shell allowlist. Do not add external dependencies unless the task explicitly has approved dependency changes. For Flutter, prefer Dart/Flutter core and local mock data when requirements permit.'''
        try:data=self.provider.generate_json(self.instructions,prompt,ACTION_SCHEMA,timeout=context.timeout)
        except Exception as e:return AgentResult(success=False,agent_name=self.name,task_id=task.id,summary='Developer structured output failed.',errors=[str(e)],next_action='fix')
        if not isinstance(data,dict) or not isinstance(data.get('actions'),list) or not isinstance(data.get('summary'),str):
            return AgentResult(success=False,agent_name=self.name,task_id=task.id,summary='Invalid Developer output.',errors=['invalid_developer_output'],next_action='fix')
        if task.files_expected and not data.get('actions'):
            return AgentResult(success=False,agent_name=self.name,task_id=task.id,summary='Developer returned no changes for a file-producing task.',errors=['no_file_changes_for_required_task'],next_action='fix')
        created=[]; modified=[]; deleted=[]; commands=[]; command_results=[]; errors=[]; changes=[]
        for action in data['actions']:
            if not isinstance(action,dict): errors.append('invalid_action'); continue
            op=action.get('op'); rel=str(action.get('path','')).strip()
            if op not in {'write','run'}:
                errors.append(f'unsupported_action:{op}')
                continue
            try:
                if op=='write':
                    if not rel: raise PermissionError('File path is required')
                    # WorkspaceFS performs canonical boundary validation before any write.
                    existed=fs.exists(rel)
                    fs.write(rel,str(action.get('content','')))
                    (modified if existed else created).append(rel)
                    changes.append({'op':'modify' if existed else 'create','path':rel})
                elif op=='run':
                    cmd=str(action.get('command','')).strip()
                    if not cmd: raise PermissionError('Command is required')
                    r=run('developer',cmd,w,context.timeout); commands.append(cmd)
                    command_results.append({'command':cmd,'exit_code':r.exit_code,'stdout':r.stdout,'stderr':r.stderr,'duration_seconds':r.duration_seconds})
                    changes.append({'op':'run','command':cmd,'exit_code':r.exit_code})
                    if r.exit_code:
                        errors.append(f'{cmd}\nexit={r.exit_code}\n{r.stderr[-4000:]}')
            except Exception as e:
                errors.append(str(e))
        warnings=[str(x) for x in data.get('warnings',[]) if isinstance(x,str)]
        tests=[str(x) for x in data.get('tests_to_run',[]) if isinstance(x,str)]
        return AgentResult(success=not errors,agent_name=self.name,task_id=task.id,summary=data['summary'],files_created=created,files_modified=modified,files_deleted=deleted,files_to_create=created,files_to_modify=modified,files_to_delete=deleted,generated_changes=changes,commands_requested=commands,commands_executed=commands,detailed_output={'command_results':command_results},tests_to_run=tests,tests_run=tests,warnings=warnings,errors=errors,next_action='test' if not errors else 'fix')
