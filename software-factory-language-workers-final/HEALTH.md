# Health and operations

`factory health` checks the persistent database, queue depth, worker/Telegram heartbeats, and AI provider configuration.

For Docker:

```bash
docker compose ps
docker compose logs -f worker
docker compose logs -f bot
```

The worker heartbeat is persisted in SQLite. A heartbeat being present means the service reported in at least once; it is not a substitute for an external liveness probe. For production, combine the command with Docker restart policy and host/container monitoring.

## Production health output

`factory health` reports:

- Database
- Queue size
- Telegram heartbeat
- Python worker heartbeat
- Node worker heartbeat
- Java worker heartbeat
- Flutter worker heartbeat
- AI provider configuration

A language environment is considered healthy when its dedicated worker heartbeat is fresh. `NOT REQUIRED/NOT REPORTED` is not a claim that the SDK is installed on the current CLI host; it means the corresponding worker service has not reported from that environment.
