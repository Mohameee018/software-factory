from __future__ import annotations

import re
import urllib.error
import urllib.request
import json
from pathlib import Path

from factory.tools.shell import run


class GitFlow:
    """Small, auditable Git/GitHub workflow used by generated projects."""

    def __init__(self, settings):
        self.token = settings.github_token
        self.enabled = bool(settings.github_enabled and self.token)

    @staticmethod
    def branch_name(project_id: str, task_id: str | None = None, kind: str = "work") -> str:
        suffix = re.sub(r"[^a-zA-Z0-9._-]+", "-", (task_id or project_id)).strip("-")
        return f"factory/{kind}/{suffix}"[:120]

    def create_branch(self, workspace: str | Path, branch: str):
        result = run("developer", f'git switch -c "{branch}"', workspace)
        if result.exit_code != 0:
            raise RuntimeError(result.stderr or result.stdout or "git branch creation failed")
        return branch

    def commit_and_push(self, workspace: str | Path, branch: str, message: str):
        status = run("developer", "git status --short", workspace)
        if status.exit_code != 0:
            raise RuntimeError(status.stderr or "git status failed")
        if status.stdout.strip():
            add = run("developer", "git add -A", workspace)
            if add.exit_code != 0:
                raise RuntimeError(add.stderr or "git add failed")
            commit = run(
                "developer",
                f'git commit -m "{message.replace(chr(34), chr(39))}"',
                workspace,
            )
            if commit.exit_code != 0:
                raise RuntimeError(commit.stderr or commit.stdout or "git commit failed")
        push = run("developer", f'git push -u origin "{branch}"', workspace)
        if push.exit_code != 0:
            raise RuntimeError(push.stderr or push.stdout or "git push failed")
        return {"branch": branch, "pushed": True}

    def create_pull_request(self, full_name: str, head: str, base: str = "main",
                            title: str = "Factory change", body: str = ""):
        if not self.enabled:
            raise RuntimeError("GitHub publishing is not configured")
        payload = {"title": title, "head": head, "base": base, "body": body, "draft": True}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{full_name}/pulls",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "software-factory",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub PR API {exc.code}: {detail[:1000]}") from exc
        return {
            "number": result.get("number"),
            "url": result.get("html_url"),
            "draft": bool(result.get("draft", True)),
            "head": head,
            "base": base,
        }
