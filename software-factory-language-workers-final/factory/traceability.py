from __future__ import annotations
from pathlib import Path
import re
from dataclasses import dataclass

@dataclass
class TraceabilityReport:
    requirements: list[str]
    mapped_requirements: dict[str,list[int]]
    unmapped: list[str]
    task_count: int
    complete: bool

def _sections(text: str) -> list[str]:
    items=[]
    for line in text.splitlines():
        m=re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$",line)
        if m and len(m.group(1).strip())>8: items.append(re.sub(r"\s+"," ",m.group(1).strip()))
    return items

def build_report(workspace: str) -> TraceabilityReport:
    root=Path(workspace); docs=root/"docs"
    source=""
    for name in ("REQUIREMENTS.md","PRD.md","ACCEPTANCE_CRITERIA.md","ARCHITECTURE.md"):
        p=docs/name
        if p.exists(): source += "\n"+p.read_text(encoding="utf-8",errors="ignore")[:30000]
    reqs=_sections(source)
    task_path=docs/"TASKS.md"
    tasks=_sections(task_path.read_text(encoding="utf-8",errors="ignore")) if task_path.exists() else []
    mapped={}
    unmapped=[]
    for i,req in enumerate(reqs,1):
        words={w.lower() for w in re.findall(r"[A-Za-z0-9_]{4,}|[\u0600-\u06ff]{4,}",req)}
        hits=[]
        for ti,task in enumerate(tasks,1):
            tw={w.lower() for w in re.findall(r"[A-Za-z0-9_]{4,}|[\u0600-\u06ff]{4,}",task)}
            if words and len(words & tw) >= max(1,min(3,len(words))):
                hits.append(ti)
        mapped[str(i)]=hits
        if not hits: unmapped.append(req)
    return TraceabilityReport(reqs,mapped,unmapped,len(tasks),bool(reqs) and bool(tasks) and not unmapped)

def write_report(workspace: str) -> TraceabilityReport:
    r=build_report(workspace); p=Path(workspace)/"docs"/"TRACEABILITY.md"; p.parent.mkdir(parents=True,exist_ok=True)
    lines=["# Requirement Traceability","","Every material requirement must map to at least one executable task.","",
           f"- Requirements detected: {len(r.requirements)}","- Tasks detected: {r.task_count}","- Status: {'COMPLETE' if r.complete else 'INCOMPLETE'}","",
           "## Mapping"]
    for i,req in enumerate(r.requirements,1):
        lines.append(f"- R{i}: {req} → "+(", ".join(f"T{x}" for x in r.mapped_requirements[str(i)]) or "UNMAPPED"))
    if r.unmapped:
        lines += ["","## Unmapped requirements"]+[f"- {x}" for x in r.unmapped]
    p.write_text("\n".join(lines)+"\n",encoding="utf-8")
    return r
