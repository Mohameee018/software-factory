# 008 — First Complete Program: Personal Expense Manager

## Type
TASK

## Owner
ChatGPT — Factory Manager

## Goal
Build the first complete real application through the AI Software Factory workflow. The benchmark application is a small but production-minded Flutter Personal Expense Manager.

## Mandatory workflow
Requirements → Planner → Architect/UIUX → Developer → Tester → QA → Security → Reviewer → Release.

Each stage must produce evidence. A task cannot be marked DONE without evidence.

## Product requirements
Build a Flutter mobile app with:
- Dashboard showing total balance, income, expenses, and recent transactions.
- Add/Edit/Delete transaction.
- Transaction fields: amount, type (income/expense), category, date, note.
- Categories with a useful default set.
- Search/filter transactions.
- Local persistence so data survives app restart.
- Input validation and friendly empty/error states.
- Clean responsive UI suitable for phone screens.
- Arabic + English-ready text structure; English UI is acceptable for the benchmark.
- No external paid services required.

## Engineering requirements
- Flutter/Dart.
- Keep architecture maintainable and reasonably modular.
- Use local storage with a stable package or a simple reliable local persistence layer.
- Add unit/widget tests for core CRUD, validation, filtering, and important UI behavior.
- README with setup, run, test, architecture, and known limitations.
- Dependency/security review before release.
- No secrets in repository.
- Do not claim tests passed without actual evidence.

## Repository requirements
The generated application must be pushed to a new private GitHub repository under the owner's GitHub account. Do not make it public.
Repository name: personal-expense-manager.

## Release requirements
Before release:
1. Full factory test suite passes.
2. Generated app tests pass.
3. QA verifies acceptance criteria.
4. Security/dependency review is recorded.
5. Reviewer confirms no blocking issues.
6. Release employee prepares the final artifact/README.
7. Railway deployment is attempted only after the above gates pass.

## Failure handling
If a stage fails:
- Record the failure and evidence.
- Create/update a follow-up fix task.
- Do not mark the failed task DONE.
- Re-run the relevant tests after the fix.

## Final evidence required
- GitHub private repository URL.
- Commit SHA(s).
- Test commands and exact results.
- QA report.
- Security/dependency report.
- Final release artifact or build evidence.
- Railway deployment ID/status if deployed.
- Summary of any known limitations.

## Manager rule
Work one stage/task at a time. Do not skip gates just to produce a demo.

## Claude handoff
Claude is optional for this task. If Claude is unavailable, the Factory's available employee execution path must still process the task.

## Created
2026-09-26
