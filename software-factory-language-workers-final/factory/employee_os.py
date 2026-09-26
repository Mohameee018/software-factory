from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import re

EMPLOYEE_ROLES = {
    "manager": "Coordinate work, dependencies and escalation.",
    "planner": "Decompose requirements into executable work.",
    "developer": "Implement code and tests for the assigned task.",
    "tester": "Break the implementation and record reproducible evidence.",
    "qa": "Validate acceptance criteria and regression safety.",
    "reviewer": "Review implementation quality and correctness.",
    "security": "Check secrets, permissions, dependencies and attack surface.",
    "release": "Validate release readiness and deployment evidence.",
    "monitor": "Watch runtime health and create incident tasks.",
    "auditor": "Audit factory consistency and process drift.",
}

def role_for_task(title: str, current: str | None = None) -> str:
    """Choose a stable employee role without changing an explicit Manager assignment."""
    if current and current.lower() in EMPLOYEE_ROLES:
        return current.lower()
    text = (title or "").lower()
    if any(x in text for x in ("test", "qa", "regression")):
        return "tester"
    if any(x in text for x in ("security", "secret", "permission", "vulnerability")):
        return "security"
    if any(x in text for x in ("review", "audit", "inspect")):
        return "reviewer"
    if any(x in text for x in ("plan", "requirements", "architecture")):
        return "planner"
    return "developer"

def _safe_task_name(task_id: str, title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title).strip("-").lower()[:70] or "task"
    return f"{task_id}-{slug}.md"

def sync_task_file(project_workspace: str | Path, task, status: str | None = None, *, evidence: list[str] | None = None) -> Path:
    """Mirror a DB task into a human-readable employee inbox/review folder.

    The DB remains authoritative; the files are the employee communication surface.
    """
    root = Path(project_workspace) / ".factory" / "TASKS"
    state = (status or getattr(task.status, "value", task.status) or "PENDING").upper()
    bucket = {"PENDING": "INBOX", "READY": "INBOX", "IN_PROGRESS": "IN_PROGRESS", "TESTING": "REVIEW", "REVIEW": "REVIEW", "DONE": "VERIFIED", "FAILED": "FAILED", "BLOCKED": "FAILED"}.get(state, "INBOX")
    path = root / bucket
    path.mkdir(parents=True, exist_ok=True)
    role = role_for_task(getattr(task, "title", ""), getattr(task, "assigned_agent", None))
    lines = [
        f"# {task.id}: {task.title}", "", f"- Status: `{state}`", f"- Employee: `#{role.upper()}`",
        f"- Mission: {EMPLOYEE_ROLES[role]}", f"- Updated: {datetime.now(timezone.utc).isoformat()}", "",
        "## Task", getattr(task, "description", "") or task.title, "", "## Acceptance criteria"
    ]
    criteria = getattr(task, "acceptance_criteria", []) or []
    lines.extend([f"- {x}" for x in criteria] or ["- Complete the requested change without regressions."])
    tests = getattr(task, "tests_required", []) or []
    if tests: lines += ["", "## Required tests", *[f"- {x}" for x in tests]]
    expected = getattr(task, "files_expected", []) or []
    if expected: lines += ["", "## Expected files", *[f"- `{x}`" for x in expected]]
    if getattr(task, "failure_reason", None): lines += ["", "## Previous failure", task.failure_reason]
    if evidence: lines += ["", "## Evidence", *[f"- {x}" for x in evidence]]
    out = path / _safe_task_name(task.id, task.title)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
