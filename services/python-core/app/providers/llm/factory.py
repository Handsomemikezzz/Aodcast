from __future__ import annotations

from app.domain.provider_config import LLMProviderConfig
from app.providers.llm.base import LLMProvider
from app.providers.llm.mock_provider import MockLLMProvider


def build_llm_provider(config: LLMProviderConfig) -> LLMProvider:
    if config.provider == "mock":
        return MockLLMProvider()
    if config.provider == "openai_compatible":
        from app.providers.llm.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(config)
    raise ValueError(f"Unsupported LLM provider '{config.provider}'.")
