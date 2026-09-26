from __future__ import annotations
import os, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from factory.providers.registry import build_provider_for_spec

class AIQuotaExhausted(RuntimeError):
    def __init__(self, role, models, resume_at):
        self.role, self.models, self.resume_at = role, models, resume_at
        super().__init__(f"AI_QUOTA_EXHAUSTED role={role} resume_at={resume_at.isoformat()} models={','.join(models)}")

class RoleRouter:
    def __init__(self, parent, role):
        self.parent, self.role = parent, role
        self.last_model = None
        self.last_attempts = []
        self.last_skipped = []

    def _failed_models(self):
        if not self.parent.project_id or not self.parent.db:
            return set()
        state = self.parent.db.get_state(self.parent.project_id)
        return set(state.failed_models_by_role.get(self.role, []) if state else [])

    def _record_failure(self, label):
        pid = self.parent.project_id
        if not pid or not self.parent.db:
            return
        state = self.parent.db.get_state(pid)
        if not state:
            return
        models = state.failed_models_by_role.setdefault(self.role, [])
        if label not in models:
            models.append(label)
            self.parent.db.save_state(state)
        try:
            from factory.models import WorkflowEvent
            self.parent.db.event(WorkflowEvent(project_id=pid,event_type='MODEL_FAILED_FOR_PROJECT',details={'role': self.role, 'model': label}))
        except Exception:
            pass


    @property
    def is_mock(self):
        return self.parent.settings.mode in ('mock','dry-run') or all(x['provider']=='mock' for x in self.parent.specs_for(self.role))

    def _run(self, method, *args, **kwargs):
        attempts=[]; quota_models=[]; last_error=None
        failed_models = self._failed_models()
        self.last_skipped = []
        for spec in self.parent.specs_for(self.role):
            label=spec['label']
            if label in failed_models:
                self.last_skipped.append(label)
                continue
            attempts.append(label)
            self.parent._notify(self.role, label, 'attempt')
            try:
                provider=self.parent.provider_for(spec)
                result=getattr(provider, method)(*args, **kwargs)
                self.last_model=label; self.last_attempts=attempts
                self.parent._notify(self.role, label, 'success')
                return result
            except Exception as exc:
                last_error=exc
                if self.parent.is_quota_error(exc):
                    quota_models.append(label)
                    self.parent._notify(self.role, label, 'quota')
                else:
                    self._record_failure(label)
                    self.parent._notify(self.role, label, 'failed')
        self.last_attempts=attempts
        if attempts and len(quota_models)==len(attempts):
            raise AIQuotaExhausted(self.role, attempts, self.parent.next_quota_time())
        raise RuntimeError('MODEL_FAILOVER_EXHAUSTED role=%s attempts=%s skipped=%s last_error=%s' % (self.role, ','.join(attempts), ','.join(self.last_skipped), str(last_error)[:1000]))

    def generate_json(self, system, prompt, schema, *, timeout=None, images=None):
        return self._run('generate_json', system, prompt, schema, timeout=timeout, images=images)

    def generate(self, system, prompt, *, timeout=None):
        return self._run('generate', system, prompt, timeout=timeout)

