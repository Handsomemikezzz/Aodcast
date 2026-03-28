from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ScriptGenerationRequest:
    session_id: str
    topic: str
    creation_intent: str
    transcript_text: str


@dataclass(frozen=True, slots=True)
class ScriptGenerationResponse:
    draft: str
    provider_name: str
    model_name: str


class LLMProvider(Protocol):
    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        """Generate a script draft from interview transcript text."""
