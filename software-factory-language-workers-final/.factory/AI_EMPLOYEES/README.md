# AI Employee System

The Software Factory treats AI models as role-based employees. Models are providers; roles are stable contracts.

## Employees

- MANAGER — owns orchestration, task assignment and escalation.
- PLANNER — decomposes requirements into executable work.
- DEVELOPER — implements code and tests.
- TESTER — tries to break the implementation and records evidence.
- QA — validates acceptance criteria and regression safety.
- REVIEWER — reviews diffs and blocks unsafe/incomplete changes.
- SECURITY — checks secrets, permissions, dependencies and attack surface.
- RELEASE — validates release readiness and deployment evidence.
- MONITOR — watches runtime health and creates incident tasks.
- AUDITOR — periodically checks factory consistency and process drift.

A role may use any configured AI provider. Provider/model routing is separate from the employee contract so failover does not change responsibilities.

## Rules

1. Employees never receive secrets through task files.
2. Every task has an owner role, acceptance criteria and evidence.
3. A task is not complete because a model says it is complete; tests/evidence are required.
4. Review and security remain independent gates.
5. Human approval remains required for configured high-risk actions.
6. One task at a time per project is the default execution invariant.

## Task lifecycle

INBOX → IN_PROGRESS → REVIEW → VERIFIED

Failures move to FAILED with evidence and can be retried by the Manager.
