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
