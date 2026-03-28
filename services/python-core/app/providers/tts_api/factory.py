from __future__ import annotations

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_api.base import TTSProvider
from app.providers.tts_api.mock_remote import MockRemoteTTSProvider
from app.providers.tts_api.openai_compatible import OpenAICompatibleTTSProvider


def build_tts_provider(config: TTSProviderConfig) -> TTSProvider:
    if config.provider == "mock_remote":
        return MockRemoteTTSProvider()
    if config.provider == "openai_compatible":
        return OpenAICompatibleTTSProvider(config)
    raise ValueError(f"Unsupported TTS provider '{config.provider}'.")