class ModelRouter:
    def __init__(self, settings, notifier=None, db=None):
        self.settings, self.notifier, self.db = settings, notifier, db
        self.project_id = None
        self._providers={}

    def set_project_context(self, project_id):
        self.project_id = project_id

    def for_role(self, role):
        return RoleRouter(self, role)

    def _default_spec(self):
        return {'provider': self.settings.provider, 'model': self.settings.model, 'label': f'{self.settings.provider}:{self.settings.model}'}

    def specs_for(self, role):
        key='AI_MODELS_'+re.sub(r'[^A-Z0-9]', '_', role.upper())
        raw=os.getenv(key,'').strip()
        specs=[]
        def add_item(item):
            item=item.strip()
            if not item: return
            if ':' in item:
                provider,model=item.split(':',1)
                provider,model=provider.strip().lower(),model.strip()
            else:
                model=item
                low=model.lower()
                if low.startswith('gpt-5-codex') or low.startswith('gpt-5.1-codex') or low.startswith('gpt-5.2-codex'): provider='codex'
                elif low.startswith('gpt-oss-') or low.startswith('openai/gpt-oss-'): provider='groq'
                elif low.startswith('gpt-'): provider='openai'
                elif low.startswith('gemini-'): provider='gemini'
                elif low.startswith('claude-'): provider='anthropic'
                else: provider=str(self.settings.provider).strip().lower()
            if provider and model:
                label=f'{provider}:{model}'
                if not any(x['label']==label for x in specs):
                    specs.append({'provider':provider,'model':model,'label':label})
        if raw:
            for item in raw.split(','): add_item(item)
        if not specs:
            specs=[self._default_spec()]
            # If no role-specific pool was configured, build a safe automatic
            # failover pool from credentials already present in the deployment.
            # Never introduce a paid provider unless its API key is already set.
            base_url=str(self.settings.api_base_url).lower()
            current_provider=str(self.settings.provider).strip().lower()
            if current_provider == 'openai-compatible' and 'generativelanguage.googleapis.com' in base_url:
                # Gemini Flash models use the same OpenAI-compatible endpoint and
                # key, while different model buckets can have independent limits.
                for model_name in (
                    'gemini-3.7-flash',
                    'gemini-3.6-flash',
                    'gemini-3.5-flash',
                    'gemini-3.5-flash-lite',
                    'gemini-3.1-flash-lite',
                ):
                    add_item(f'openai-compatible:{model_name}')
            # Do not auto-select unrelated providers merely because a key exists.
            # A stale/unused provider key in Railway must not hijack the workflow.
            # Cross-provider failover is opt-in through AI_MODELS / AI_MODELS_<ROLE>.
            # For a Gemini deployment, keep the automatic pool inside Gemini.
        global_raw=os.getenv('AI_MODELS','').strip()
        if global_raw:
            for item in global_raw.split(','): add_item(item)
        return specs

    def provider_for(self, spec):
        key=(spec['provider'],spec['model'])
        if key not in self._providers:
            self._providers[key]=build_provider_for_spec(self.settings,spec['provider'],spec['model'])
        return self._providers[key]

    def is_quota_error(self, exc):
        text=str(exc).upper()
        return any(x in text for x in ('RESOURCE_EXHAUSTED','QUOTA EXCEEDED','FREE_TIER_REQUESTS','GENERATE_CONTENT_FREE_TIER_REQUESTS','DAILY QUOTA','RPD','RATE LIMIT','TOO MANY REQUESTS','429'))

    def next_quota_time(self):
        tz=ZoneInfo(os.getenv('FACTORY_QUOTA_TIMEZONE','Africa/Cairo'))
        raw=os.getenv('FACTORY_QUOTA_RESUME_AT','09:00').strip()
        try: hour,minute=[int(x) for x in raw.split(':',1)]
        except Exception: hour,minute=9,0
        now=datetime.now(tz); target=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if target <= now: target += timedelta(days=1)
        return target

    def _notify(self, role, model, event):
        if not self.notifier: return
        tag={'uiux':'#UIUX','planner':'#PM','analyzer':'#ANALYZER','developer':'#DEV','reviewer':'#REVIEWER','uiux_reviewer':'#UXREVIEW'}.get(role,'#AI')
        try:
            if event=='attempt': self.notifier._send(f'🤖 <b>{tag}</b> المودل الحالي: <code>{model}</code>')
            elif event=='failed': self.notifier._send(f'⚠️ <b>{tag}</b> المودل <code>{model}</code> فشل — تجربة البديل.')
            elif event=='quota': self.notifier._send(f'⏳ <b>{tag}</b> المودل <code>{model}</code> حصته غير متاحة — الانتقال للبديل.')
        except Exception: pass
