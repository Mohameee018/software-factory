from pathlib import Path
from factory.models import ProjectType, Project, FactoryState
from factory.project_detection import detect_project_type
from factory.adapters.registry import detect
from factory.database import Database
from factory.queue import PersistentJobQueue


def test_workspace_detection_priority(tmp_path):
    (tmp_path/'package.json').write_text('{}')
    assert detect_project_type(workspace=tmp_path) == ProjectType.NODE
    (tmp_path/'pom.xml').write_text('<project/>')
    assert detect_project_type(workspace=tmp_path) == ProjectType.JAVA
    (tmp_path/'pubspec.yaml').write_text('name: x')
    assert detect_project_type(workspace=tmp_path) == ProjectType.FLUTTER


def test_adapter_routing_by_real_project_files(tmp_path):
    cases=[('pyproject.toml','python','python'),('package.json','node','node'),('pom.xml','java','java'),('pubspec.yaml','flutter','flutter')]
    for filename, expected_name, expected_worker in cases:
        root=tmp_path/expected_name; root.mkdir(); (root/filename).write_text('{}')
        a=detect(root)
        assert a.name == expected_name
        assert expected_worker == a.name


def test_job_persists_worker_type(tmp_path):
    db=Database(tmp_path/'factory.db')
    p=Project(name='Node',description='node',project_type=ProjectType.NODE,workspace_path=str(tmp_path/'node'))
    Path(p.workspace_path).mkdir(); db.save_project(p)
    db.save_state(FactoryState(project_id=p.id,project_name=p.name,project_type=p.project_type,current_state=p.current_state,workspace_path=p.workspace_path))
    jid=PersistentJobQueue(db).enqueue(p.id)
    assert db.list_jobs(p.id)[0][-1] == 'node'
    assert db.claim_job('node-worker','node').id == jid
    assert db.claim_job('python-worker','python') is None
