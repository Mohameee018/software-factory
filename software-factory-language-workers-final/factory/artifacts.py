from __future__ import annotations
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
def _sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
def record_artifacts(workspace,project_id,db,paths):
    root=Path(workspace); manifest=root/'docs'/'ARTIFACT_MANIFEST.json'; manifest.parent.mkdir(parents=True,exist_ok=True)
    current={}
    if manifest.exists():
        try: current=json.loads(manifest.read_text(encoding='utf-8'))
        except Exception: current={}
    versions=current.get('artifacts',{}); stamp=datetime.now(timezone.utc).isoformat()
    for raw in paths:
        p=Path(raw)
        if not p.is_absolute(): p=root/p
        if not p.exists() or not p.is_file() or '.git' in p.parts: continue
        rel=str(p.relative_to(root)); digest=_sha(p); entry=versions.setdefault(rel,{'versions':[]})
        if not entry['versions'] or entry['versions'][-1]['sha256']!=digest:
            entry['versions'].append({'version':len(entry['versions'])+1,'sha256':digest,'size':p.stat().st_size,'timestamp':stamp})
        db.artifact(project_id,rel,'file',{'sha256':digest,'version':entry['versions'][-1]['version']})
    manifest.write_text(json.dumps({'schema_version':1,'updated_at':stamp,'artifacts':versions},indent=2,ensure_ascii=False),encoding='utf-8')
    return 'docs/ARTIFACT_MANIFEST.json'
