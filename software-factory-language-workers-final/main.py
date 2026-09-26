from __future__ import annotations
import json
import typer
from factory.config import get_settings
from factory.storage import build_database
from factory.logging_config import configure_logging
from factory.models import ProjectType,WorkflowState
from factory.orchestrator import Orchestrator
from factory.approvals import ApprovalService
app=typer.Typer(help='Multi-Agent Autonomous Software Factory')
def svc():
 s=get_settings();s.ensure_directories();return Orchestrator(build_database(s),s)
@app.callback()
def root():configure_logging(get_settings().log_level)
@app.command('create-project')
def create_project(name:str=typer.Option(...),description:str=typer.Option(...),project_type:ProjectType=typer.Option(ProjectType.UNKNOWN)):
 p=svc().create_project(name,description,project_type);typer.echo(f'{p.id} | {p.name} | {p.workspace_path}')
@app.command('list-projects')
def list_projects():
 for p in svc().db.list_projects():typer.echo(f'{p.id} [{p.current_state.value}] {p.name}')
@app.command('show-project')
def show_project(project_id:str):
 s=svc();p=s.db.get_project(project_id)
 if not p:raise typer.BadParameter('Project not found')
 typer.echo(f'{p.name}\nID: {p.id}\nState: {p.current_state.value}\nType: {p.project_type.value}\nWorkspace: {p.workspace_path}')
 for t in s.db.list_tasks(p.id):typer.echo(f'  {t.id} [{t.status.value}] {t.title}')
@app.command('run')
def run(project_id:str,dry_run:bool=typer.Option(False,'--dry-run'),mock:bool=typer.Option(False,'--mock')):
 st=svc().run(project_id,dry_run=dry_run,mock=mock);typer.echo(f'Run finished: {st.current_state.value}; iterations={st.iteration_count}')
@app.command('github-pr')
def github_pr(project_id:str, title:str=typer.Option('Factory change','--title'), body:str=typer.Option('','--body')):
 s=svc(); p=s.db.get_project(project_id)
 if not p: raise typer.BadParameter('Project not found')
 if not s.gitflow.enabled: raise typer.BadParameter('GitHub publishing is not configured')
 info=s.github.repo_info(p.workspace_path)
 if not info: raise typer.BadParameter('GitHub repository is not configured')
 branch=p.git_branch
 s.gitflow.commit_and_push(p.workspace_path, branch, title)
 pr=s.gitflow.create_pull_request(info['full_name'], branch, 'main', title, body)
 typer.echo(pr.get('url') or str(pr))
@app.command('github-public')
def github_public(project_id:str):
 s=svc(); p=s.db.get_project(project_id)
 if not p: raise typer.BadParameter('Project not found')
 info=s.github.make_public(p); typer.echo(info.get('html_url') or info.get('full_name'))
@app.command('status')
def status(project_id:str):
 p=svc().db.get_project(project_id)
 if not p:raise typer.BadParameter('Project not found')
 typer.echo(f'{p.id} {p.current_state.value} {p.name}')
@app.command('tasks')
def tasks(project_id:str):
 for t in svc().db.list_tasks(project_id):typer.echo(f'{t.id} [{t.status.value}] deps={t.dependencies} {t.title}')
@app.command('pause')
def pause(project_id:str):svc().pause(project_id);typer.echo('PAUSED')
@app.command('resume')
def resume(project_id:str):svc().resume(project_id);typer.echo('RESUMED')
@app.command('cancel')
def cancel(project_id:str):
 s=svc();p=s.db.get_project(project_id)
 if not p:raise typer.BadParameter('Project not found')
 s.set_state(p,WorkflowState.CANCELLED);typer.echo('CANCELLED')
@app.command('retry')
def retry(project_id:str):
 s=svc(); state=s.retry(project_id); typer.echo(f'Retry finished: {state.current_state.value}; iterations={state.iteration_count}')
@app.command('review')
def review(project_id:str):
 p=svc().db.get_project(project_id);typer.echo(f'Project {p.name if p else project_id}: human review state={p.current_state.value if p else "UNKNOWN"}')
@app.command('feedback')
def feedback(project_id:str,feedback:str=typer.Argument(...)):
 s=svc();p=s.db.get_project(project_id)
 if not p:raise typer.BadParameter('Project not found')
 t=s.add_feedback(p.id,feedback);typer.echo(f'Created task {t.id}'); s.run(p.id)
@app.command('approval-list')
def approval_list(project_id:str|None=typer.Option(None,'--project-id')):
 for a in svc().db.list_approvals(project_id):typer.echo(f'{a.id} [{a.status.value}] {a.requested_action} | {a.reason}')
@app.command('approval-approve')
def approval_approve(approval_id:str,response:str=typer.Option('Approved','--response')):
 s=svc();a=s.db.get_approval(approval_id)
 if not a:raise typer.BadParameter('Approval not found')
 resolved=ApprovalService(s.db).resolve(a,True,response);typer.echo('APPROVED')
 if resolved.requested_action == 'flutter pub get':
  state=s.run(resolved.project_id);typer.echo(f'Resumed workflow: {state.current_state.value}')
@app.command('approval-reject')
def approval_reject(approval_id:str,response:str=typer.Option('Rejected','--response')):
 s=svc();a=s.db.get_approval(approval_id)
 if not a:raise typer.BadParameter('Approval not found')
 ApprovalService(s.db).resolve(a,False,response);typer.echo('REJECTED')
