from __future__ import annotations

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_api.base import TTSProvider
from app.providers.tts_api.mock_remote import MockRemoteTTSProvider
from app.providers.tts_api.openai_compatible import OpenAICompatibleTTSProvider
from app.providers.tts_local_mlx.provider import LocalMLXTTSProvider

SUPPORTED_TTS_PROVIDERS = ("mock_remote", "openai_compatible", "local_mlx")


def validate_tts_provider(provider: str) -> None:
    if provider not in SUPPORTED_TTS_PROVIDERS:
        allowed = ", ".join(SUPPORTED_TTS_PROVIDERS)
        raise ValueError(f"Unsupported TTS provider '{provider}'. Allowed providers: {allowed}.")


def build_tts_provider(config: TTSProviderConfig) -> TTSProvider:
    validate_tts_provider(config.provider)
    if config.provider == "mock_remote":
        return MockRemoteTTSProvider()
    if config.provider == "openai_compatible":
        return OpenAICompatibleTTSProvider(config)
    if config.provider == "local_mlx":
        return LocalMLXTTSProvider(config)
    raise AssertionError("Validated provider should always match a supported TTS provider.")
