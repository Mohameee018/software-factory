from __future__ import annotations
import hmac,json
from html import escape
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from factory.config import get_settings
from factory.storage import build_database
from factory.budget import BudgetManager
WORKER_TYPES=('generic','python','node','java','flutter')
def _workers(db):
 rows=[]
 for worker_type in WORKER_TYPES:
  hb=db.get_heartbeat(f'worker:{worker_type}'); rows.append({'type':worker_type,'heartbeat':hb[0] if hb else None,'details':json.loads(hb[1]) if hb else None})
 hb=db.get_heartbeat('telegram'); rows.append({'type':'telegram','heartbeat':hb[0] if hb else None,'details':json.loads(hb[1]) if hb else None})
 return rows
def snapshot(db):
 rows=[]; budget=BudgetManager(db,get_settings())
 for p in db.list_projects():
  tasks=db.list_tasks(p.id)
  rows.append({'id':p.id,'name':p.name,'state':p.current_state.value,'type':p.project_type.value,'tasks':{'total':len(tasks),'done':sum(t.status.value=='DONE' for t in tasks)},'budget':{'agent_runs':budget.used_agent_runs(p.id),'seconds':budget.project_seconds(p.id)},'updated_at':p.updated_at.isoformat()})
 return {'projects':rows,'queue_pending':db.queue_count(),'workers':_workers(db)}
class Handler(BaseHTTPRequestHandler):
 def _authorized(self):
  expected=get_settings().dashboard_token
  if not expected:return True
  supplied=self.headers.get('Authorization','')
  if supplied.startswith('Bearer '):supplied=supplied[7:]
  return bool(supplied) and hmac.compare_digest(supplied,expected)
 def do_GET(self):
  parsed=urlparse(self.path); path=parsed.path
  if path=='/health':
   db=build_database(get_settings()); return self._json({'ok':True,'database_backend':type(db).__name__,'queue_pending':db.queue_count(),'workers':_workers(db)})
  if not self._authorized():
   self.send_response(401); self.send_header('WWW-Authenticate','Bearer'); self.end_headers(); return
  db=build_database(get_settings())
  if path=='/api/projects':return self._json(snapshot(db))
  if path=='/api/workers':return self._json({'workers':_workers(db)})
  if path=='/api/queue':return self._json({'pending':db.queue_count(),'jobs':db.list_jobs(limit=200)})
  if path=='/api/metrics':
   projects=db.list_projects(); return self._json({'projects':len(projects),'queue_pending':db.queue_count(),'agent_runs':sum(BudgetManager(db,get_settings()).used_agent_runs(p.id) for p in projects),'workers':_workers(db)})
  if path=='/':return self._html(snapshot(db))
  if path.startswith('/api/projects/'):
   parts=[x for x in path.split('/') if x]
   if len(parts)>=3 and parts[2]=='events':
    pid=parts[1]
    if not db.get_project(pid):return self.send_error(404)
    return self._json({'events':[json.loads(e.model_dump_json()) for e in db.list_events(pid,200)]})
   pid=parts[-1]; project=db.get_project(pid)
   if not project:return self.send_error(404)
   tasks=db.list_tasks(pid)
   return self._json({'project':json.loads(project.model_dump_json()),'tasks':[json.loads(t.model_dump_json()) for t in tasks],'jobs':db.list_jobs(pid),'approvals':[json.loads(a.model_dump_json()) for a in db.list_approvals(pid)],'events':[json.loads(e.model_dump_json()) for e in db.list_events(pid,100)]})
  self.send_error(404)
 def _json(self,data):
  raw=json.dumps(data,ensure_ascii=False,default=str).encode(); self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
 def _html(self,data):
  project_rows=''.join(f"<tr><td>{escape(str(p['name']))}</td><td>{escape(str(p['state']))}</td><td>{p['tasks']['done']}/{p['tasks']['total']}</td><td>{escape(str(p['type']))}</td><td>{p['budget']['agent_runs']}</td></tr>" for p in data['projects'])
  worker_rows=''.join(f"<tr><td>{escape(str(w['type']))}</td><td>{escape(str(w['heartbeat'] or 'never'))}</td><td>{escape(str((w['details'] or {}).get('status','unknown')))}</td></tr>" for w in data['workers'])
  raw=("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Software Factory</title><style>body{font-family:system-ui;margin:32px}table{border-collapse:collapse;width:100%;margin-bottom:28px}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}</style><h1>Software Factory</h1><p>Queued jobs: "+str(data['queue_pending'])+"</p><h2>Workers</h2><table><tr><th>Type</th><th>Heartbeat</th><th>Status</th></tr>"+worker_rows+"</table><h2>Projects</h2><table><tr><th>Project</th><th>State</th><th>Tasks</th><th>Type</th><th>Agent runs</th></tr>"+project_rows+"</table>")
  body=raw.encode(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
def run_dashboard(host='0.0.0.0',port=8080):ThreadingHTTPServer((host,int(port)),Handler).serve_forever()
