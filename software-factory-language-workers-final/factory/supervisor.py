from __future__ import annotations
import json, os, threading, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from factory.models import WorkflowEvent

class FactorySupervisor:
    """Always-on control layer for the factory."""
    AUDIT_SCHEMA = {
        "type":"object",
        "properties":{
            "health":{"type":"string"},"communication":{"type":"string"},
            "intelligence":{"type":"string"},"skills":{"type":"string"},
            "reliability":{"type":"string"},"findings":{"type":"array"},
            "improvements":{"type":"array"},"priority_actions":{"type":"array"},
            "summary":{"type":"string"},
        },
        "required":["health","communication","intelligence","skills","reliability",
                    "findings","improvements","priority_actions","summary"],
    }
    def __init__(self, service, worker):
        self.service=service; self.worker=worker; self.db=service.db; self.settings=service.settings
        self._stop=threading.Event(); self._thread=None; self._last_audit_date=None; self._last_recovery=0.0
    @property
    def root(self):
        p=Path(self.settings.workspaces_root)/".factory"; p.mkdir(parents=True,exist_ok=True); return p
    @property
    def learning_path(self): return self.root/"FACTORY_LEARNING.md"
    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._thread=threading.Thread(target=self._run,name="factory-supervisor",daemon=True); self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread: self._thread.join(timeout=10)
    def _run(self):
        self.db.heartbeat("supervisor",{"status":"running"})
        while not self._stop.wait(30):
            try:
                self.db.heartbeat("supervisor",{"status":"running","last_check":datetime.now(timezone.utc).isoformat(),"last_audit":self._last_audit_date})
                self._recover_stale_jobs(); self._daily_audit_if_due()
            except Exception as exc:
                self.db.heartbeat("supervisor",{"status":"degraded","error":f"{type(exc).__name__}: {str(exc)[:500]}"})
        self.db.heartbeat("supervisor",{"status":"stopped"})
    def _recover_stale_jobs(self):
        if time.monotonic()-self._last_recovery<300: return
        self._last_recovery=time.monotonic()
        try: self.db.reclaim_expired_jobs()
        except Exception: pass
    def _audit_hour(self):
        try: return max(0,min(23,int(os.getenv("FACTORY_AUDIT_HOUR","9"))))
        except Exception: return 9
    def _daily_audit_if_due(self):
        try: tz=ZoneInfo(os.getenv("FACTORY_AUDIT_TIMEZONE","Africa/Cairo"))
        except Exception: tz=timezone.utc
        now=datetime.now(tz); key=now.date().isoformat()
        if self._last_audit_date==key or now.hour<self._audit_hour(): return
        self._last_audit_date=key; self.run_audit()
    def _snapshot(self):
        projects=[]
        for p in self.db.list_projects()[:30]:
            state=self.db.get_state(p.id); tasks=self.db.list_tasks(p.id)
            projects.append({"id":p.id,"name":p.name,"type":p.project_type.value,"state":p.current_state.value,
                             "tasks":len(tasks),"open_tasks":sum(1 for t in tasks if t.status.value!="DONE"),
                             "last_agent":state.timestamps.get("last_agent") if state else None,
                             "iteration":state.iteration_count if state else 0})
        heartbeats={}
        for name in ("telegram","supervisor","worker:generic","worker:python","worker:node","worker:java","worker:flutter"):
            try:
                hb=self.db.get_heartbeat(name)
                if hb: heartbeats[name]={"updated_at":hb[0],"details":json.loads(hb[1])}
            except Exception: pass
        events=self.db.list_events(limit=40)
        learning=self.learning_path.read_text(encoding="utf-8",errors="ignore")[-12000:] if self.learning_path.exists() else ""
        return {"projects":projects,"queue_pending":self.db.queue_count(),"heartbeats":heartbeats,
                "recent_events":[{"type":e.event_type,"project_id":e.project_id,"state":e.state,"details":e.details,"timestamp":e.timestamp.isoformat()} for e in events],
                "learning":learning}
    def run_audit(self):
        snapshot=self._snapshot()
        instructions=("You are the senior operations and intelligence supervisor of an autonomous software factory. "
                       "Audit the factory itself, not a single project. Inspect health, reliability, AI quality, agent skills, "
                       "owner communication, memory, and recurring failure patterns. Identify concrete improvements that make "
                       "the factory understand the owner faster, produce better software, recover from failures, and work unattended. "
                       "Never invent evidence. Separate observed facts from recommendations. Do not expose secrets. "
                       "Recommendations must be actionable and safe; do not silently change security or destructive-operation policies.")
        provider=self.service.model_router.for_role("auditor")
        try:
            data=provider.generate_json(instructions,json.dumps(snapshot,ensure_ascii=False),self.AUDIT_SCHEMA,timeout=min(self.settings.ai_timeout,90))
        except Exception as exc:
            data={"health":"Audit provider unavailable.","communication":"No fresh audit was delivered.",
                  "intelligence":"Unknown.","skills":"Unknown.","reliability":"Unknown.",
                  "findings":[f"Daily audit failed: {type(exc).__name__}: {str(exc)[:700]}"],
                  "improvements":["Restore AI provider/failover availability."],
                  "priority_actions":["Check AI quota and provider health."],
                  "summary":"The daily supervisor audit could not complete."}
        self._write_audit(data,snapshot); self._update_learning(data); self._notify(data)
        pid=self._event_project_id()
        if pid:
            try: self.db.event(WorkflowEvent(project_id=pid,event_type="FACTORY_DAILY_AUDIT",
                details={"summary":str(data.get("summary",""))[:2000],"findings":data.get("findings",[])[:10],"improvements":data.get("improvements",[])[:10]}))
            except Exception: pass
        return True
    def _event_project_id(self):
        ps=self.db.list_projects(); return ps[0].id if ps else ""
    def _write_audit(self,data,snapshot):
        stamp=datetime.now(timezone.utc).strftime("%Y-%m-%d"); path=self.root/f"FACTORY_AUDIT_{stamp}.md"
        lines=[f"# Factory Daily Audit — {stamp}","","## Summary",str(data.get("summary","")),
               "","## Health",str(data.get("health","")),"","## Communication",str(data.get("communication","")),
               "","## Intelligence",str(data.get("intelligence","")),"","## Skills",str(data.get("skills","")),
               "","## Reliability",str(data.get("reliability","")),"","## Findings"]
        lines += [f"- {x}" for x in data.get("findings",[])]
        lines += ["","## Recommended Improvements"]+[f"- {x}" for x in data.get("improvements",[])]
        lines += ["","## Priority Actions"]+[f"- {x}" for x in data.get("priority_actions",[])]
        lines += ["","## Snapshot",json.dumps(snapshot,ensure_ascii=False,indent=2)[:30000]]
        path.write_text("\n".join(lines)+"\n",encoding="utf-8")
    def _update_learning(self,data):
        existing=self.learning_path.read_text(encoding="utf-8",errors="ignore") if self.learning_path.exists() else ""
        stamp=datetime.now(timezone.utc).strftime("%Y-%m-%d")
        additions=[f"\n## Learning — {stamp}",f"- Summary: {data.get('summary','')}"]+[f"- Improvement: {x}" for x in data.get("improvements",[])[:10]]
        self.learning_path.write_text((existing+"\n"+"\n".join(additions)).strip()[-50000:]+"\n",encoding="utf-8")
    def _notify(self,data):
        notifier=getattr(self.service,"notifier",None)
        if not notifier: return
        lines=["🧠 <b>FACTORY DAILY AUDIT</b>","",f"📊 <b>الخلاصة:</b> {str(data.get('summary',''))[:1200]}"]
        findings=data.get("findings",[])[:5]; improvements=data.get("improvements",[])[:5]
        if findings: lines += ["","🔎 <b>ملاحظات:</b>"]+[f"• {str(x)[:500]}" for x in findings]
        if improvements: lines += ["","🚀 <b>اقتراحات التطوير:</b>"]+[f"• {str(x)[:500]}" for x in improvements]
        lines += ["","📄 التقرير الكامل محفوظ داخل <code>.factory/FACTORY_AUDIT_YYYY-MM-DD.md</code>"]
        notifier._send("\n".join(lines))
