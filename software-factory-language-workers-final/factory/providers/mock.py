from __future__ import annotations
import json
from factory.providers.base import AIProvider, LLMResponse

class MockProvider(AIProvider):
    is_mock = True
    def __init__(self, model='mock'): self.model = model
    def generate(self, system: str, prompt: str, *, timeout: int | None = None) -> LLMResponse:
        return LLMResponse('MOCK_PROVIDER_RESPONSE', self.model)
    def generate_json(self, system: str, prompt: str, schema: dict, *, timeout: int | None = None, images=None) -> dict:
        props = schema.get('properties', {})
        out = {}
        for key, spec in props.items():
            typ = spec.get('type')
            if typ == 'array': out[key] = []
            elif typ == 'object': out[key] = {}
            elif typ == 'boolean': out[key] = True
            else: out[key] = ''
        if 'success' in props: out['success'] = True
        return out
