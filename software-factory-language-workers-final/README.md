# Multi-Agent Autonomous Software Factory — Private Telegram Cloud

A human-supervised software factory that runs on a persistent server instead of the user's PC. Telegram is the control plane; a persistent SQLite-backed queue feeds a background worker; the existing orchestrator, agents, WorkspaceFS, approvals, Git flow and recovery remain the execution core.

## Production architecture

```text
Telegram
   ↓
Private Telegram Bot (allowlist)
   ↓
Command/Service layer
   ↓
Persistent SQLite Job Queue
   ↓
Background Worker (restart policy)
   ↓
Existing Orchestrator
   ↓
Planner → Analyzer → Tasks → Developer → Tester → Reviewer → Security
   ↓
Persistent project state + workspace + audit events
   ↓
Telegram notifications / approval gates
```

The bot never waits for a full project run. `/new`, `/run`, `/resume`, `/retry`, and approved actions enqueue work and return immediately.

## What changed in this cloud conversion

- Persistent `jobs` table with job ID, project/task, priority, timestamps, retries, errors, worker state and lease data.
- Atomic SQLite job claiming using `BEGIN IMMEDIATE`, so two workers cannot claim the same queued job.
- Restart recovery for `RUNNING` jobs and existing `IN_PROGRESS` tasks.
- Persistent Telegram active-project selection per Telegram user.
- Background worker process with graceful SIGTERM/SIGINT handling.
- Telegram bot and worker can run as separate restartable services.
- `/new` and `/run` are asynchronous; they queue work instead of running the factory inside the Telegram update handler.
- Approval resolution re-queues the project automatically.
- Pause/cancel stop pending jobs; resume creates a fresh queued job.
- Worker and Telegram heartbeats are persisted for operational checks.
- `factory health` reports database, queue, service heartbeats and AI configuration status.
- Docker Compose + Dockerfile + PowerShell/bash deployment scripts.
- Existing 66-test suite preserved; cloud architecture adds 7 tests.

## Server requirements

For the baseline server deployment:

- Linux VPS/server
- Docker Engine + Docker Compose plugin
- persistent disk for `/data`
- Telegram bot token
- your Telegram user ID in `TELEGRAM_ALLOWED_USER_IDS`
- real AI provider credentials for non-mock execution
- Git in the worker image (included)

The current repository supports Flutter and Python adapters. Flutter/Dart is **not installed in the generic image**; a production Flutter workload requires a worker image/environment containing the Flutter and Dart SDKs. Do not treat a generic Python worker as a Flutter build environment.

## Configuration

Copy `.env.example` to `.env` and set at minimum:

```env
FACTORY_MODE=real
AI_PROVIDER=openai-compatible
AI_API_KEY=...
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini

TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=123456789

DATABASE_PATH=/data/factory.db
WORKSPACE_PATH=/data/projects
JOB_MAX_RETRIES=5
```

Never commit `.env`.

### Telegram privacy

The bot is deny-by-default. If both allowlists are empty, every Telegram user is rejected. For a private 1:1 Telegram chat, `TELEGRAM_ALLOWED_USER_IDS` is the required identity allowlist; the notifier can use those IDs as chat IDs when `TELEGRAM_ALLOWED_CHAT_IDS` is empty.

## Deploy from zero

1. Install Docker and Docker Compose on the server.
2. Copy the repository to the server.
3. Create `.env` from `.env.example`.
4. Fill the Telegram token, allowed user ID(s), AI provider and persistent paths.
5. Build and start:

```bash
docker compose build
docker compose up -d worker bot
```

Or:

```bash
bash scripts/deploy.sh
```

PowerShell is also available:

```powershell
.\scripts\deploy.ps1
```

6. Verify:

```bash
docker compose ps
factory health
```

`factory health` is an operational snapshot. AI `OK` means configuration is present; it does not mean a live external API call was made. Use `factory ai-smoke` for an explicit provider connectivity check.

## Operations

```bash
docker compose logs -f worker
docker compose logs -f bot
docker compose restart worker bot
docker compose stop worker bot
docker compose up -d worker bot
```

The Docker services use `restart: unless-stopped`, so a process/container crash is restarted by Docker. On restart, the worker reclaims recoverable jobs and the existing orchestrator recovers interrupted tasks from persistent state.

## Telegram workflow

```text
/new
→ describe project
→ project is created and a job is queued
→ bot immediately returns
→ worker executes in background
→ Telegram sends important state changes
→ approval gate can move the job to WAITING_APPROVAL
→ /approve <approval_id> or inline approval
→ a new queued job resumes the project
→ READY_FOR_HUMAN notification
→ /feedback <project_id> <text>
→ new task + queued job
```

Commands remain:

`/start /help /new /projects /project /status /tasks /run /pause /resume /cancel /retry /logs /approve /reject /review /feedback`

## Persistence and recovery

The following are persisted in SQLite:

- projects and FactoryState
- tasks
- approvals
- workflow events
- agent/test/review/security records
- Telegram active-project mapping
- jobs and retry state
- service heartbeats

SQLite is appropriate for a single-server/single-writer deployment. The business layer accesses persistence through `Database`; a future PostgreSQL implementation can replace that layer without changing the orchestrator/agents/Telegram contracts. The current build does **not** claim PostgreSQL support.

## Security

- Telegram allowlist is deny-by-default.
- No secrets are stored in source code.
- WorkspaceFS blocks path traversal and resolved-path escapes.
- Controlled shell rejects dangerous shell operators and dependency installation without approval.
- Telegram does not expose arbitrary shell execution.
- Logs/errors must redact secrets.
- Generated code still executes with worker/container privileges. This is a known security boundary; use a dedicated server/container and do not treat the worker as a hardened sandbox.

See `SECURITY.md` for the existing safety model.

## Testing

Run:

```bash
python -m compileall -q .
pytest -q
```

The current local validation in this environment is 73 passing tests. External Telegram, external AI credentials, and real Flutter SDK execution are not verified here.

## Updating

1. Stop or scale down bot/worker.
2. Replace the code/image.
3. Keep the persistent `/data` volume.
4. Rebuild and start services.
5. Run `factory health` and inspect logs.

Do not delete the persistent volume during an application update.

## Production worker environments

The cloud deployment now routes persistent jobs by deterministic project type:

- `FLUTTER` → `worker-flutter` (Flutter/Dart SDK)
- `JAVA` → `worker-java` (JDK 21 + Maven + Gradle)
- `NODE` → `worker-node` (Node 22)
- `PYTHON` → `worker-python` (Python 3.12)
- `UNKNOWN` → blocked safely; no arbitrary worker is selected.

Workspace-file detection is authoritative once files exist. Priority is deterministic: Flutter, Java, Node, Python.

Each worker image contains only its relevant language runtime plus the factory runtime. Jobs persist their `worker_type` in SQLite and workers claim only matching jobs.

## Production commands

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f
```

To restart without deleting persistent data:

```bash
docker compose restart
```

To stop services while preserving the named volume:

```bash
docker compose down
```

Persistent database and project workspaces are stored in the `factory_data` Docker volume under `/data`.

## Backup

Back up both `/data/factory.db` and `/data/projects`. The deployment documentation includes a simple volume-copy procedure; do not delete the live volume as part of backup.

## Important verification status

The repository contains the production deployment configuration, but a repository build/configuration is not the same as an external production verification. Real Telegram credentials, a real AI key, and a running Docker/VPS environment are required for final external smoke testing.
