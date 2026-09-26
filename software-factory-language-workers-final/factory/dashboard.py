from __future__ import annotations

import hmac
import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from factory.config import get_settings
from factory.storage import build_database


def _workers(db):
    rows=[]
    for worker_type in ('generic','python','node','java','flutter'):
        hb=db.get_heartbeat(f'worker:{worker_type}')
        rows.append({'type':worker_type,'heartbeat':hb[0] if hb else None,'details':json.loads(hb[1]) if hb else None})
    return rows

def snapshot(db):
    rows = []
    for p in db.list_projects():
        tasks = db.list_tasks(p.id)
        rows.append({
            "id": p.id,
            "name": p.name,
            "state": p.current_state.value,
            "type": p.project_type.value,
            "tasks": {
                "total": len(tasks),
                "done": sum(t.status.value == "DONE" for t in tasks),
            },
            "updated_at": p.updated_at.isoformat(),
        })
    return {"projects": rows, "queue_pending": db.queue_count(), "workers": _workers(db)}


class Handler(BaseHTTPRequestHandler):
    def _authorized(self):
        expected = get_settings().dashboard_token
        if not expected:
            return True
        supplied = self.headers.get("Authorization", "")
        if supplied.startswith("Bearer "):
            supplied = supplied[7:]
        return bool(supplied) and hmac.compare_digest(supplied, expected)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            db = build_database(get_settings())
            return self._json({"ok": True, "queue_pending": db.queue_count()})
        if not self._authorized():
            self.send_response(401)
            self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            return

        db = build_database(get_settings())
        if path == "/api/projects":
            return self._json(snapshot(db))
        if path == "/":
            return self._html(snapshot(db))
        if path.startswith("/api/projects/"):
            pid = path.rsplit("/", 1)[-1]
            project = db.get_project(pid)
            if not project:
                return self.send_error(404)
            tasks = db.list_tasks(pid)
            return self._json({
                "project": json.loads(project.model_dump_json()),
                "tasks": [json.loads(t.model_dump_json()) for t in tasks],
                "jobs": db.list_jobs(pid),
                "approvals": [json.loads(a.model_dump_json()) for a in db.list_approvals(pid)],
            })
        self.send_error(404)

    def _json(self, data):
        raw = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _html(self, data):
        cards = "".join(
            f"<tr><td>{escape(str(p['name']))}</td>"
            f"<td>{escape(str(p['state']))}</td>"
            f"<td>{p['tasks']['done']}/{p['tasks']['total']}</td>"
            f"<td>{escape(str(p['type']))}</td></tr>"
            for p in data["projects"]
        )
        raw = (
            "<!doctype html><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Software Factory</title>"
            "<style>body{font-family:system-ui;margin:32px}table{border-collapse:collapse;width:100%}"
            "td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}</style>"
            "<h1>Software Factory</h1>"
            f"<p>Queued jobs: {data['queue_pending']}</p>"
            "<table><tr><th>Project</th><th>State</th><th>Tasks</th><th>Type</th></tr>"
            f"{cards}</table>"
        )
        body = raw.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_dashboard(host="0.0.0.0", port=8080):
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()
