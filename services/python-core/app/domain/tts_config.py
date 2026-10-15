from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields
from typing import Any

DEFAULT_LOCAL_TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
KOKORO_TTS_MODEL = "mlx-community/Kokoro-82M-bf16"
DEFAULT_SPEECH_URL = "http://127.0.0.1:8090/v1"


@dataclass(slots=True)
class TTSProviderConfig:
    provider: str = "local_http"
    model: str = DEFAULT_LOCAL_TTS_MODEL
    base_url: str = ""
    api_key: str = ""
    voice: str = "默认中文音色"
    audio_format: str = "wav"

    def __post_init__(self) -> None:
        if self.provider == "local_http" and not self.base_url.strip():
            self.base_url = os.getenv("AODCAST_SPEECH_URL", DEFAULT_SPEECH_URL)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TTSProviderConfig":
        return cls(
            **{f.name: str(payload[f.name]) for f in fields(cls) if f.name in payload}
        )
