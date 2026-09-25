from __future__ import annotations
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from factory.permissions import Permission, check

@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float

ALLOWED_PREFIXES = ('python ', 'python -m ', 'pytest', 'ruff ', 'dart ', 'flutter ', 'git ', 'npm ', 'yarn ', 'pnpm ', 'node ', 'java ', 'mvn ', 'gradle ', './gradlew ', 'gradlew.bat ', 'powershell ')


def _argv(command: str) -> list[str]:
    """Parse an allow-listed command without invoking a shell.

    `python` is resolved to the interpreter running the factory so a factory
    started with `.venv\\Scripts\\python.exe` never accidentally executes a
    different system Python from PATH (especially on Windows).
    """
    parts = shlex.split(command, posix=(sys.platform != 'win32'))
    if not parts:
        raise PermissionError('Empty command is not allowed')
    if parts[0].lower() == 'python':
        parts[0] = sys.executable
    return parts


def run(role, command, cwd, timeout=120):
    check(role, Permission.RUN_DEV_COMMANDS if role == 'developer' else Permission.RUN_TESTS)
    if any(x in command for x in ('&&', '||', ';', '|', '>', '<', '`', '$(')):
        raise PermissionError('Shell operators are not permitted')
    if '\n' in command or '\r' in command:
        raise PermissionError('Multiline commands are not permitted')
    normalized = command.strip().lower()
    if role == 'developer' and normalized in {'flutter pub get', 'pip install', 'python -m pip install', 'npm install', 'npm i', 'dart pub get'}:
        raise PermissionError('Dependency installation requires explicit ApprovalService approval and is not available to Developer shell actions')
    if not command.strip().lower().startswith(ALLOWED_PREFIXES):
        raise PermissionError(f'Command not allowed: {command}')
    argv = _argv(command)
    start = time.monotonic()
    try:
        p = subprocess.run(argv, cwd=str(Path(cwd)), shell=False, capture_output=True, text=True, timeout=timeout)
        exit_code = p.returncode
        stdout, stderr = p.stdout, p.stderr
    except FileNotFoundError as e:
        exit_code = 127
        stdout, stderr = '', str(e)
    except subprocess.TimeoutExpired as e:
        exit_code = 124
        stdout = e.stdout or ''
        stderr = e.stderr or f'Command timed out after {timeout}s'

    def redact(s):
        return re.sub(r'(?i)(api[_-]?key|password|secret|token)(\s*[:=]\s*)[^\s,;]+', r'\1\2[REDACTED]', s or '')

    return CommandResult(command, exit_code, redact(stdout), redact(stderr), time.monotonic() - start)
