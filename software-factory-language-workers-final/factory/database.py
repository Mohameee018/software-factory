from __future__ import annotations
import sqlite3,json
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from pathlib import Path
from factory.models import Project,Task,AgentResult,TestResult,ReviewFinding,ApprovalRequest,WorkflowEvent,FactoryState,ProjectStatus,WorkflowState,new_id,now
SCHEMA="""
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT,project_type TEXT,current_state TEXT,created_at TEXT,updated_at TEXT,data_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,status TEXT,priority TEXT,created_at TEXT,updated_at TEXT,data_json TEXT NOT NULL,FOREIGN KEY(project_id) REFERENCES projects(id));
CREATE TABLE IF NOT EXISTS agent_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT,agent_name TEXT,success INTEGER,timestamp TEXT,data_json TEXT);
CREATE TABLE IF NOT EXISTS test_runs(id TEXT PRIMARY KEY,project_id TEXT,kind TEXT,exit_code INTEGER,passed INTEGER,timestamp TEXT,data_json TEXT);
CREATE TABLE IF NOT EXISTS review_findings(id TEXT PRIMARY KEY,project_id TEXT,severity TEXT,status TEXT,data_json TEXT);
CREATE TABLE IF NOT EXISTS security_findings(id TEXT PRIMARY KEY,project_id TEXT,severity TEXT,status TEXT,data_json TEXT);
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,project_id TEXT,task_id TEXT,status TEXT,created_at TEXT,data_json TEXT);
CREATE TABLE IF NOT EXISTS workflow_events(id TEXT PRIMARY KEY,project_id TEXT,event_type TEXT,state TEXT,task_id TEXT,timestamp TEXT,data_json TEXT);
CREATE TABLE IF NOT EXISTS artifacts(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT,path TEXT,kind TEXT,created_at TEXT,data_json TEXT);
CREATE TABLE IF NOT EXISTS human_feedback(id TEXT PRIMARY KEY,project_id TEXT,feedback TEXT,created_at TEXT,data_json TEXT);
CREATE TABLE IF NOT EXISTS factory_states(project_id TEXT PRIMARY KEY,state_json TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,task_id TEXT,status TEXT NOT NULL,priority INTEGER NOT NULL,created_at TEXT NOT NULL,started_at TEXT,completed_at TEXT,retry_count INTEGER NOT NULL DEFAULT 0,last_error TEXT,worker_state TEXT,worker_id TEXT,lease_until TEXT,worker_type TEXT NOT NULL DEFAULT 'generic',resume_at TEXT,FOREIGN KEY(project_id) REFERENCES projects(id));
CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status,priority,created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_events_project_time ON workflow_events(project_id,timestamp);
CREATE INDEX IF NOT EXISTS idx_artifacts_project_path ON artifacts(project_id,path);
CREATE INDEX IF NOT EXISTS idx_agent_runs_project_time ON agent_runs(project_id,timestamp);
CREATE TABLE IF NOT EXISTS telegram_sessions(user_id INTEGER PRIMARY KEY,active_project_id TEXT,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS telegram_chats(chat_id INTEGER PRIMARY KEY,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS service_heartbeats(service TEXT PRIMARY KEY,updated_at TEXT NOT NULL,details_json TEXT NOT NULL);

"""
class Database:
 def __init__(self,path): self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.init()
 @contextmanager
 def conn(self):
  c=sqlite3.connect(self.path, timeout=30); c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=30000'); c.execute('PRAGMA journal_mode=WAL')
  try:yield c;c.commit()
  finally:c.close()
 def init(self):
  with self.conn() as c:
   c.executescript(SCHEMA)
   cols={r[1] for r in c.execute('PRAGMA table_info(jobs)')}
   if 'worker_type' not in cols: c.execute("ALTER TABLE jobs ADD COLUMN worker_type TEXT NOT NULL DEFAULT 'generic'")
   if 'resume_at' not in cols: c.execute("ALTER TABLE jobs ADD COLUMN resume_at TEXT")
 def heartbeat(self, service, details=None):
  with self.conn() as c:c.execute("INSERT INTO service_heartbeats VALUES(?,?,?) ON CONFLICT(service) DO UPDATE SET updated_at=excluded.updated_at,details_json=excluded.details_json",(service,now().isoformat(),json.dumps(details or {})))
 def get_heartbeat(self, service):
  with self.conn() as c:return c.execute("SELECT updated_at,details_json FROM service_heartbeats WHERE service=?",(service,)).fetchone()
 def set_active_project(self,user_id,project_id):
  with self.conn() as c:c.execute("INSERT INTO telegram_sessions VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET active_project_id=excluded.active_project_id,updated_at=excluded.updated_at",(user_id,project_id,now().isoformat()))
 def get_active_project(self,user_id):
  with self.conn() as c:r=c.execute("SELECT active_project_id FROM telegram_sessions WHERE user_id=?",(user_id,)).fetchone()
  return r[0] if r else None
 def register_telegram_chat(self,chat_id):
  with self.conn() as c:c.execute("INSERT INTO telegram_chats(chat_id,updated_at) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET updated_at=excluded.updated_at",(chat_id,now().isoformat()))
 def list_telegram_chats(self):
  with self.conn() as c:return [r[0] for r in c.execute("SELECT chat_id FROM telegram_chats ORDER BY updated_at DESC").fetchall()]
 def enqueue_job(self,project_id,task_id=None,priority=50,worker_type=None):
  jid=new_id('job'); ts=now().isoformat()
  if worker_type is None:
   row=self.get_project(project_id); worker_type = row.project_type.value if row else 'generic'
  with self.conn() as c:c.execute("INSERT INTO jobs(id,project_id,task_id,status,priority,created_at,started_at,completed_at,retry_count,last_error,worker_state,worker_id,lease_until,worker_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,project_id,task_id,'PENDING',priority,ts,None,None,0,None,None,None,None,worker_type))
  return jid
 def reclaim_expired_jobs(self):
  with self.conn() as c:
   ts=now().isoformat()
   c.execute("UPDATE jobs SET status='RETRYING',worker_state='lease_expired',worker_id=NULL,lease_until=NULL,last_error=? WHERE status='RUNNING' AND lease_until IS NOT NULL AND lease_until<=?",("Worker lease expired; job returned to queue.",ts))
   return c.rowcount

 def extend_job_lease(self,job_id,worker_id,minutes=30):
  lease=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat()
  with self.conn() as c:
   r=c.execute("UPDATE jobs SET lease_until=?,worker_state='running' WHERE id=? AND status='RUNNING' AND worker_id=?",(lease,job_id,worker_id))
   return r.rowcount==1

 def claim_job(self,worker_id,worker_type='generic'):
  self.reclaim_expired_jobs()
  with self.conn() as c:
   c.execute('BEGIN IMMEDIATE')

   # Only one active worker may advance a project at a time. This keeps
   # Telegram retries, queue workers and future horizontal workers from
   # mutating the same project concurrently.
   if worker_type == 'generic':
    row=c.execute("SELECT j.id FROM jobs j WHERE (j.status IN ('PENDING','RETRYING') OR (j.status='WAITING_QUOTA' AND j.resume_at IS NOT NULL AND julianday(j.resume_at)<=julianday(?))) AND NOT EXISTS (SELECT 1 FROM jobs r WHERE r.project_id=j.project_id AND r.status='RUNNING') ORDER BY (j.priority + CAST((julianday(?) - julianday(j.created_at))*10 AS INTEGER)) DESC,j.created_at LIMIT 1",(now().isoformat(),now().isoformat())).fetchone()
   else:
    row=c.execute("SELECT j.id FROM jobs j WHERE (j.status IN ('PENDING','RETRYING') OR (j.status='WAITING_QUOTA' AND j.resume_at IS NOT NULL AND j.resume_at<=?)) AND j.worker_type=? AND NOT EXISTS (SELECT 1 FROM jobs r WHERE r.project_id=j.project_id AND r.status='RUNNING') ORDER BY (j.priority + CAST((julianday(?) - julianday(j.created_at))*10 AS INTEGER)) DESC,j.created_at LIMIT 1",(now().isoformat(),worker_type,now().isoformat())).fetchone()
   if not row:return None
   jid=row[0]; ts=now().isoformat(); lease=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
   c.execute("UPDATE jobs SET status='RUNNING',started_at=COALESCE(started_at,?),worker_id=?,lease_until=?,worker_state='running',resume_at=NULL WHERE id=? AND (status IN ('PENDING','RETRYING') OR status='WAITING_QUOTA')",(ts,worker_id,lease,jid))
   r=c.execute("SELECT id,project_id,task_id,status,priority,created_at,started_at,completed_at,retry_count,last_error,worker_state,worker_type FROM jobs WHERE id=?",(jid,)).fetchone()
  from factory.queue import Job
  return Job(*r) if r else None
 def update_job(self,job_id,status,**fields):
  allowed={'started_at','completed_at','retry_count','last_error','worker_state','worker_id','lease_until','resume_at'}; sets=['status=?']; vals=[status]
  for k,v in fields.items():
   if k in allowed: sets.append(k+'=?'); vals.append(v)
  vals.append(job_id)
  with self.conn() as c:c.execute('UPDATE jobs SET '+','.join(sets)+' WHERE id=?',vals)
 def retry_job(self,job_id,error,max_retries=5):
  with self.conn() as c:
   row=c.execute('SELECT retry_count FROM jobs WHERE id=?',(job_id,)).fetchone()
   count=(row[0] if row else 0)+1
   status='FAILED' if count >= max_retries else 'RETRYING'
   c.execute("UPDATE jobs SET status=?,retry_count=?,last_error=?,worker_state=?,completed_at=?,lease_until=NULL WHERE id=?",(status,count,error,status,now().isoformat() if status=='FAILED' else None,job_id))
 def cancel_pending_jobs(self,project_id):
  with self.conn() as c:c.execute("UPDATE jobs SET status='CANCELLED',completed_at=?,worker_state='cancelled' WHERE project_id=? AND status IN ('PENDING','RETRYING','WAITING_APPROVAL')",(now().isoformat(),project_id))
 def queue_count(self,worker_type=None):
  with self.conn() as c:
   if worker_type and worker_type != 'generic': return c.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('PENDING','RETRYING') AND worker_type=?",(worker_type,)).fetchone()[0]
   return c.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('PENDING','RETRYING')").fetchone()[0]
 def list_jobs(self,project_id=None,limit=100):
  q="SELECT id,project_id,task_id,status,priority,created_at,started_at,completed_at,retry_count,last_error,worker_state,worker_type FROM jobs"; args=[]
  if project_id:q+=' WHERE project_id=?';args.append(project_id)
  q+=' ORDER BY created_at DESC LIMIT ?';args.append(limit)
  with self.conn() as c:return c.execute(q,args).fetchall()
 def recover_jobs(self):
  with self.conn() as c:
   c.execute("UPDATE jobs SET status='RETRYING',worker_state='recovered',worker_id=NULL,lease_until=NULL WHERE status='RUNNING'")
   c.execute("UPDATE jobs SET status='PENDING',worker_state='recovered',worker_id=NULL,lease_until=NULL WHERE status='RETRYING' AND retry_count=0")
   c.execute("UPDATE jobs SET worker_state='waiting_approval' WHERE status='WAITING_APPROVAL'")
 def has_pending_approval(self,project_id):
  with self.conn() as c:return bool(c.execute("SELECT 1 FROM approvals WHERE project_id=? AND status='PENDING' LIMIT 1",(project_id,)).fetchone())
 def log_job_event(self,project_id,job_id,event_type,error):
  self.event(WorkflowEvent(project_id=project_id,event_type=event_type,details={'job_id':job_id,'error':error}))
 def save(self,table,obj,extra=()):
  with self.conn() as c:
   if table=='projects':c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,project_type=excluded.project_type,current_state=excluded.current_state,updated_at=excluded.updated_at,data_json=excluded.data_json',(obj.id,obj.name,obj.project_type.value,obj.current_state.value,obj.created_at.isoformat(),obj.updated_at.isoformat(),obj.model_dump_json()))
   elif table=='tasks':c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,priority=excluded.priority,updated_at=excluded.updated_at,data_json=excluded.data_json',(obj.id,obj.project_id,obj.status.value,obj.priority.value,obj.created_at.isoformat(),obj.updated_at.isoformat(),obj.model_dump_json()))
 def save_project(self,p):
  if p.status != ProjectStatus.CREATED:
   try:p.current_state=WorkflowState(p.status.value)
   except ValueError:pass
  self.save('projects',p)
 def get_project(self,i):
  with self.conn() as c:r=c.execute('SELECT data_json FROM projects WHERE id=?',(i,)).fetchone()
  return Project.model_validate_json(r[0]) if r else None
 def list_projects(self):
  with self.conn() as c:rs=c.execute('SELECT data_json FROM projects ORDER BY created_at DESC').fetchall()
  return [Project.model_validate_json(r[0]) for r in rs]
 def save_task(self,t):self.save('tasks',t)
 def get_task(self,i):
  with self.conn() as c:r=c.execute('SELECT data_json FROM tasks WHERE id=?',(i,)).fetchone()
  return Task.model_validate_json(r[0]) if r else None
 def list_tasks_for_project(self,pid):
  return self.list_tasks(pid)
 def list_tasks(self,pid):
  with self.conn() as c:rs=c.execute('SELECT data_json FROM tasks WHERE project_id=? ORDER BY created_at',(pid,)).fetchall()
  return [Task.model_validate_json(r[0]) for r in rs]
 def save_state(self,s):
  with self.conn() as c:c.execute('INSERT INTO factory_states VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at',(s.project_id,s.model_dump_json(),s.timestamps.get('updated_at','')))
 def get_state(self,pid):
  with self.conn() as c:r=c.execute('SELECT state_json FROM factory_states WHERE project_id=?',(pid,)).fetchone()
  return FactoryState.model_validate_json(r[0]) if r else None
 def agent_result(self,pid,r):
  with self.conn() as c:c.execute('INSERT INTO agent_runs(project_id,agent_name,success,timestamp,data_json) VALUES(?,?,?,?,?)',(pid,r.agent_name,int(r.success),r.timestamp.isoformat(),r.model_dump_json()))
 def test_result(self,r):
  with self.conn() as c:c.execute('INSERT INTO test_runs VALUES(?,?,?,?,?,?,?)',(r.id,r.project_id,r.kind,r.exit_code,int(r.passed),r.timestamp.isoformat(),r.model_dump_json()))
 def finding(self,pid,f,security=False):
  with self.conn() as c:c.execute('INSERT OR REPLACE INTO '+('security_findings' if security else 'review_findings')+' VALUES(?,?,?,?,?)',(f.id,pid,f.severity.value,f.status,f.model_dump_json()))
 def approval(self,a):
  with self.conn() as c:c.execute('INSERT OR REPLACE INTO approvals VALUES(?,?,?,?,?,?)',(a.id,a.project_id,a.task_id,a.status.value,a.created_at.isoformat(),a.model_dump_json()))
 def event(self,e):
  with self.conn() as c:c.execute('INSERT INTO workflow_events VALUES(?,?,?,?,?,?,?)',(e.id,e.project_id,e.event_type,e.state,e.task_id,e.timestamp.isoformat(),e.model_dump_json()))

 def list_approvals(self,project_id=None):
  q="SELECT data_json FROM approvals"; args=()
  if project_id: q += " WHERE project_id=?"; args=(project_id,)
  with self.conn() as c: rs=c.execute(q+" ORDER BY created_at DESC",args).fetchall()
  return [ApprovalRequest.model_validate_json(r[0]) for r in rs]
 def get_approval(self,approval_id):
  with self.conn() as c:r=c.execute("SELECT data_json FROM approvals WHERE id=?",(approval_id,)).fetchone()
  return ApprovalRequest.model_validate_json(r[0]) if r else None
 def list_events(self,project_id=None,limit=100):
  q="SELECT data_json FROM workflow_events"; args=()
  if project_id:q += " WHERE project_id=?";args=(project_id,)
  with self.conn() as c:rs=c.execute(q+" ORDER BY timestamp DESC LIMIT ?",args+(limit,)).fetchall()
  return [WorkflowEvent.model_validate_json(r[0]) for r in rs]

 def feedback(self,pid,feedback):
  from factory.models import new_id,now
  fid=new_id('fb'); payload=json.dumps({'id':fid,'project_id':pid,'feedback':feedback,'created_at':now().isoformat()})
  with self.conn() as c:c.execute('INSERT INTO human_feedback VALUES(?,?,?,?,?)',(fid,pid,feedback,now().isoformat(),payload))
  return fid
 def artifact(self,pid,path,kind):
  with self.conn() as c:c.execute('INSERT INTO artifacts(project_id,path,kind,created_at,data_json) VALUES(?,?,?,?,?)',(pid,path,kind,__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),json.dumps({'path':path,'kind':kind})))
