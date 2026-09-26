from __future__ import annotations
from pathlib import Path

DEFAULT_SKILLS={
 "requirements":"Conversational discovery, ambiguity detection and PRD generation.",
 "uiux":"UI/UX, responsive design, accessibility and visual systems.",
 "architecture":"System architecture, APIs, data and platform boundaries.",
 "flutter":"Flutter/Dart implementation across mobile, web and desktop.",
 "backend":"API, authentication, business logic and integrations.",
 "database":"Schema, persistence, migrations and data integrity.",
 "testing":"Automated tests, integration tests and acceptance validation.",
 "security":"Threat modeling, secrets, auth and secure coding.",
 "review":"Code quality, maintainability and requirement traceability.",
 "debugging":"Root-cause analysis and targeted fixes.",
 "release":"Build, packaging and deployment readiness."
}

def available_skills(root: str|Path):
    root=Path(root); skills=dict(DEFAULT_SKILLS)
    custom=root/"skills"
    if custom.is_dir():
        for p in custom.iterdir():
            if p.is_dir() and (p/"SKILL.md").exists():
                skills[p.name]=(p/"SKILL.md").read_text(encoding="utf-8",errors="ignore")[:6000]
    return skills

def select_skills(text: str, root: str|Path):
    t=text.lower(); result=["requirements"]
    if any(x in t for x in ("flutter","android","ios","iphone","web","desktop","windows","macos")): result.append("flutter")
    if any(x in t for x in ("api","backend","login","authentication","auth","server")): result.append("backend")
    if any(x in t for x in ("database","sql","postgres","mysql","sqlite","data")): result.append("database")
    if any(x in t for x in ("design","ui","ux","screen","brand","color")): result.append("uiux")
    if any(x in t for x in ("security","permission","role","password","token")): result.append("security")
    result.extend(["testing","review"])
    return list(dict.fromkeys(result))
