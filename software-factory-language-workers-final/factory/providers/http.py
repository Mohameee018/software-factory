from __future__ import annotations
import json, time, urllib.error, urllib.request
from factory.providers.base import AIProvider, LLMResponse

class HTTPProvider(AIProvider):
    def __init__(self, api_key: str, model: str, base_url: str, timeout: int = 120, max_retries: int = 3):
        if not api_key or not api_key.strip(): raise ValueError('API key is required')
        if not model or not model.strip(): raise ValueError('AI model is required')
        if not base_url or not base_url.strip(): raise ValueError('AI base URL is required')
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip('/')
        self.timeout, self.max_retries = max(1, int(timeout)), max(0, int(max_retries))

    def _safe_error(self, text: str) -> str:
        text = (text or '').replace(self.api_key, '[REDACTED]')
        return text[:1000]

    def _request(self, url: str, body: dict, headers: dict[str, str], timeout: int | None):
        payload = json.dumps(body).encode()
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                detail = e.read().decode('utf-8', 'replace')
                if e.code in (408, 409, 429) or e.code >= 500:
                    if attempt < self.max_retries:
                        time.sleep(min(2 ** attempt, 8)); continue
                # Never echo credentials from request headers/body.
                raise RuntimeError(f'AI provider HTTP {e.code}: {self._safe_error(detail)}') from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8)); continue
                raise RuntimeError(f'AI provider connection error: {type(e).__name__}') from e

class OpenAICompatibleProvider(HTTPProvider):
    def generate(self, system, prompt, *, timeout=None):
        body = {'model': self.model, 'messages': [{'role':'system','content':system},{'role':'user','content':prompt}]}
        data = self._request(f'{self.base_url}/chat/completions', body, {'Authorization': f'Bearer {self.api_key}', 'Content-Type':'application/json'}, timeout)
        choice = (data.get('choices') or [{}])[0]
        msg = choice.get('message') or {}
        usage = data.get('usage') or {}
        self.last_usage = usage
        return LLMResponse(msg.get('content') or '', data.get('model', self.model), usage.get('prompt_tokens'), usage.get('completion_tokens'), data)

    def generate_json(self, system, prompt, schema, *, timeout=None, images=None):
        # Prefer native JSON-object response format, with schema instructions retained for broad model compatibility.
        if images:
            user_content=[{'type':'text','text':prompt + '\nJSON schema:\n' + json.dumps(schema)}]
            user_content += [{'type':'image_url','image_url':{'url':'data:%s;base64,%s' % (x['mime_type'],x['data'])}} for x in images]
            body={'model':self.model,'messages':[{'role':'system','content':system},{'role':'user','content':user_content}], 'response_format': {'type':'json_object'}}
        else:
            body = {'model': self.model, 'messages': [{'role':'system','content':system},{'role':'user','content':prompt + '\nJSON schema:\n' + json.dumps(schema)}], 'response_format': {'type':'json_object'}}
        data = self._request(f'{self.base_url}/chat/completions', body, {'Authorization': f'Bearer {self.api_key}', 'Content-Type':'application/json'}, timeout)
        text = ((data.get('choices') or [{}])[0].get('message') or {}).get('content')
        if isinstance(text, dict):
            return self.validate_structured(text, schema)
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Provider returned empty structured output')
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Provider returned invalid structured JSON: {text[:500]}') from exc
        return self.validate_structured(value, schema)

class AnthropicProvider(HTTPProvider):
    def generate(self, system, prompt, *, timeout=None):
        body = {'model': self.model, 'max_tokens': 8192, 'system': system, 'messages': [{'role':'user','content':prompt}]}
        data = self._request(f'{self.base_url}/messages', body, {'x-api-key':self.api_key,'anthropic-version':'2023-06-01','content-type':'application/json'}, timeout)
        text = ''.join(x.get('text','') for x in data.get('content',[]) if x.get('type')=='text')
        usage = data.get('usage') or {}
        self.last_usage = usage
        return LLMResponse(text, data.get('model', self.model), usage.get('input_tokens'), usage.get('output_tokens'), data)
