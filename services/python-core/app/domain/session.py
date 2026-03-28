from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.domain.common import utc_now_iso


class SessionState(StrEnum):
    TOPIC_DEFINED = "topic_defined"
    INTERVIEW_IN_PROGRESS = "interview_in_progress"
    READINESS_EVALUATION = "readiness_evaluation"
    READY_TO_GENERATE = "ready_to_generate"
    SCRIPT_GENERATED = "script_generated"
    SCRIPT_EDITED = "script_edited"
    AUDIO_RENDERING = "audio_rendering"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class SessionRecord:
    topic: str
    creation_intent: str
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.TOPIC_DEFINED
    llm_provider: str = ""
    tts_provider: str = ""
    last_error: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def transition(self, new_state: SessionState) -> None:
        self.state = new_state
        if new_state != SessionState.FAILED:
            self.last_error = ""
        self.updated_at = utc_now_iso()

    def set_error(self, message: str) -> None:
        self.state = SessionState.FAILED
        self.last_error = message
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionRecord":
        return cls(
            session_id=payload["session_id"],
            topic=payload["topic"],
            creation_intent=payload["creation_intent"],
            state=SessionState(payload["state"]),
            llm_provider=payload.get("llm_provider", ""),
            tts_provider=payload.get("tts_provider", ""),
            last_error=payload.get("last_error", ""),
            created_at=payload.get("created_at", utc_now_iso()),
            updated_at=payload.get("updated_at", utc_now_iso()),
        )
