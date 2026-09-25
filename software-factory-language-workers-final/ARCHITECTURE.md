# Cloud Architecture

## Processes

### Bot service
Owns Telegram polling and authentication. It does not execute long-running factory runs. Commands create/read/update persistent state and enqueue jobs.

### Worker service
Claims persistent jobs atomically, invokes the existing Orchestrator, records completion/failure/retry state, and exits cleanly on SIGTERM/SIGINT.

### Persistence
SQLite stores projects, FactoryState, tasks, approvals, workflow events, jobs, Telegram active-project sessions and service heartbeats. `Database` is the persistence boundary.

## Job lifecycle

`PENDING → RUNNING → COMPLETED`

or:

`RUNNING → RETRYING → RUNNING`

or:

`RUNNING → WAITING_APPROVAL → PENDING/RUNNING`

or:

`RUNNING → FAILED/CANCELLED`

A worker restart changes abandoned `RUNNING` jobs to recoverable states. The orchestrator independently recovers `IN_PROGRESS` tasks.

## Concurrency

SQLite uses `BEGIN IMMEDIATE` for job claiming. The selected job is changed to `RUNNING` in the same transaction, preventing duplicate claims across worker processes.

The design intentionally keeps one active worker as the simple production baseline. The queue is safe for multiple claimers, but the workflow itself should be load-tested before horizontally scaling workers.

## Server filesystem

The persistent Docker volume is mounted at `/data`:

```text
/data/factory.db
/data/projects/<project-id>/
```

The generic worker image contains Python and Git. Language-specific SDKs must be supplied by the corresponding worker environment/image before those project types are run.

## Telegram state

Active project selection is persisted by Telegram user ID. This means changing phone/desktop does not lose the selected project.

## Notifications

The existing orchestrator notifier is reused. Important state transitions and approval/ready events are sent to the private allowlisted Telegram chat(s). The worker can notify without a running Telegram process by calling the Bot API directly.

## Health

`factory health` reads service heartbeats and queue state. It intentionally does not perform an external AI request. `factory ai-smoke` is the explicit provider connectivity test.

## Language-specific worker routing

Persistent jobs carry `worker_type`. The queue atomically claims only jobs matching the worker service's `WORKER_TYPE`. This preserves the existing queue/orchestrator architecture while preventing a Node job from being consumed by a Python/Flutter worker.

Project type is detected deterministically from workspace files when available:
`pubspec.yaml`, Maven/Gradle files, `package.json`, then Python packaging files. Natural-language detection remains only the initial `/new` fallback.

Unknown projects are blocked rather than sent to an arbitrary runtime.
