from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.domain.attachment import Attachment
from app.domain.common import utc_now_iso


class Speaker(StrEnum):
    AGENT = "agent"
    USER = "user"


def new_turn_id() -> str:
    return f"turn_{uuid4().hex}"


@dataclass(slots=True)
class TranscriptTurn:
    speaker: Speaker
    content: str
    created_at: str = field(default_factory=utc_now_iso)
    turn_id: str = field(default_factory=new_turn_id)
    # Lightweight routing metadata added during the interview.
    # Keys: interview_focus, turn_role, prompt_version, prompt_section_ids.
    metadata: dict[str, Any] = field(default_factory=dict)
    # User turns only; attachment text never feeds long-term memory.
    attachments: list[Attachment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "speaker": self.speaker.value,
            "content": self.content,
            "created_at": self.created_at,
            "turn_id": self.turn_id,
        }
        # Omit empty metadata to keep JSON compact.
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        if self.attachments:
            payload["attachments"] = [attachment.to_dict() for attachment in self.attachments]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TranscriptTurn":
        return cls(
            speaker=Speaker(payload["speaker"]),
            content=payload["content"],
            created_at=payload["created_at"],
            turn_id=payload["turn_id"],
            metadata=dict(payload.get("metadata") or {}),
            attachments=[Attachment.from_dict(item) for item in payload.get("attachments") or []],
        )


@dataclass(slots=True)
class TranscriptRecord:
    session_id: str
    turns: list[TranscriptTurn] = field(default_factory=list)

    def append(
        self,
        speaker: Speaker,
        content: str,
        metadata: dict[str, Any] | None = None,
        attachments: list[Attachment] | None = None,
    ) -> TranscriptTurn:
        if attachments and speaker != Speaker.USER:
            raise ValueError("Only user turns may carry attachments.")
        turn = TranscriptTurn(
            speaker=speaker,
            content=content,
            metadata=dict(metadata) if metadata else {},
            attachments=list(attachments or []),
        )
        self.turns.append(turn)
        return turn

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turns": [turn.to_dict() for turn in self.turns],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TranscriptRecord":
        return cls(
            session_id=payload["session_id"],
            turns=[TranscriptTurn.from_dict(turn) for turn in payload.get("turns", [])],
        )
