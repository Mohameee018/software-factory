from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime, timezone

def _path(root,user_id):
    p=Path(root)/"memory"/"users"/str(user_id); p.mkdir(parents=True,exist_ok=True); return p/"MEMORY.md"

def load_user_memory(root,user_id):
    p=_path(root,user_id)
    return p.read_text(encoding="utf-8",errors="ignore") if p.exists() else ""

def save_user_memory(root,user_id,content):
    p=_path(root,user_id)
    p.write_text(content[:30000],encoding="utf-8")
    return str(p)

def update_user_memory(root,user_id,conversation,provider,timeout):
    current=load_user_memory(root,user_id)
    schema={"type":"object","properties":{"memory":{"type":"string"}},"required":["memory"]}
    prompt=f"""Existing user memory:
{current[-16000:]}

Recent conversation:
{conversation[-12000:]}

Update only durable, useful preferences about how this client communicates or works.
Do not store secrets, tokens, passwords, financial data or sensitive personal information.
Do not store temporary project requirements as permanent user preferences.
Return concise markdown memory."""
    try:
        data=provider.generate_json("Maintain concise durable user preferences.",prompt,schema,timeout=timeout)
        return save_user_memory(root,user_id,data.get("memory",current))
    except Exception:
        return save_user_memory(root,user_id,current) if current else ""
