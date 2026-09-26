from __future__ import annotations
from pathlib import Path
from factory.agents.base import Agent
from factory.models import AgentResult
from factory.tools.safety import redact_secrets

SCHEMA={
    "type":"object",
    "properties":{
        "architecture":{"type":"string"},"components":{"type":"string"},"data_model":{"type":"string"},
        "api_contracts":{"type":"string"},"file_structure":{"type":"string"},"technical_decisions":{"type":"string"},
        "acceptance_mapping":{"type":"string"},"summary":{"type":"string"}
    },
    "required":["architecture","components","data_model","api_contracts","file_structure","technical_decisions","acceptance_mapping","summary"]
}

class ArchitectAgent(Agent):
    name="Architect Agent"; role="architect"
    instructions=("Act as the software architect. Turn approved requirements and the UI/UX direction into an implementation-ready architecture. "
                  "Do not invent critical product behavior. Make dependencies, boundaries, data flow, file structure and acceptance mapping explicit.")
    def __init__(self, provider): self.provider=provider

    def run(self, context, task=None):
        w=Path(context.workspace); d=w/"docs"
        required=("PRD.md","REQUIREMENTS.md","ACCEPTANCE_CRITERIA.md","DESIGN.md")
        missing=[x for x in required if not (d/x).exists()]
        if missing:
            return AgentResult(success=False,agent_name=self.name,summary="Architecture blocked by missing source documents.",
                               errors=["missing_architecture_inputs:"+",".join(missing)],next_action="fix")
        source="\n\n".join(f"### {x}\n{redact_secrets((d/x).read_text(encoding='utf-8',errors='ignore')[:18000])}" for x in required)
        prompt=f"""Create an implementation-ready architecture from these approved project artifacts.

{source}

Return JSON with concrete components, data model, API contracts (if applicable), file/folder structure, technical decisions and a mapping from acceptance criteria to implementation responsibilities. Flag unresolved ambiguity instead of inventing behavior."""
        try:
            data=self.provider.generate_json(self.instructions,prompt,SCHEMA,timeout=context.timeout)
        except Exception as e:
            return AgentResult(success=False,agent_name=self.name,summary="Architecture generation failed.",errors=[str(e)],next_action="fix")
        if getattr(self.provider,"is_mock",False):
            data={"architecture":"Layered application with clear UI, domain and infrastructure boundaries.",
                  "components":"UI, application/domain services, persistence/integration adapters.",
                  "data_model":"Defined by project requirements; keep persistence behind an interface.",
                  "api_contracts":"Document external boundaries and validation where applicable.",
                  "file_structure":"Follow the existing project conventions and keep modules cohesive.",
                  "technical_decisions":"Prefer existing dependencies and the smallest safe architecture.",
                  "acceptance_mapping":"Every acceptance criterion maps to at least one implementation task and test.",
                  "summary":"Mock architecture approved."}
        content=(f"# Architecture\n\n## Summary\n{data['summary']}\n\n## Architecture\n{data['architecture']}\n\n"
                 f"## Components\n{data['components']}\n\n## Data Model\n{data['data_model']}\n\n"
                 f"## API Contracts\n{data['api_contracts']}\n\n## File Structure\n{data['file_structure']}\n\n"
                 f"## Technical Decisions\n{data['technical_decisions']}\n\n## Acceptance Mapping\n{data['acceptance_mapping']}\n")
        (d/"ARCHITECTURE.md").write_text(content,encoding="utf-8")
        return AgentResult(success=True,agent_name=self.name,summary=data["summary"],
                           detailed_output=data,files_created=["docs/ARCHITECTURE.md"],next_action="create_tasks",
                           completion_evidence=["docs/ARCHITECTURE.md"])
