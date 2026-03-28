from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


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


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class SessionRecord:
    topic: str
    creation_intent: str
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.TOPIC_DEFINED
    llm_provider: str = ""
    tts_provider: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def transition(self, new_state: SessionState) -> None:
        self.state = new_state
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
            created_at=payload.get("created_at", utc_now_iso()),
            updated_at=payload.get("updated_at", utc_now_iso()),
        )
