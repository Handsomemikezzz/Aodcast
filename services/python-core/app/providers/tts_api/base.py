from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class TTSGenerationRequest:
    session_id: str
    script_text: str
    voice: str
    audio_format: str
    speed: float = 1.0
    style_id: str = ""
    style_prompt: str = ""
    language: str = "zh"
    should_cancel: Callable[[], bool] | None = None
    # Optional callback that providers may invoke whenever they have new
    # chunk-level progress information. The ``event`` payload is provider
    # defined; callers should treat unknown fields as informational only.
    on_progress: Callable[[Any], None] | None = None


@dataclass(frozen=True, slots=True)
class TTSGenerationResponse:
    audio_bytes: bytes
    file_extension: str
    provider_name: str
    model_name: str


class TTSProvider(Protocol):
    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        """Render audio bytes for the supplied script."""
