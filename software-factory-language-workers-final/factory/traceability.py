from __future__ import annotations
from pathlib import Path
import re
from dataclasses import dataclass

_ID_RE=re.compile(r'\b(?:RQ|BR|AC|ARCH|T|TEST|REV|SEC|UX)-\d{3,}\b',re.I)

@dataclass
class TraceabilityReport:
    requirements:list[str]
    mapped_requirements:dict[str,list[int]]
    unmapped:list[str]
    task_count:int
    complete:bool

def _items(text:str)->list[str]:
    items=[]
    for line in text.splitlines():
        m=re.match(r'^\s*(?:[-*]|\d+[.)])\s+(.+)$',line)
        if m and len(m.group(1).strip())>8:
            items.append(re.sub(r'\s+',' ',m.group(1).strip()))
    return items

def _id_items(text:str,prefix:str)->list[tuple[str,str]]:
    out=[]
    for line in text.splitlines():
        ids=re.findall(rf'\b{prefix}-\d{{3,}}\b',line,re.I)
        if ids:
            for ident in ids:
                cleaned=re.sub(r'^\s*(?:[-*]|\d+[.)])\s*','',line).strip()
                out.append((ident.upper(),cleaned))
    return out

def _stable_requirements(docs:Path)->list[tuple[str,str]]:
    # Prefer explicit IDs supplied by the Requirements/BA stage.
    explicit=[]
    for name,prefix in (('REQUIREMENTS.md','RQ'),('PRD.md','RQ')):
        p=docs/name
        if p.exists(): explicit.extend(_id_items(p.read_text(encoding='utf-8',errors='ignore'),prefix))
    if explicit:
        seen=set(); return [(i,t) for i,t in explicit if not (i in seen or seen.add(i))]
    # Backward-compatible deterministic IDs for older projects.
    raw=[]
    for name in ('REQUIREMENTS.md','PRD.md'):
        p=docs/name
        if p.exists(): raw.extend(_items(p.read_text(encoding='utf-8',errors='ignore')))
    seen=set(); raw=[x for x in raw if not (x in seen or seen.add(x))]
    return [(f'RQ-{i:03d}',x) for i,x in enumerate(raw,1)]

def _task_ids(docs:Path)->list[tuple[str,str]]:
    p=docs/'TASKS.md'
    if not p.exists(): return []
    explicit=_id_items(p.read_text(encoding='utf-8',errors='ignore'),'T')
    if explicit: return explicit
    return [(f'T-{i:03d}',x) for i,x in enumerate(_items(p.read_text(encoding='utf-8',errors='ignore')),1)]

def _tokens(text:str)->set[str]:
    return {w.lower() for w in re.findall(r'[A-Za-z0-9_]{4,}|[\u0600-\u06ff]{4,}',text)}

def build_report(workspace:str)->TraceabilityReport:
    root=Path(workspace); docs=root/'docs'
    reqs=_stable_requirements(docs); tasks=_task_ids(docs)
    mapped={}; unmapped=[]
    for rid,req in reqs:
        words=_tokens(req); hits=[]
        for ti,(tid,task) in enumerate(tasks,1):
            if words and len(words & _tokens(task)) >= max(1,min(3,len(words))): hits.append(ti)
        mapped[rid]=hits
        if not hits: unmapped.append(f'{rid}: {req}')
    return TraceabilityReport([f'{i}: {t}' for i,t in reqs],mapped,unmapped,len(tasks),bool(reqs) and bool(tasks) and not unmapped)

def write_report(workspace:str)->TraceabilityReport:
    r=build_report(workspace); p=Path(workspace)/'docs'/'TRACEABILITY.md'; p.parent.mkdir(parents=True,exist_ok=True)
    task_lines=_task_ids(Path(workspace)/'docs')
    task_ids=[x[0] for x in task_lines]
    lines=[
        '# Requirement Traceability','',
        'Stable IDs are used so requirements remain traceable across revisions.',
        '',
        f'- Requirements detected: {len(r.requirements)}',
        f'- Tasks detected: {r.task_count}',
        f'- Status: {"COMPLETE" if r.complete else "INCOMPLETE"}','',
        '## Mapping'
    ]
    for rid_req in r.requirements:
        rid,_,req=rid_req.partition(': ')
        hits=r.mapped_requirements.get(rid,[])
        rendered=', '.join(task_ids[x-1] for x in hits if 0<x<=len(task_ids)) or 'UNMAPPED'
        lines.append(f'- {rid}: {req} → {rendered}')
    if r.unmapped:
        lines += ['','## Unmapped requirements']+[f'- {x}' for x in r.unmapped]
    lines += ['','## Lifecycle IDs','',
              '- RQ-* = Requirement','- BR-* = Business Rule','- AC-* = Acceptance Criterion',
              '- ARCH-* = Architecture component','- T-* = Implementation task',
              '- TEST-* = Test evidence','- REV-* = Code review finding',
              '- UX-* = UX review finding','- SEC-* = Security finding']
    p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return r
