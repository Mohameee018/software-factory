from factory.providers.base import AIProvider
from factory.providers.mock import MockProvider
from factory.providers.http import OpenAICompatibleProvider, AnthropicProvider
import os

def build_provider(settings) -> AIProvider:
    return build_provider_for_spec(settings, settings.provider, settings.model)

def build_provider_for_spec(settings, provider_name, model) -> AIProvider:
    provider=(provider_name or '').strip().lower()
    if model.strip().lower() == 'gemini-2.5-flash': model='gemini-3.8-flash'
    key_map={'openai':'OPENAI_API_KEY','openai-compatible':'OPENAI_API_KEY','gemini':'GEMINI_API_KEY','google':'GEMINI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}
    key=os.getenv(key_map.get(provider,'')) if provider in key_map else None
    if not key and provider == str(settings.provider).lower(): key=settings.api_key
    if not key and provider in ('gemini','google') and 'generativelanguage.googleapis.com' in str(settings.api_base_url): key=settings.api_key
    if settings.mode in ('mock','dry-run') or provider == 'mock': return MockProvider(model)
    if not key: raise RuntimeError(f'API key required for model {provider}:{model}. Set {key_map.get(provider, "provider-specific API key")}.')
    if provider in ('openai','openai-compatible'):
        base=os.getenv('OPENAI_BASE_URL') or ('https://api.openai.com/v1' if provider=='openai' else settings.api_base_url)
        return OpenAICompatibleProvider(key,model,base,timeout=settings.ai_timeout,max_retries=0)
    if provider in ('gemini','google'):
        base=os.getenv('GEMINI_BASE_URL') or 'https://generativelanguage.googleapis.com/v1beta/openai/'
        return OpenAICompatibleProvider(key,model,base,timeout=settings.ai_timeout,max_retries=0)
    if provider=='anthropic':
        base=os.getenv('ANTHROPIC_BASE_URL') or 'https://api.anthropic.com/v1'
        return AnthropicProvider(key,model,base,timeout=settings.ai_timeout,max_retries=0)
    raise RuntimeError(f'Unsupported AI provider {provider!r}')
