import os

from factory.providers.router import ModelRouter


def test_cross_provider_failover_adds_credentialed_backup(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.delenv("AI_MODELS", raising=False)
    monkeypatch.delenv("AI_MODELS_DEVELOPER", raising=False)

    class Settings:
        provider = "openai-compatible"
        model = "gemini-3.8-flash"
        api_base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    router = ModelRouter(Settings())
    specs = router.specs_for("developer")
    labels = [item["label"] for item in specs]

    assert any(label.startswith("openai-compatible:") for label in labels)
    assert "groq:openai/gpt-oss-20b" in labels


def test_explicit_ai_models_remain_authoritative(monkeypatch):
    monkeypatch.setenv("AI_MODELS", "groq:openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    class Settings:
        provider = "openai-compatible"
        model = "gemini-3.8-flash"
        api_base_url = "https://example.invalid/v1"

    router = ModelRouter(Settings())
    specs = router.specs_for("developer")

    assert [item["label"] for item in specs] == ["openai-compatible:gemini-3.8-flash", "groq:openai/gpt-oss-20b"]



def test_role_specific_model_pool_does_not_break_cross_provider_failover(monkeypatch):
    monkeypatch.setenv("AI_MODELS_DEVELOPER", "openai-compatible:gemini-3.8-flash")
    monkeypatch.delenv("AI_MODELS", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    class Settings:
        provider = "openai-compatible"
        model = "gemini-3.8-flash"
        api_base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    router = ModelRouter(Settings())
    labels = [item["label"] for item in router.specs_for("developer")]
    assert labels[0] == "openai-compatible:gemini-3.8-flash"
    assert "groq:openai/gpt-oss-20b" in labels
