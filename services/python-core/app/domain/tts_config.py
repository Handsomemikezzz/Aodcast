from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TTSProviderConfig:
    provider: str = "mock_remote"
    model: str = "mock-voice"
    base_url: str = ""
    api_key: str = ""
    voice: str = "alloy"
    audio_format: str = "wav"
    local_runtime: str = "mlx"
    local_model_path: str = ""
    local_ref_audio_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "voice": self.voice,
            "audio_format": self.audio_format,
            "local_runtime": self.local_runtime,
            "local_model_path": self.local_model_path,
            "local_ref_audio_path": self.local_ref_audio_path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TTSProviderConfig":
        return cls(
            provider=str(payload.get("provider", "mock_remote")),
            model=str(payload.get("model", "mock-voice")),
            base_url=str(payload.get("base_url", "")),
            api_key=str(payload.get("api_key", "")),
            voice=str(payload.get("voice", "alloy")),
            audio_format=str(payload.get("audio_format", "wav")),
            local_runtime=str(payload.get("local_runtime", "mlx")),
            local_model_path=str(payload.get("local_model_path", "")),
            local_ref_audio_path=str(payload.get("local_ref_audio_path", "")),
        )
