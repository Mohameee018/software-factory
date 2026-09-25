# Development

## Local setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

For offline/CI validation where build dependencies are already installed, `pip install -e . --no-build-isolation --no-deps` can be used.

## Verification

```powershell
pytest -q
python -m compileall -q .
factory doctor
factory ai-smoke
```

Normal tests must not require network access, API credentials, Telegram, or Flutter SDK. Use fake providers/adapters for deterministic integration tests. Real-provider smoke tests may be run manually with explicit credentials.

## Adding an adapter

Implement `ProjectAdapter` in `factory/adapters/` and register it in `factory/adapters/registry.py`. Keep command execution behind `factory.tools.shell`.

## Adding an agent

Implement `Agent`, use a structured provider schema, and return `AgentResult`. File writes must go through `WorkspaceFS`. Do not expose unrestricted shell access to the agent.

## Release verification

Before packaging:

1. Run the full test suite.
2. Run `python -m compileall -q .`.
3. Run `python main.py --help` and `factory --help` when the package is installed.
4. Run `factory doctor`.
5. Run `factory ai-smoke` only when a real provider is intentionally configured.
6. If Flutter is installed, run the real Flutter integration test separately from unit tests.
7. Confirm `.env`, databases, caches, virtual environments, and generated workspaces are excluded from the release archive.
