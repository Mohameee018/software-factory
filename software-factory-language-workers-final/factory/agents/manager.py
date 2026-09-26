from __future__ import annotations
from pathlib import Path
from factory.agents.base import Agent
from factory.models import AgentResult
from factory.skills import select_skills
from factory.company_os import get_contract
from factory.skills_registry import names as discover_skill_names

SCHEMA={
 "type":"object",
 "properties":{
   "approved":{"type":"boolean"},
   "summary":{"type":"string"},
   "issues":{"type":"array","items":{"type":"string"}},
   "assignments":{"type":"array","items":{"type":"object","properties":{"task_number":{"type":"integer"},"role":{"type":"string"},"skills":{"type":"array","items":{"type":"string"}}},"required":["task_number","role","skills"]}}
 },
 "required":["approved","summary","issues","assignments"]
}

class ManagerAgent(Agent):
    name="Manager Agent"
    role="manager"
    instructions=(
        "Act as the senior delivery manager. Read the approved requirements, architecture, design and task plan. "
        "Validate that every important requirement is represented by tasks, acceptance criteria and tests. "
        "Do not silently accept contradictions or missing backend/auth/platform work. Assign each task to the "
        "appropriate employee role and select relevant skills automatically. If the plan is incomplete, reject it "
        "with concrete issues so the Planner/Architect can fix it. Never invent requirements."
    )
    def __init__(self,provider): self.provider=provider

    def run(self,context,task=None):
        w=Path(context.workspace); d=w/"docs"
        parts=[]
        for name in ("PRD.md","REQUIREMENTS.md","ACCEPTANCE_CRITERIA.md","DESIGN.md","ARCHITECTURE.md","TASKS.md"):
            p=d/name
            if p.exists(): parts.append(f"### {name}\n{p.read_text(encoding='utf-8',errors='ignore')[:22000]}")
        prompt="\n\n".join(parts)
        try:data=self.provider.generate_json(self.instructions,prompt,SCHEMA,timeout=context.timeout)
        except Exception as e:
            return AgentResult(success=False,agent_name=self.name,summary="Manager validation failed.",errors=[str(e)],next_action="fix")
        if getattr(self.provider,"is_mock",False):
            data={"approved":True,"summary":"Manager validation passed.","issues":[],"assignments":[]}
        lines=["# Manager Plan","","## Validation",data.get("summary","")]
        if data.get("issues"): lines += ["","## Issues"]+[f"- {x}" for x in data["issues"]]
        lines += ["","## Assignments"]
        tasks_path=d/"TASKS.md"
        task_lines=[]
        if tasks_path.exists():
            import re
            task_lines=[x for x in tasks_path.read_text(encoding="utf-8",errors="ignore").splitlines() if re.match(r"^\s*\d+[.)]\s+",x)]
        assignments=data.get("assignments",[])
        for a in assignments:
            n=int(a.get("task_number",0)); role=str(a.get("role","developer")).lower(); skills=list(a.get("skills") or [])
            if not skills:
                source=task_lines[n-1] if 0<n<=len(task_lines) else ""
                skills=list(dict.fromkeys(select_skills(source,w)+discover_skill_names(source,[role])))
            contract=get_contract(role)
            lines.append(f"- Task {n}: #{role.upper()} | Skills: {', '.join(skills)} | Gate: {', '.join(contract.quality_gates) or 'evidence'}")
        (d/"MANAGER_PLAN.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        return AgentResult(success=bool(data.get("approved")),agent_name=self.name,summary=data.get("summary",""),detailed_output=data,files_created=["docs/MANAGER_PLAN.md"],next_action="implement" if data.get("approved") else "replan",errors=list(data.get("issues",[])) if not data.get("approved") else [],completion_evidence=["docs/MANAGER_PLAN.md"])
