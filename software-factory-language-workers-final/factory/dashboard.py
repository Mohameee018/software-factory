from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from factory.config import get_settings
from factory.database import Database
def snapshot(db):
    rows=[]
    for p in db.list_projects():
        tasks=db.list_tasks(p.id)
        rows.append({'id':p.id,'name':p.name,'state':p.current_state.value,'type':p.project_type.value,'tasks':{'total':len(tasks),'done':sum(t.status.value=='DONE' for t in tasks)},'updated_at':p.updated_at.isoformat()})
    return {'projects':rows,'queue_pending':db.queue_count()}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        db=Database(get_settings().db_path); path=urlparse(self.path).path
        if path=='/api/projects': return self._json(snapshot(db))
        if path=='/health': return self._json({'ok':True,'queue_pending':db.queue_count()})
        if path=='/': return self._html(snapshot(db))
        if path.startswith('/api/projects/'):
            pid=path.rsplit('/',1)[-1]; p=db.get_project(pid)
            if not p:return self.send_error(404)
            tasks=db.list_tasks(pid)
            return self._json({'project':json.loads(p.model_dump_json()),'tasks':[json.loads(t.model_dump_json()) for t in tasks],'jobs':db.list_jobs(pid),'approvals':[json.loads(a.model_dump_json()) for a in db.list_approvals(pid)]})
        self.send_error(404)
    def _json(self,data):
        raw=json.dumps(data,ensure_ascii=False,default=str).encode(); self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def _html(self,data):
        cards=''.join(f"<tr><td>{p['name']}</td><td>{p['state']}</td><td>{p['tasks']['done']}/{p['tasks']['total']}</td><td>{p['type']}</td></tr>" for p in data['projects'])
        raw=f"""<!doctype html><meta charset='utf-8'><title>Software Factory</title><style>body{{font-family:system-ui;margin:32px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border-bottom:1px solid #ddd}}</style><h1>Software Factory</h1><p>Queued jobs: {data['queue_pending']}</p><table><tr><th>Project</th><th>State</th><th>Tasks</th><th>Type</th></tr>{cards}</table>"""
        b=raw.encode(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
def run_dashboard(host='0.0.0.0',port=8080): ThreadingHTTPServer((host,int(port)),Handler).serve_forever()
