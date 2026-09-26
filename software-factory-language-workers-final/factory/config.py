from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

def _csv_int(value):
    return {int(x.strip()) for x in value.split(',') if x.strip()}

def _role_limits(value):
    result={}
    for item in str(value or '').split(','):
        role, sep, limit = item.partition(':')
        if sep and role.strip() and limit.strip().isdigit(): result[role.strip().lower()] = int(limit.strip())
    return result or None

def _env_bool(value):
    return str(value).strip().lower() in {'1','true','yes','on'}

@dataclass(frozen=True)
class Settings:
    db_path: Path; workspaces_root: Path; log_level: str; provider: str; model: str; api_key: str|None
    max_retries: int = 3; max_iterations: int = 30; command_timeout: int = 120
    api_base_url: str = 'https://api.openai.com/v1'
    telegram_bot_token: str|None = None; telegram_allowed_user_ids: set[int]|None = None; telegram_allowed_chat_ids: set[int]|None = None
    telegram_enabled: bool = False; telegram_notification_level: str = 'important'
    github_token: str|None = None; github_owner: str|None = None; github_enabled: bool = False; github_auto_sync: bool = True
    mode: str = 'auto'; ai_timeout: int = 120; database_url: str|None = None; worker_poll_interval: float = 2.0; job_max_retries: int = 5; worker_type: str = 'generic'; max_agent_runs: int = 250; max_project_seconds: int = 0; max_agent_runs_by_role: dict[str,int] | None = None; dashboard_port: int = 8080; dashboard_token: str|None = None
    def __post_init__(self):
        if self.telegram_allowed_user_ids is None: object.__setattr__(self, 'telegram_allowed_user_ids', set())
        if self.telegram_allowed_chat_ids is None: object.__setattr__(self, 'telegram_allowed_chat_ids', set())
    def ensure_directories(self):
        self.db_path.parent.mkdir(parents=True,exist_ok=True); self.workspaces_root.mkdir(parents=True,exist_ok=True)

def load_settings():
    provider=os.getenv('AI_PROVIDER') or os.getenv('FACTORY_LLM_PROVIDER','mock').lower()
    key=os.getenv('AI_API_KEY') or os.getenv('FACTORY_API_KEY') or os.getenv('OPENAI_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    model = os.getenv('AI_MODEL') or os.getenv('FACTORY_MODEL','gpt-4o-mini')
    # Gemini 2.5 Flash has been retired for new users. Keep existing Railway
    # deployments self-healing by transparently moving the legacy setting to
    # the current stable Flash model instead of retrying a permanent 404.
    if model.strip().lower() == 'gemini-2.5-flash':
        model = 'gemini-3.8-flash'
    return Settings(
      Path(os.getenv('DATABASE_PATH') or os.getenv('FACTORY_DB_PATH','./factory.db')).resolve(), Path(os.getenv('WORKSPACE_PATH') or os.getenv('FACTORY_WORKSPACES_ROOT','./workspaces')).resolve(),
      os.getenv('FACTORY_LOG_LEVEL','INFO').upper(), provider, model, key,
      int(os.getenv('MAX_RETRIES') or os.getenv('FACTORY_MAX_RETRIES','3')), int(os.getenv('MAX_WORKFLOW_ITERATIONS') or os.getenv('FACTORY_MAX_ITERATIONS','30')), int(os.getenv('COMMAND_TIMEOUT') or os.getenv('FACTORY_COMMAND_TIMEOUT','120')),
      os.getenv('AI_BASE_URL') or os.getenv('FACTORY_API_BASE_URL','https://api.openai.com/v1'), os.getenv('TELEGRAM_BOT_TOKEN'), _csv_int(os.getenv('TELEGRAM_ALLOWED_USER_IDS','')),
      _csv_int(os.getenv('TELEGRAM_ALLOWED_CHAT_IDS','')), _env_bool(os.getenv('TELEGRAM_ENABLED','false')),
      os.getenv('TELEGRAM_NOTIFICATION_LEVEL','important').lower(), os.getenv('GITHUB_TOKEN'), os.getenv('GITHUB_OWNER'), _env_bool(os.getenv('GITHUB_ENABLED', 'true' if os.getenv('GITHUB_TOKEN') else 'false')), _env_bool(os.getenv('GITHUB_AUTO_SYNC','true')), os.getenv('FACTORY_MODE','real' if provider != 'mock' else 'mock').lower(),
      int(os.getenv('AI_TIMEOUT') or os.getenv('FACTORY_AI_TIMEOUT') or os.getenv('COMMAND_TIMEOUT') or '120'),
      os.getenv('DATABASE_URL'), float(os.getenv('WORKER_POLL_INTERVAL','2')), int(os.getenv('JOB_MAX_RETRIES','5')), os.getenv('WORKER_TYPE','generic').lower(), int(os.getenv('MAX_AGENT_RUNS','250')), int(os.getenv('MAX_PROJECT_SECONDS','0')), _role_limits(os.getenv('MAX_AGENT_RUNS_BY_ROLE','')), int(os.getenv('DASHBOARD_PORT','8080')), os.getenv('DASHBOARD_TOKEN'))
_settings=None
def get_settings():
    global _settings
    if _settings is None: _settings=load_settings()
    return _settings
