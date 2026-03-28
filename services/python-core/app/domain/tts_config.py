from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TTSProviderConfig:
    provider: str = "mock_remote"
    model: str = "mock-voice"
    base_url: str = ""
    api_key_env: str = ""
    voice: str = "alloy"
    audio_format: str = "wav"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "voice": self.voice,
            "audio_format": self.audio_format,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TTSProviderConfig":
        return cls(
            provider=str(payload.get("provider", "mock_remote")),
            model=str(payload.get("model", "mock-voice")),
            base_url=str(payload.get("base_url", "")),
            api_key_env=str(payload.get("api_key_env", "")),
            voice=str(payload.get("voice", "alloy")),
            audio_format=str(payload.get("audio_format", "wav")),
        )
