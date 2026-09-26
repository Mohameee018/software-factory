from __future__ import annotations
from pathlib import Path
from typing import Iterable
from factory.models import AgentResult, Task, WorkflowState

class GateFailure(ValueError):
    """Raised when an agent claims completion without enough verifiable evidence."""

def _missing(root: Path, paths: Iterable[str]) -> list[str]:
    return [p for p in paths if not (root / p).exists()]

def verify(stage: WorkflowState, workspace: str, result: AgentResult | None = None, task: Task | None = None) -> list[str]:
    root = Path(workspace)
    errors: list[str] = []

    if stage == WorkflowState.WAITING_FOR_DESIGN_APPROVAL:
        errors += [f"missing_design_artifact:{p}" for p in _missing(root, ("docs/DESIGN.md", "docs/design/preview.html"))]
        if result and not result.files_created and not (root / "docs/design/preview.html").exists():
            errors.append("design_agent_produced_no_verifiable_artifact")

    elif stage == WorkflowState.DOCUMENTATION:
        errors += [f"missing_planning_document:{p}" for p in _missing(root, (
            "docs/PRD.md","docs/MVP.md","docs/ARCHITECTURE.md","docs/REQUIREMENTS.md",
            "docs/TASKS.md","docs/ACCEPTANCE_CRITERIA.md","docs/RISKS.md"
        ))]

    elif stage == WorkflowState.ARCHITECTURE:
        errors += [f"missing_architecture_artifact:{p}" for p in _missing(root, ("docs/ARCHITECTURE.md",))]
        if result and not result.success:
            errors.append("architect_result_not_successful")

    elif stage == WorkflowState.IMPLEMENTATION:
        if not (root / "docs/TRACEABILITY.md").exists():
            errors.append("missing_traceability_artifact")
        if task is None:
            errors.append("implementation_gate_missing_task")
        elif result is not None:
            changed = set(result.files_created + result.files_modified)
            if task.files_expected:
                for expected in task.files_expected:
                    if not (root / expected).exists():
                        errors.append(f"expected_file_missing:{expected}")
            if not changed and not task.files_expected:
                errors.append("developer_produced_no_file_changes")
            failed_commands=[x for x in result.generated_changes if isinstance(x,dict) and x.get("op")=="run" and int(x.get("exit_code",0))!=0]
            if failed_commands:
                errors.append("developer_reported_failed_command")

    elif stage == WorkflowState.TESTING:
        if result is None or not result.success:
            errors.append("qa_did_not_pass")
        elif isinstance(result.detailed_output, dict):
            rows = result.detailed_output.get("results", [])
            if rows and any(int(row[2]) != 0 for row in rows if isinstance(row, (list, tuple)) and len(row) >= 3):
                errors.append("qa_contains_failed_test")
            if not rows and not result.tests_run:
                errors.append("qa_produced_no_test_evidence")

    elif stage == WorkflowState.REVIEWING:
        if result is None or not result.success:
            errors.append("code_review_not_passed")

    elif stage == WorkflowState.UX_REVIEW:
        if result is None or not result.success:
            errors.append("uiux_review_not_passed")

    elif stage == WorkflowState.SECURITY_REVIEW:
        if result is None or not result.success:
            errors.append("security_review_not_passed")

    elif stage == WorkflowState.READY_FOR_HUMAN:
        required = ("docs/DESIGN.md","docs/PRD.md","docs/ARCHITECTURE.md","docs/ACCEPTANCE_CRITERIA.md","docs/TEST_REPORT.md","docs/CODE_REVIEW.md","docs/UX_REVIEW.md","docs/SECURITY_REVIEW.md")
        errors += [f"final_artifact_missing:{p}" for p in _missing(root, required)]

    return errors
