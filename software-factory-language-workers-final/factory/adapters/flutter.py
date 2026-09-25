from pathlib import Path
from factory.adapters.base import ProjectAdapter

class FlutterAdapter(ProjectAdapter):
    name='flutter'

    def detect_project(self, w):
        return (Path(w) / 'pubspec.yaml').exists()

    def install_dependencies(self):
        return 'flutter pub get'

    def format(self):
        return 'dart format .'

    def analyze(self):
        return 'flutter analyze'

    def test(self):
        return 'flutter test'

    def build(self):
        return 'flutter build apk --debug'

    def validate_environment(self):
        return 'flutter --version'

    def validation_commands(self):
        """Return the real Flutter lifecycle commands in execution order."""
        return [
            ('dependencies', self.install_dependencies()),
            ('format', self.format()),
            ('static_analysis', self.analyze()),
            ('unit_tests', self.test()),
            ('build_validation', self.build()),
        ]
