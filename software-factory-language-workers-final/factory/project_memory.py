from __future__ import annotations
from pathlib import Path
import json

def update_project_memory(workspace: str, project_id: str, state: str, summary: str, facts: list[str]=()):
    p=Path(workspace)/"PROJECT_MEMORY.json"; current={}
    if p.exists():
        try: current=json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    current.update({"project_id":project_id,"last_state":state,"last_summary":summary})
    current["facts"]=list(dict.fromkeys((current.get("facts",[])+list(facts))[-500:]))
    p.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding="utf-8")
    return current

def read_project_memory(workspace: str) -> dict:
    p=Path(workspace)/"PROJECT_MEMORY.json"
    if not p.exists(): return {}
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {}
