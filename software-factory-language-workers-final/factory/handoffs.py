from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json, uuid

@dataclass
class Handoff:
    id: str
    project_id: str
    from_role: str
    to_role: str
    purpose: str
    inputs: list[str]
    outputs: list[str]
    acceptance_checks: list[str]
    status: str = "PENDING"
    created_at: str = ""

    def to_dict(self):
        return self.__dict__.copy()

def create_handoff(workspace: str, project_id: str, from_role: str, to_role: str,
                   purpose: str, inputs: list[str], outputs: list[str],
                   acceptance_checks: list[str]) -> Handoff:
    h=Handoff(str(uuid.uuid4()),project_id,from_role,to_role,purpose,inputs,outputs,acceptance_checks,
              "PENDING",datetime.now(timezone.utc).isoformat())
    p=Path(workspace)/"handoffs.jsonl"; p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("a",encoding="utf-8") as f: f.write(json.dumps(h.to_dict(),ensure_ascii=False)+"\n")
    return h

def list_handoffs(workspace: str) -> list[dict]:
    p=Path(workspace)/"handoffs.jsonl"
    if not p.exists(): return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
