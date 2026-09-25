from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from factory.agents.base import Agent
from factory.models import AgentResult


class ReleaseAgent(Agent):
    name = "Release Agent"
    role = "release"
    instructions = (
        "Prepare a safe, reproducible release package after final human approval. "
        "Never include secrets, .git metadata, caches, or the release output itself."
    )

    _EXCLUDED_DIRS = {
        ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
        "node_modules", "build", ".dart_tool",
    }
    _EXCLUDED_NAMES = {".env", ".env.local", ".env.production"}

    def run(self, context, task=None):
        root = Path(context.workspace).resolve()
        release_dir = root / "release"
        release_dir.mkdir(parents=True, exist_ok=True)
        package = release_dir / f"{context.project.id}-release.zip"
        manifest_path = release_dir / "RELEASE_MANIFEST.json"

        files = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in self._EXCLUDED_DIRS for part in rel.parts):
                continue
            if path.name in self._EXCLUDED_NAMES or path.suffix in {".pyc", ".pyo"}:
                continue
            if rel.parts and rel.parts[0] == "release":
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append({
                "path": rel.as_posix(),
                "size": path.stat().st_size,
                "sha256": digest,
            })

        files.sort(key=lambda x: x["path"])
        manifest = {
            "project_id": context.project.id,
            "project_name": context.project.name,
            "project_type": context.project.project_type.value,
            "git_branch": context.project.git_branch,
            "file_count": len(files),
            "files": files,
            "exclusions": sorted(self._EXCLUDED_DIRS | self._EXCLUDED_NAMES),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in files:
                archive.write(root / item["path"], item["path"])
            archive.write(manifest_path, "RELEASE_MANIFEST.json")

        summary = f"Release package created: release/{package.name} ({len(files)} files)."
        return AgentResult(
            success=True,
            agent_name=self.name,
            summary=summary,
            detailed_output={
                "package": str(package.relative_to(root)),
                "manifest": str(manifest_path.relative_to(root)),
                "file_count": len(files),
            },
            files_created=[str(package.relative_to(root)), str(manifest_path.relative_to(root))],
            next_action="complete",
        )
