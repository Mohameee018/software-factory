from __future__ import annotations
from pathlib import Path
import json
from factory.agents.base import Agent
from factory.models import AgentResult
from factory.intake import extract_text

SCHEMA={
  "type":"object",
  "properties":{
    "status":{"type":"string","enum":["NEED_INFO","READY_FOR_REVIEW"]},
    "reply":{"type":"string"},
    "missing_information":{"type":"array","items":{"type":"string"}},
    "project_name":{"type":"string"},
    "project_type":{"type":"string"},
    "prd":{"type":"string"},
    "requirements":{"type":"string"},
    "acceptance_criteria":{"type":"string"},
    "assumptions":{"type":"array","items":{"type":"string"}}
  },
  "required":["status","reply","missing_information","project_name","project_type","prd","requirements","acceptance_criteria","assumptions"]
}

class RequirementsAgent(Agent):
    name="Requirements Specialist"
    role="requirements"
    instructions=(
        "Act as a senior product discovery specialist and conversational requirements analyst. "
        "Talk naturally like ChatGPT. Never use a fixed questionnaire. Ask exactly one useful "
        "next question when important information is missing, based on the complete conversation, "
        "project files and prior answers. Never ask for information already present. Do not invent "
        "critical product behavior. When enough information is known, produce complete PRD, "
        "REQUIREMENTS and ACCEPTANCE_CRITERIA documents. Prefer explicit assumptions over guessing."
    )
    def __init__(self,provider): self.provider=provider

    def run(self,context,task=None):
        w=Path(context.workspace); d=w/"docs"; d.mkdir(parents=True,exist_ok=True)
        conversation=d/"CLIENT_CONVERSATION.md"
        history=conversation.read_text(encoding="utf-8",errors="ignore") if conversation.exists() else ""
        files=[]
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".md",".txt",".json",".yaml",".yml",".csv"} and p.name!="CLIENT_CONVERSATION.md":
                try: files.append(f"### {p.relative_to(w)}\n{p.read_text(encoding='utf-8',errors='ignore')[:16000]}")
                except Exception: pass
        prompt=f"""PROJECT REQUEST:
{context.project.description}

CONVERSATION:
{history[-30000:]}

AVAILABLE PROJECT MATERIAL:
{chr(10).join(files)[-50000:]}

Your job is to continue a natural client discovery conversation. Decide whether one important
piece of information is still missing. If yes, status=NEED_INFO and reply with ONE clear,
human-sounding question only. If no, status=READY_FOR_REVIEW and generate the three documents.
The client may have specified Flutter, Android, iOS, Web, Windows, macOS or other platforms;
preserve explicit platform requirements and identify platform-specific behavior when known.
Do not turn this into a numbered questionnaire.
"""
        images=[]
        for ext in ('*.png','*.jpg','*.jpeg','*.webp'):
            for p in d.rglob(ext):
                try:
                    import base64
                    mime='image/png' if p.suffix.lower()=='.png' else 'image/jpeg'
                    images.append({'mime_type':mime,'data':base64.b64encode(p.read_bytes()).decode('ascii')})
                except OSError: pass
        try:
            data=self.provider.generate_json(self.instructions,prompt,SCHEMA,timeout=context.timeout,images=images or None)
        except Exception as e:
            return AgentResult(success=False,agent_name=self.name,summary="Requirements discovery failed.",errors=[str(e)],next_action="retry")
        if getattr(self.provider,"is_mock",False):
            data={"status":"READY_FOR_REVIEW","reply":"جمعت المتطلبات الأساسية. راجع الملفات قبل ما أسلمها للـ Manager.","missing_information":[],"project_name":context.project.name,"project_type":context.project.project_type.value,"prd":"# Product Requirements\n\n"+context.project.description,"requirements":"# Requirements\n\n- "+context.project.description,"acceptance_criteria":"# Acceptance Criteria\n\n- Requested product journey is implemented and tested.","assumptions":[]}
        with conversation.open("a",encoding="utf-8") as fh:
            fh.write(f"\n\n## Factory turn\nUser context: {context.project.description}\nFactory: {data.get('reply','')}\n")
        if data["status"]=="NEED_INFO":
            return AgentResult(success=True,agent_name=self.name,summary=data["reply"],detailed_output=data,next_action="ask_client")
        # Preserve explicit client platform/domain; never let a generic model label overwrite it.\n        from factory.models import ProjectType\n        import re\n        detected_type = str(data.get("project_type","")).strip().casefold()\n        explicit_flutter = bool(re.search(r"\\bflutter\\b", history + "\\n" + context.project.description, re.I))\n        if explicit_flutter:\n            context.project.project_type = ProjectType.FLUTTER\n        elif detected_type in {x.value for x in ProjectType if x != ProjectType.UNKNOWN}:\n            context.project.project_type = ProjectType(detected_type)\n        (d/"PRD.md").write_text(str(data["prd"]),encoding="utf-8")
        (d/"REQUIREMENTS.md").write_text(str(data["requirements"]),encoding="utf-8")
        (d/"ACCEPTANCE_CRITERIA.md").write_text(str(data["acceptance_criteria"]),encoding="utf-8")
        (d/"ASSUMPTIONS.md").write_text("# Assumptions\n\n"+("\n".join(f"- {x}" for x in data.get("assumptions",[])) or "- None"),encoding="utf-8")
        return AgentResult(success=True,agent_name=self.name,summary=data["reply"],detailed_output=data,files_created=["docs/PRD.md","docs/REQUIREMENTS.md","docs/ACCEPTANCE_CRITERIA.md","docs/ASSUMPTIONS.md"],next_action="client_approval",completion_evidence=["docs/PRD.md","docs/REQUIREMENTS.md","docs/ACCEPTANCE_CRITERIA.md","docs/ASSUMPTIONS.md"])
