from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.domain.common import is_within_days_since, utc_now_iso


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
    deleted_at: str | None = None
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

    def rename_topic(self, topic: str) -> None:
        cleaned = topic.strip()
        if not cleaned:
            raise ValueError("Session topic cannot be empty.")
        self.topic = cleaned

    def soft_delete(self) -> None:
        now = utc_now_iso()
        self.deleted_at = now
        self.updated_at = now

    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def can_restore(self, *, within_days: int = 30) -> bool:
        if self.deleted_at is None:
            return True
        return is_within_days_since(self.deleted_at, days=within_days)

    def restore(self, *, within_days: int = 30) -> None:
        if self.deleted_at is None:
            return
        if not self.can_restore(within_days=within_days):
            raise ValueError(f"Session restore window exceeded ({within_days} days).")
        self.deleted_at = None
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
            deleted_at=payload.get("deleted_at") or None,
            created_at=payload.get("created_at", utc_now_iso()),
            updated_at=payload.get("updated_at", utc_now_iso()),
        )
