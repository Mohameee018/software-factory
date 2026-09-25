# Security

## Trust boundary

LLM output is untrusted input. The Developer can only use the structured actions accepted by `DeveloperAgent`, write through `WorkspaceFS`, and execute commands through the controlled shell.

## Workspace isolation

All file paths are resolved canonically and must remain under the project workspace. Path traversal and workspace escape attempts are rejected.

## Shell safety

The controlled shell uses `shell=False`, an allowlist, timeout handling, and rejects common shell operators. Developer dependency-install commands such as `flutter pub get`, `pip install`, `npm install`, and `dart pub get` are blocked unless the workflow reaches the ApprovalService path.

## Dependencies

Dependency installation can change the execution environment or introduce untrusted code. The Factory therefore requires explicit human approval for `flutter pub get` in the Flutter workflow.

## Secrets

- Put API keys and Telegram tokens in environment variables or `.env`.
- Never commit `.env`.
- Provider errors redact the configured API key.
- Do not include credentials in project requirements or generated source files.

## Telegram

If both Telegram allowlists are empty, access is denied. Approval records are persisted in SQLite and are resolved atomically so already-resolved approvals cannot be replayed.

## Generated code execution

The Factory is **not an OS sandbox**. Generated code runs with the privileges of the Python process that launches the Factory. For untrusted workloads, run the Factory or generated project inside an external container/VM/sandbox with restricted filesystem, network, and OS permissions.

## Release checklist

- No API keys, Telegram tokens, passwords, or secrets in Git.
- `.env`, databases, caches, `.venv`, and generated workspaces excluded from release archives.
- Real Flutter commands only through the controlled shell.
- Real dependency installation only after human approval.
- Review and security gates remain enabled.
