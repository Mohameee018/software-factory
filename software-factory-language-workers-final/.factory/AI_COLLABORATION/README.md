# AI Collaboration Hub

This folder is the shared communication channel between AI coding agents working on the Software Factory.

## Roles

- **ChatGPT**: architecture, orchestration, QA, debugging, integration, verification, and task definition.
- **Claude**: implementation, deep code review, refactoring, debugging, and verification.
- **Human owner**: final authority for product decisions and production-risk changes.

## Communication protocol

Never edit the other agent's message files.

### Incoming task format

ChatGPT writes:
`CHATGPT_TO_CLAUDE/<number>_<type>_<short-name>.md`

Claude replies:
`CLAUDE_TO_CHATGPT/<number>_<type>_<short-name>.md`

Use increasing numbers so the conversation is chronological.

Allowed types:
- `TASK` - implementation request
- `BUG` - reproducible problem
- `IDEA` - proposed improvement
- `NOTE` - observation or context
- `REVIEW` - review request
- `VERIFY` - verification request

## Required reply structure

Claude should state:
1. Status: DONE / PARTIAL / BLOCKED
2. What was changed
3. Files changed
4. Tests/checks run
5. Evidence/results
6. Remaining risks or next action
7. Commit SHA and branch, when applicable

ChatGPT follows the same structure when replying to Claude.

## Safety rules

- Do not put API keys, Telegram bot tokens, passwords, cookies, or other secrets in this folder.
- Do not silently change production credentials or security settings.
- Prefer a feature/fix branch and pull request for substantial changes.
- Do not claim a test passed without evidence.
- If a request is ambiguous or unsafe, write a BLOCKED reply explaining exactly what is needed.

## Conversation lifecycle

1. One agent writes a message.
2. The other agent reads it and responds with a new message file.
3. Each response references the previous message filename.
4. For code changes, include commit SHA and verification evidence.
5. The next task can reference any previous message by filename.

The folder is intentionally plain Markdown so Claude Code, ChatGPT, CI, and other agents can all read/write it.
