from __future__ import annotations
import re
_SECRET = re.compile(r"(?im)^([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|PASSWORD|SECRET)[A-Z0-9_]*\s*[:=]\s*)([^\n]+)$")
_QUOTED = re.compile(r"(?i)(api[_-]?key|password|secret|token)(\s*[:=]\s*[\"\'])([^\"\']+)([\"\'])")
def redact_secrets(text: str) -> str:
    text=_SECRET.sub(lambda m:m.group(1)+'[REDACTED]',text)
    return _QUOTED.sub(lambda m:m.group(1)+m.group(2)+'[REDACTED]'+m.group(4),text)
