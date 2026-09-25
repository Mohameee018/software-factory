from __future__ import annotations
import re
from pathlib import Path
from factory.models import ProjectType

# Natural-language fallback is kept for /new descriptions; workspace detection is authoritative
# once files exist. Priority is deterministic and documented: Flutter > Java > Node > Python.
_FLUTTER_PATTERNS = (r'\bflutter\b', r'\bdart\s+flutter\b')
_PYTHON_PATTERNS = (r'\bpython\b', r'\bpython\s+app\b')

def detect_project_type(description: str = '', workspace=None) -> ProjectType:
    if workspace is not None:
        root = Path(workspace)
        if (root / 'pubspec.yaml').exists(): return ProjectType.FLUTTER
        if any((root / n).exists() for n in ('pom.xml','build.gradle','build.gradle.kts')): return ProjectType.JAVA
        if (root / 'package.json').exists(): return ProjectType.NODE
        if any((root / n).exists() for n in ('pyproject.toml','requirements.txt')): return ProjectType.PYTHON
    text = (description or '').casefold()
    if any(re.search(pattern, text) for pattern in _FLUTTER_PATTERNS): return ProjectType.FLUTTER
    if re.search(r'\b(java|maven|gradle)\b', text): return ProjectType.JAVA
    if re.search(r'\b(node(?:\.js)?|npm|yarn|pnpm|typescript|react)\b', text): return ProjectType.NODE
    if any(re.search(pattern, text) for pattern in _PYTHON_PATTERNS): return ProjectType.PYTHON
    return ProjectType.UNKNOWN
