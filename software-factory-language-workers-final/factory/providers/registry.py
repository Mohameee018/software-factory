from factory.providers.base import AIProvider
from factory.providers.mock import MockProvider
from factory.providers.http import OpenAICompatibleProvider, AnthropicProvider

def build_provider(settings) -> AIProvider:
    if settings.mode in ('mock','dry-run') or settings.provider == 'mock': return MockProvider(settings.model)
    if not settings.api_key: raise RuntimeError(f'API key required for real provider {settings.provider!r}')
    kwargs = dict(timeout=settings.ai_timeout, max_retries=settings.max_retries)
    if settings.provider in ('openai','openai-compatible'):
        return OpenAICompatibleProvider(settings.api_key, settings.model, settings.api_base_url, **kwargs)
    if settings.provider == 'anthropic':
        return AnthropicProvider(settings.api_key, settings.model, settings.api_base_url or 'https://api.anthropic.com/v1', **kwargs)
    raise RuntimeError(f'Unsupported AI provider: {settings.provider}')
