from __future__ import annotations

from app.domain.provider_config import LLMProviderConfig
from app.providers.llm.base import LLMProvider
from app.providers.llm.mock_provider import MockLLMProvider

SUPPORTED_LLM_PROVIDERS = ("mock", "openai_compatible", "codex_subscription")


def validate_llm_provider(provider: str) -> None:
    if provider not in SUPPORTED_LLM_PROVIDERS:
        allowed = ", ".join(SUPPORTED_LLM_PROVIDERS)
        raise ValueError(f"Unsupported LLM provider '{provider}'. Allowed providers: {allowed}.")


def build_llm_provider(config: LLMProviderConfig) -> LLMProvider:
    validate_llm_provider(config.provider)
    if config.provider == "mock":
        return MockLLMProvider()
    if config.provider == "openai_compatible":
        from app.providers.llm.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(config)
    if config.provider == "codex_subscription":
        from app.providers.llm.codex_app_server import CodexSubscriptionProvider

        return CodexSubscriptionProvider(config)
    raise AssertionError("Validated provider should always match a supported LLM provider.")
