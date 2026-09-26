from pathlib import Path

from factory.models import ProjectType
from factory.project_detection import detect_project_type


def test_flutter_detection_english_and_arabic():
    assert detect_project_type('Build a Flutter mobile app') == ProjectType.FLUTTER
    assert detect_project_type('متجر ملابس Flutter') == ProjectType.FLUTTER
    assert detect_project_type('Dart Flutter clothing store') == ProjectType.FLUTTER


def test_python_detection():
    assert detect_project_type('Build a Python API') == ProjectType.PYTHON


def test_unknown_detection():
    assert detect_project_type('Build a simple clothing store app') == ProjectType.UNKNOWN


def test_empty_workspace_does_not_override_text_detection():
    assert detect_project_type('Build a Flutter mobile app', '') == ProjectType.FLUTTER
    assert detect_project_type('Build a Flutter mobile app', '   ') == ProjectType.FLUTTER
    assert detect_project_type('Build a Flutter mobile app', None) == ProjectType.FLUTTER


def test_real_workspace_detection_remains_authoritative(tmp_path: Path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="demo"\n')
    assert detect_project_type('Build a Flutter mobile app', tmp_path) == ProjectType.PYTHON


def test_real_flutter_workspace_detection():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / 'pubspec.yaml').write_text('name: demo\n')
        assert detect_project_type('Build a Python API', root) == ProjectType.FLUTTER
