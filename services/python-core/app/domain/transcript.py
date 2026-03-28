from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.common import utc_now_iso


class Speaker(StrEnum):
    AGENT = "agent"
    USER = "user"


@dataclass(slots=True)
class TranscriptTurn:
    speaker: Speaker
    content: str
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["speaker"] = self.speaker.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TranscriptTurn":
        return cls(
            speaker=Speaker(payload["speaker"]),
            content=payload["content"],
            created_at=payload["created_at"],
        )


@dataclass(slots=True)
class TranscriptRecord:
    session_id: str
    turns: list[TranscriptTurn] = field(default_factory=list)

    def append(self, speaker: Speaker, content: str) -> None:
        self.turns.append(TranscriptTurn(speaker=speaker, content=content))

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
