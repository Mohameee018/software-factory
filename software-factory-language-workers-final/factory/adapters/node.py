from __future__ import annotations
import json
from pathlib import Path
from factory.adapters.base import ProjectAdapter

class NodeAdapter(ProjectAdapter):
    name='node'
    def detect_project(self,w): return (Path(w)/'package.json').exists()
    def _manager(self,w):
        p=Path(w)
        if (p/'pnpm-lock.yaml').exists(): return 'pnpm'
        if (p/'yarn.lock').exists(): return 'yarn'
        return 'npm'
    def _scripts(self,w):
        try: return json.loads((Path(w)/'package.json').read_text(encoding='utf-8')).get('scripts',{})
        except Exception: return {}
    def install_dependencies(self): return 'npm install'
    def format(self): return 'npm run format'
    def analyze(self): return 'npm run lint'
    def test(self): return 'npm test'
    def build(self): return 'npm run build'
    def validate_environment(self): return 'node --version'
    def validation_commands(self, workspace=None):
        p=Path(workspace) if workspace else None
        manager=self._manager(p) if p else 'npm'
        run=lambda script: f'{manager} run {script}'
        test='npm test' if manager=='npm' else f'{manager} test'
        install={'npm':'npm install','yarn':'yarn install','pnpm':'pnpm install'}[manager]
        scripts=self._scripts(p) if p else {}
        out=[('dependencies',install)]
        if not p or 'format' in scripts: out.append(('format',run('format')))
        if not p or 'lint' in scripts: out.append(('static_analysis',run('lint')))
        if not p or 'test' in scripts: out.append(('unit_tests',test))
        if not p or 'build' in scripts: out.append(('build_validation',run('build')))
        return out
