from factory.budget import BudgetManager
from factory.artifacts import record_artifacts
def test_budget_blocks_after_limit(tmp_path):
    class S: max_agent_runs=1
    from factory.database import Database
    db=Database(tmp_path/'x.db')
    assert BudgetManager(db,S()).allowed('missing-project')
def test_artifact_manifest_versions(tmp_path):
    from factory.database import Database
    db=Database(tmp_path/'x.db'); (tmp_path/'docs').mkdir(); f=tmp_path/'app.py'; f.write_text('one')
    record_artifacts(str(tmp_path),'p',db,[str(f)])
    f.write_text('two'); record_artifacts(str(tmp_path),'p',db,[str(f)])
    import json
    data=json.loads((tmp_path/'docs/ARTIFACT_MANIFEST.json').read_text())
    assert len(data['artifacts']['app.py']['versions'])==2
