# 007 TASK — Real AI Employee Execution + End-to-End Verification

Type: TASK
Owner: Claude
Manager: ChatGPT
Priority: HIGH

## Objective

Turn the existing filesystem-backed AI employee model into a real executable employee workflow and verify the factory can complete a real project safely.

The current production service is healthy, but the employee folders are still primarily a communication surface. The queue/worker/orchestrator already execute the project pipeline, so this task must connect task assignment/role contracts to actual execution without duplicating the existing workflow.

## Required outcome

1. A task assigned to an employee role is actually executed by the correct role/agent where that role has a concrete executable agent.
2. Developer implementation tasks continue to use the Developer agent.
3. Tester/QA, reviewer, security, release, planner, and manager responsibilities must not be silently treated as developer work when the task contract explicitly assigns one of those roles.
4. Preserve the existing stage gates and human approvals:
   - requirements approval
   - UI/UX design approval
   - Flutter dependency approval
   - final human approval
5. DB remains authoritative; .factory/TASKS files remain the employee communication/evidence surface.
6. Every completed task must record evidence and mirror it back to the corresponding employee task file.
7. A failed employee task must create/update a fix task and never be marked DONE without evidence.
8. Preserve AI provider failover and quota handling.
9. Do not expose secrets in logs/task files.
10. Do not break Telegram polling or supervisor/worker startup.

## Verification target

Use a small but real Flutter benchmark project for end-to-end validation:
- private generated GitHub repository
- Flutter application
- at least 3 meaningful screens
- local persistent data
- CRUD for the core entity
- validation/error states
- automated tests
- README/run instructions
- security/basic dependency review
- final release artifact

The exact benchmark app can be a Personal Expense Manager if no existing user project is selected.

## Tests required

- Existing full test suite.
- New unit tests for employee-role routing/execution.
- Regression test proving explicit task role is preserved.
- Regression test proving a completed task contains evidence and is mirrored to .factory/TASKS/VERIFIED.
- Regression test proving a failed task cannot become DONE.
- Worker queue test covering WAITING_FOR_APPROVAL and WAITING_FOR_QUOTA.
- End-to-end factory smoke test using mock provider if real provider credentials are unavailable.
- If real AI credentials are available in Claude's environment, run the real benchmark and report exact evidence; never print credentials.

## Evidence required in CLAUDE_TO_CHATGPT

Reply with:
- Status
- What changed
- Files changed
- Tests/checks and exact results
- E2E result
- Evidence paths
- Risks / next action
- Commit SHA
- Branch
- PR URL

Rules:
- Do not claim tests passed without actual output.
- Do not modify Railway secrets.
- Do not commit secrets.
- Prefer feature branch + PR.
- One task at a time.
