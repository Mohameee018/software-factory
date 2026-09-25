from pathlib import Path
from factory.adapters.base import ProjectAdapter
class PythonAdapter(ProjectAdapter):
    name='python'
    def detect_project(self,w): return (Path(w)/'pyproject.toml').exists() or (Path(w)/'requirements.txt').exists()
    def install_dependencies(self): return 'python -m pip install -e .'
    def format(self): return 'ruff format .'
    def analyze(self): return 'ruff check .'
    def test(self): return 'python -m pytest -q'
    def build(self): return 'python -m compileall .'
    def validate_environment(self): return 'python --version'
    def validation_commands(self, workspace=None):
        p=Path(workspace) if workspace else None; out=[]
        if p and (p/'requirements.txt').exists() and not (p/'pyproject.toml').exists():
            # requirements-only projects do not support editable install
            out.append(('dependencies','python -m pip install -r requirements.txt'))
        out += [('dependencies', self.install_dependencies())] if p and (p/'pyproject.toml').exists() else []
        out += [('format',self.format()),('static_analysis',self.analyze()),('unit_tests',self.test()),('build_validation',self.build())]
        return out
