from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TTSGenerationRequest:
    session_id: str
    script_text: str
    voice: str
    audio_format: str


@dataclass(frozen=True, slots=True)
class TTSGenerationResponse:
    audio_bytes: bytes
    file_extension: str
    provider_name: str
    model_name: str


class TTSProvider(Protocol):
    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        """Render audio bytes for the supplied script."""
