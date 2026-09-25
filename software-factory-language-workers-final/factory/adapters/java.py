from __future__ import annotations
from pathlib import Path
from factory.adapters.base import ProjectAdapter

class JavaAdapter(ProjectAdapter):
    name='java'
    def detect_project(self,w):
        p=Path(w); return (p/'pom.xml').exists() or (p/'build.gradle').exists() or (p/'build.gradle.kts').exists()
    def _gradle(self,w): return (Path(w)/'gradlew').exists() or (Path(w)/'gradlew.bat').exists()
    def install_dependencies(self): return 'mvn -B -q -DskipTests dependency:go-offline'
    def format(self): return 'mvn -B -q fmt:format'
    def analyze(self): return 'mvn -B -q verify -DskipTests'
    def test(self): return 'mvn -B test'
    def build(self): return 'mvn -B package -DskipTests'
    def validate_environment(self): return 'java --version'
    def validation_commands(self, workspace=None):
        p=Path(workspace) if workspace else None
        if p and (p/'pom.xml').exists():
            return [('unit_tests',self.test()),('build_validation',self.build())]
        if p and (p/'gradlew').exists(): return [('unit_tests','./gradlew test'),('build_validation','./gradlew build')]
        if p and (p/'gradlew.bat').exists(): return [('unit_tests','gradlew.bat test'),('build_validation','gradlew.bat build')]
        return [('unit_tests','gradle test'),('build_validation','gradle build')]
