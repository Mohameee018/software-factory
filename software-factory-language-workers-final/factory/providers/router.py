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

    def _run(self, method, *args, **kwargs):
        attempts=[]; quota_models=[]; last_error=None
        for spec in self.parent.specs_for(self.role):
            label=spec['label']; attempts.append(label)
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
                    self.parent._notify(self.role, label, 'failed')
        self.last_attempts=attempts
        if attempts and len(quota_models)==len(attempts):
            raise AIQuotaExhausted(self.role, attempts, self.parent.next_quota_time())
        raise RuntimeError('MODEL_FAILOVER_EXHAUSTED role=%s attempts=%s last_error=%s' % (self.role, ','.join(attempts), str(last_error)[:1000]))

    def generate_json(self, system, prompt, schema, *, timeout=None, images=None):
        return self._run('generate_json', system, prompt, schema, timeout=timeout, images=images)

    def generate(self, system, prompt, *, timeout=None):
        return self._run('generate', system, prompt, timeout=timeout)

class ModelRouter:
    def __init__(self, settings, notifier=None):
        self.settings, self.notifier = settings, notifier
        self._providers={}

    def for_role(self, role):
        return RoleRouter(self, role)

    def _default_spec(self):
        return {'provider': self.settings.provider, 'model': self.settings.model, 'label': f'{self.settings.provider}:{self.settings.model}'}

    def specs_for(self, role):
        key='AI_MODELS_'+re.sub(r'[^A-Z0-9]', '_', role.upper())
        raw=os.getenv(key,'').strip()
        specs=[]
        if raw:
            for item in raw.split(','):
                if ':' not in item: continue
                provider,model=item.split(':',1); provider,model=provider.strip().lower(),model.strip()
                if provider and model: specs.append({'provider':provider,'model':model,'label':f'{provider}:{model}'})
        if not specs: specs=[self._default_spec()]
        global_raw=os.getenv('AI_MODELS','').strip()
        if global_raw:
            for item in global_raw.split(','):
                if ':' not in item: continue
                provider,model=item.split(':',1); provider,model=provider.strip().lower(),model.strip()
                label=f'{provider}:{model}'
                if provider and model and not any(x['label']==label for x in specs):
                    specs.append({'provider':provider,'model':model,'label':label})
        return specs

    def provider_for(self, spec):
        key=(spec['provider'],spec['model'])
        if key not in self._providers:
            self._providers[key]=build_provider_for_spec(self.settings,spec['provider'],spec['model'])
        return self._providers[key]

    def is_quota_error(self, exc):
        text=str(exc).upper()
        return any(x in text for x in ('RESOURCE_EXHAUSTED','QUOTA EXCEEDED','FREE_TIER_REQUESTS','GENERATE_CONTENT_FREE_TIER_REQUESTS','DAILY QUOTA','RPD'))

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
