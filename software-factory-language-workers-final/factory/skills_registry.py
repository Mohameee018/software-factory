from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    roles: tuple[str,...]
    triggers: tuple[str,...]
    quality_checks: tuple[str,...]

SKILLS=(
 Skill("requirements-traceability","Map requirements to executable work and evidence",("requirements","manager","planner"),("requirement","scope","acceptance"),("traceability",)),
 Skill("flutter","Flutter mobile/web/desktop engineering",("architect","developer","tester"),("flutter","dart","android","ios"),("flutter test",)),
 Skill("web-frontend","Web frontend engineering",("architect","developer","tester"),("web","frontend","react","next"),("build","test")),
 Skill("backend","API and service engineering",("architect","developer","tester"),("api","backend","server","authentication"),("integration-test",)),
 Skill("database","Data modeling and persistence",("architect","developer","tester"),("database","sql","postgres","schema"),("migration-test",)),
 Skill("security","Application security and threat modeling",("security","architect","reviewer"),("auth","security","payment","pii"),("security-review",)),
 Skill("accessibility","Accessibility and inclusive UX",("uiux","uiux_reviewer","tester"),("accessibility","a11y"),("accessibility-review",)),
 Skill("devops","Build/deploy/observability automation",("developer","release"),("deploy","docker","ci","cd","production"),("deployment-check",)),
)

def discover(text: str, roles: list[str]|None=None) -> list[Skill]:
    t=text.lower(); wanted=set(roles or ())
    return [s for s in SKILLS if (not wanted or wanted.intersection(s.roles)) and any(x in t for x in s.triggers)]

def names(text: str, roles: list[str]|None=None) -> list[str]:
    return [s.name for s in discover(text,roles)]
