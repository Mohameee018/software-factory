# Auto Skills

Skills are capabilities selected automatically from project context. The client does not need to name a skill.

Built-in skills are defined in `factory/skills.py`. Custom skills can be added as:

```
skills/<skill-name>/SKILL.md
```

The Manager/Orchestrator decides when a skill is relevant and passes the relevant context to the appropriate employee.