@app.command('logs')
def logs(project_id:str,limit:int=typer.Option(100,'--limit')):
 for e in svc().db.list_events(project_id,limit):typer.echo(f'{e.timestamp.isoformat()} {e.event_type} state={e.state or "-"} task={e.task_id or "-"}')
@app.command('doctor')
def doctor():
 import shutil, sys
 s=get_settings(); s.ensure_directories()
 def version(command):
  path=shutil.which(command)
  if not path: return 'NOT FOUND'
  try:
   from factory.tools.shell import run as run_command
   r=run_command('developer', f'{command} --version', s.workspaces_root, s.command_timeout)
   text=(r.stdout or r.stderr).strip().splitlines()
   return text[0] if r.exit_code == 0 and text else f'ERROR ({r.exit_code})'
  except Exception as exc: return f'ERROR ({type(exc).__name__})'
 print(f'Python: {sys.version.split()[0]}'); print(f'Flutter: {version("flutter")}'); print(f'Dart: {version("dart")}'); print(f'Git: {version("git")}')
 configured = bool(s.api_key) if s.provider != 'mock' and s.mode not in ('mock','dry-run') else True
 print(f'LLM provider: {s.provider} | model: {s.model} | configured: {"yes" if configured else "no"}'); print(f'Factory mode: {s.mode}')
 print(f'Database backend: {"PostgreSQL" if s.database_url else "SQLite"}'); print(f'Database path: {s.db_path} | exists={s.db_path.exists()}'); print(f'Workspace root: {s.workspaces_root} | exists={s.workspaces_root.exists()}')
 if s.provider != 'mock' and s.mode not in ('mock','dry-run') and not s.api_key: print('LLM configuration error: AI_API_KEY is not configured.')
@app.command('ai-smoke')
def ai_smoke():
 s=get_settings()
 if s.mode in ('mock','dry-run') or s.provider == 'mock': typer.echo(f'Provider: {s.provider} | model: {s.model} | configured: yes | mock: yes'); typer.echo('Smoke test skipped network: Mock provider is active.'); return
 if not s.api_key: raise typer.BadParameter('AI_API_KEY is not configured for the selected real provider')
 from factory.providers.registry import build_provider
 provider=build_provider(s); schema={'type':'object','properties':{'ok':{'type':'boolean'},'message':{'type':'string'}},'required':['ok','message']}
 try:
  result=provider.generate_json('Return a minimal smoke-test response.', 'Reply with ok=true and a short message.', schema, timeout=s.ai_timeout)
  typer.echo(f'Provider: {s.provider} | model: {s.model} | configured: yes | structured: yes'); typer.echo('Connection: OK'); typer.echo(f"Structured response valid: {bool(result.get('ok') is True and isinstance(result.get('message'), str))}")
 except Exception as e:
  typer.echo(f'Provider: {s.provider} | model: {s.model} | configured: yes'); typer.echo(f'Connection: FAILED | {type(e).__name__}: {str(e).replace(s.api_key or "", "[REDACTED]")}'); raise typer.Exit(code=1)
@app.command('self-test')
def self_test():
 from factory.self_test import run_self_test
 try:
  results=run_self_test()
  for name,result in results.items(): typer.echo(f'{name}: {result}')
  typer.echo('SELF-TEST: PASS')
 except Exception as exc:
  typer.echo(f'SELF-TEST: FAIL | {type(exc).__name__}: {exc}')
  raise typer.Exit(code=1)
@app.command('telegram')
def telegram():
 import threading
 from factory.integrations.telegram.bot import TelegramBot
 from factory.integrations.telegram.service import TelegramService
 from factory.server import build_worker
 s=get_settings(); s.ensure_directories(); db=build_database(s); service=TelegramService(db,s); _,_,worker=build_worker()
 worker_thread=threading.Thread(target=worker.run_forever,name='factory-worker',daemon=True); worker_thread.start()
 try: TelegramBot(service,s).run()
 finally: worker.stop(); worker_thread.join(timeout=10)
@app.command('dashboard')
def dashboard():
 from factory.dashboard import run_dashboard
 s=get_settings(); run_dashboard(port=s.dashboard_port)
@app.command('worker')
def worker():
 from factory.server import run_worker
 run_worker()
@app.command('health')
def health():
 s=get_settings(); s.ensure_directories(); db=build_database(s)
 from datetime import datetime, timezone
 def alive(name, max_age=30):
  hb=db.get_heartbeat(name)
  if not hb:return False
  try:return (datetime.now(timezone.utc)-datetime.fromisoformat(hb[0]).astimezone(timezone.utc)).total_seconds()<=max_age and json.loads(hb[1]).get('status')=='running'
  except Exception:return False
 ai=svc().provider_info()
 typer.echo(f'Telegram: {"OK" if alive("telegram") else ("NOT CONFIGURED" if not s.telegram_enabled else "DOWN/NOT REPORTED")}')
 for wt in ('python','node','java','flutter'):typer.echo(f'{wt.title()} Environment: {"OK" if alive(f"worker:{wt}") else "NOT REQUIRED/NOT REPORTED"}')
 backend='PostgreSQL' if s.database_url else 'SQLite'
 typer.echo(f'Database: OK | backend={backend}'); typer.echo(f'Queue: OK | pending={db.queue_count()}'); typer.echo(f'AI Provider: {"OK" if ai["configured"] else "NOT CONFIGURED"} | {ai["provider"]}/{ai["model"]}')
if __name__=='__main__':app()
