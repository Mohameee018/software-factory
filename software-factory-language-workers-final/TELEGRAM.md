# Private Telegram Bot

## User flow

1. Create a Bot with BotFather and obtain the token.
2. Find your numeric Telegram user ID.
3. Put the ID in `TELEGRAM_ALLOWED_USER_IDS`.
4. Set `TELEGRAM_ENABLED=true` and `TELEGRAM_BOT_TOKEN`.
5. Deploy the bot and worker services.
6. Send `/start`.

## Authorization

Authorization is deny-by-default. A user is accepted only when their Telegram user ID is in the configured allowlist (and, if configured, their chat ID also passes the chat allowlist). Unauthorized users receive only `Unauthorized.`.

No project IDs, logs, state, workspace paths or error details are exposed before authorization.

## Background execution

`/new` and `/run` create persistent queue jobs and return immediately. The worker executes the project independently of the Telegram client being open.

## Persistent active project

The active project is stored in SQLite by Telegram user ID. The bot also keeps the in-memory `context.user_data` value for convenience, but the database is authoritative after reconnect/restart/device changes.

## Approvals

Both forms are supported:

```text
/approve <approval_id>
/reject <approval_id>
```

or, when exactly one pending approval is relevant to the project:

```text
/approve <project_id>
/reject <project_id>
```

Inline approval buttons are also supported. An approved action creates a new high-priority background job rather than running the factory inside the Telegram update.

## Operational commands

`/status`, `/tasks`, `/logs`, `/project`, `/review` read persistent state. `/pause` cancels pending queue work safely; `/resume` queues the project again. `/cancel` cancels pending jobs and moves the project to `CANCELLED`.

Telegram is an interface, not the source of truth. A Telegram outage does not delete factory state or jobs.
