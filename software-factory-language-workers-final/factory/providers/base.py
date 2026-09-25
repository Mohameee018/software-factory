from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

class AIProvider(ABC):
    last_usage: dict = {}
    @abstractmethod
    def generate(self, system: str, prompt: str, *, timeout: int | None = None) -> LLMResponse: ...

    @staticmethod
    def validate_structured(value: Any, schema: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError('Structured provider output must be a JSON object')
        required = schema.get('required', []) if isinstance(schema, dict) else []
        missing = [k for k in required if k not in value]
        if missing:
            raise ValueError(f"Structured provider output missing required fields: {', '.join(missing)}")

        def check(value, spec, path):
            if not isinstance(spec, dict): return
            typ = spec.get('type')
            if typ == 'string' and not isinstance(value, str): raise ValueError(f"Field {path!r} must be a string")
            if typ == 'boolean' and not isinstance(value, bool): raise ValueError(f"Field {path!r} must be a boolean")
            if typ == 'array':
                if not isinstance(value, list): raise ValueError(f"Field {path!r} must be an array")
                item_spec = spec.get('items')
                if item_spec:
                    for i, item in enumerate(value): check(item, item_spec, f'{path}[{i}]')
            if typ == 'object':
                if not isinstance(value, dict): raise ValueError(f"Field {path!r} must be an object")
                for key, child in spec.get('properties', {}).items():
                    if key in value: check(value[key], child, f'{path}.{key}')
                for key in spec.get('required', []):
                    if key not in value: raise ValueError(f"Field {path!r} missing required property {key!r}")

        for key, spec in (schema.get('properties', {}) if isinstance(schema, dict) else {}).items():
            if key in value: check(value[key], spec, key)
        return value

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any], *, timeout: int | None = None, images: list[dict[str, str]] | None = None) -> dict[str, Any]:
        import json, re
        if images and hasattr(self, 'generate_json_with_images'):
            return self.generate_json_with_images(system, prompt, schema, images=images, timeout=timeout)
        response = self.generate(system, prompt + "\nReturn ONLY valid JSON matching this schema:\n" + json.dumps(schema), timeout=timeout)
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                raise ValueError(f"Provider returned invalid structured output: {text[:500]}") from exc
            value = json.loads(match.group(0))
        return self.validate_structured(value, schema)
