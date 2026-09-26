from __future__ import annotations
from dataclasses import dataclass, field
from typing import FrozenSet

@dataclass(frozen=True)
class EmployeeContract:
    role: str
    title: str
    mission: str
    responsibilities: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    skills: tuple[str, ...]
    permissions: FrozenSet[str] = frozenset()
    quality_gates: tuple[str, ...] = ()
    escalates_to: str = "manager"

ROLE_CONTRACTS: dict[str, EmployeeContract] = {
    "manager": EmployeeContract("manager","Project Manager","Own delivery decisions and assemble the right team.",
        ("validate scope","select roles and skills","resolve cross-team conflicts","approve/reject plans","control rework loops"),
        ("PRD.md","REQUIREMENTS.md","ARCHITECTURE.md","TASKS.md"),
        ("MANAGER_PLAN.md","TASK_ASSIGNMENTS"),("planning","delivery-management","risk-management"),
        frozenset({"read_all_project_artifacts","assign_tasks","request_rework","approve_plan"}),
        ("requirements_coverage","architecture_coverage","task_coverage"),"client"),
    "requirements": EmployeeContract("requirements","Requirements Specialist","Turn natural client input and files into an unambiguous product contract.",
        ("discover intent","detect ambiguity","preserve explicit constraints","maintain assumptions","define acceptance criteria"),
        ("client_conversation","project_files","user_memory"),
        ("PRD.md","REQUIREMENTS.md","ACCEPTANCE_CRITERIA.md","ASSUMPTIONS.md"),
        ("product-discovery","business-analysis","requirements-traceability"),
        frozenset({"read_client_input","read_project_files","write_requirements"}),
        ("requirements_approval",),"manager"),
    "architect": EmployeeContract("architect","Solution Architect","Convert approved product intent into a scalable technical architecture.",
        ("choose boundaries","define integrations","define data ownership","define non-functional requirements","map architecture to requirements"),
        ("PRD.md","REQUIREMENTS.md","DESIGN.md","ACCEPTANCE_CRITERIA.md"),
        ("ARCHITECTURE.md",),("architecture","distributed-systems","security-by-design"),
        frozenset({"read_approved_docs","write_architecture"}),("architecture_coverage",),"manager"),
    "planner": EmployeeContract("planner","Product Planner","Produce an executable, dependency-aware delivery plan.",
        ("decompose scope","identify risks","define milestones","prepare task candidates"),
        ("PRD.md","REQUIREMENTS.md","ARCHITECTURE.md"),
        ("TASKS.md","MVP.md","RISKS.md"),("planning","decomposition","dependency-analysis"),
        frozenset({"read_project_artifacts","write_plan"}),("task_coverage",),"manager"),
    "developer": EmployeeContract("developer","Software Developer","Implement assigned work with evidence and tests.",
        ("change code","run relevant commands","preserve existing behavior","report evidence"),
        ("assigned_task","architecture","acceptance_criteria"),
        ("source_changes","implementation_evidence"),("software-development","testing","debugging"),
        frozenset({"read_assigned_task","write_source","run_safe_commands"}),("implementation_evidence",),"techlead"),
    "tester": EmployeeContract("tester","QA Engineer","Verify behavior against acceptance criteria and regressions.",
        ("design tests","execute tests","record evidence","identify failures"),
        ("acceptance_criteria","source","implementation_evidence"),
        ("TEST_REPORT.md","test_evidence"),("qa","test-automation","regression-testing"),
        frozenset({"read_project","run_tests","write_test_report"}),("test_evidence",),"manager"),
    "reviewer": EmployeeContract("reviewer","Code Reviewer","Independently review correctness, maintainability and risk.",
        ("inspect diff","find defects","require evidence","verify fixes"),
        ("source","architecture","task"),("CODE_REVIEW.md","review_findings"),("code-review","secure-coding"),
        frozenset({"read_source","read_architecture","write_review"}),("code_review",),"manager"),
    "security": EmployeeContract("security","Security Engineer","Identify and block material security risks.",
        ("threat review","dependency/security checks","verify mitigations"),
        ("source","architecture","dependencies"),("SECURITY_REVIEW.md","security_findings"),("application-security","threat-modeling"),
        frozenset({"read_project","run_security_checks","write_security_review"}),("security_review",),"manager"),
    "uiux": EmployeeContract("uiux","UI/UX Designer","Translate approved product intent into an implementable experience.",
        ("define flows","design screens","document design system","provide preview"),
        ("PRD.md","REQUIREMENTS.md"),("DESIGN.md","design/preview.html"),("uiux","design-systems","accessibility"),
        frozenset({"read_approved_requirements","write_design"}),("design_approval",),"manager"),
    "uiux_reviewer": EmployeeContract("uiux_reviewer","UX Reviewer","Verify the implementation matches approved experience.",
        ("compare implementation to design","find UX regressions","verify responsive behavior"),
        ("DESIGN.md","source"),("UX_REVIEW.md","ux_findings"),("ux-review","accessibility"),
        frozenset({"read_design","read_source","write_ux_review"}),("ux_review",),"manager"),
    "release": EmployeeContract("release","Release Manager","Prepare verified software for delivery.",
        ("verify release gates","assemble release evidence","prepare handoff"),
        ("all_quality_reports","build_artifacts"),("release_evidence","handoff"),("release-management","documentation"),
        frozenset({"read_release_artifacts","write_release_notes"}),("final_gate",),"client"),
}

def get_contract(role: str) -> EmployeeContract:
    return ROLE_CONTRACTS.get(role.lower(), EmployeeContract(role.lower(),role,"Execute an explicitly assigned project responsibility.",(),(),(),()))

def select_team(requirements_text: str, project_type: str = "") -> list[str]:
    text=(requirements_text+" "+project_type).lower()
    team=["manager","requirements","planner","architect","developer","tester","reviewer","security","release"]
    if any(x in text for x in ("flutter","mobile","ios","android","web","desktop","ui","design")):
        team.insert(4,"uiux"); team.insert(-3,"uiux_reviewer")
    if any(x in text for x in ("api","backend","service","deployment","docker","cloud")): team.insert(-1,"devops")\n    if any(x in text for x in ("documentation","guide","manual","api docs")): team.insert(-1,"writer")\n    if any(x in text for x in ("complex","large","microservice","architecture","multi-service")): team.insert(4,"techlead")\n    team.append("handoff")\n    return list(dict.fromkeys(team))
