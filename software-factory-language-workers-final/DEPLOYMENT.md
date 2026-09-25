# Production Deployment

## 1. Server

Use a dedicated Linux VPS/server with Docker Engine and the Docker Compose plugin. Keep the Docker volume on persistent storage.

## 2. Secrets

Create `.env` from `.env.example` and set:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS`
- `AI_API_KEY`
- AI provider/model/base URL

Do not put these values into Git, Dockerfile, compose YAML, or application source.

## 3. Start

```bash
docker compose build
docker compose up -d worker bot
docker compose ps
```

## 4. Verify

```bash
docker compose logs --tail=100 worker
docker compose logs --tail=100 bot
```

Then use Telegram `/start` from an allowlisted account.

## 5. Stop / restart

```bash
docker compose stop worker bot
docker compose up -d worker bot
```

Never remove the `factory_data` volume when you want to preserve projects/tasks/jobs.

## 6. Update

Pull the new code, rebuild the image, and recreate services while preserving the volume:

```bash
docker compose build
docker compose up -d worker bot
```

## 7. Recovery

If the worker crashes, Docker restarts it. On startup it converts abandoned running jobs into recoverable jobs and the orchestrator recovers interrupted tasks. Approval rows remain pending in SQLite.

## 8. External verification still required

A deployment is not considered externally verified until the operator has supplied a real Telegram token, real AI credentials, a server, and the required SDK environment for the project types they intend to build.

## Language worker deployment

The Compose deployment runs one Telegram service and four small, language-specific worker services. They share the persistent factory data volume because queue/database state is centralized, while each worker image contains only its required SDK/runtime.

Current pinned image families:

- Bot: Python 3.12.8 slim
- Python worker: Python 3.12.8 slim
- Node worker: Node 22.23 bookworm slim
- Java worker: Gradle 8.14.5 + JDK 21, with Maven installed
- Flutter worker: Cirrus Labs Flutter 3.44.0

The Flutter image source currently publishes a 3.44.0 stable image; its upstream repository notes image publishing changes after May 1, 2026, so pin/replace that image as part of normal dependency maintenance.

Node 22.23 bookworm-slim and the Java/Gradle 8.14.5 JDK 21 image are current tagged images used by this deployment configuration.

## First deployment

1. Install Docker Engine + Compose on the Linux server.
2. Copy the repository to the server.
3. Copy `.env.example` to `.env`.
4. Set the real AI provider credentials and private Telegram allowlist.
5. Validate the Compose file:

```bash
docker compose config
```

6. Build and start:

```bash
docker compose build
docker compose up -d
docker compose ps
```

7. Inspect startup:

```bash
docker compose logs -f bot
docker compose logs -f worker-python
docker compose logs -f worker-node
docker compose logs -f worker-java
docker compose logs -f worker-flutter
```

8. Health from the bot container:

```bash
docker compose exec -T bot factory health
```

## Restart / recovery

`restart: unless-stopped` restarts crashed containers. SQLite WAL + persistent queue state survives container restarts. Jobs left RUNNING are recovered by the next worker startup; in-progress tasks are recovered by the existing orchestrator recovery path.

## Backup

At minimum preserve:

- `/data/factory.db`
- `/data/projects/`

A simple backup can be made by copying the Docker volume contents to a timestamped host directory. Never remove the live volume as part of the backup operation.

## Update

```bash
git pull
docker compose build
docker compose up -d
```

The named data volume is not removed by this update procedure.
