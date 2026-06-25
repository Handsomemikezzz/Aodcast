from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.domain.common import utc_now_iso


class Speaker(StrEnum):
    AGENT = "agent"
    USER = "user"


def new_turn_id() -> str:
    return f"turn_{uuid4().hex}"


def derive_turn_id(session_id: str, created_at: str, speaker: str, content: str) -> str:
    """Deterministic id for legacy turns that predate turn_id.

    Stable across reads so memory evidence, cursors, and forget fingerprints
    can reference old turns without rewriting history first.
    """
    digest = hashlib.sha1(
        " ".join([session_id, created_at, speaker, content]).encode("utf-8")
    ).hexdigest()
    return f"turn_{digest[:24]}"


@dataclass(slots=True)
class TranscriptTurn:
    speaker: Speaker
    content: str
    created_at: str = field(default_factory=utc_now_iso)
    turn_id: str = field(default_factory=new_turn_id)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["speaker"] = self.speaker.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, session_id: str = "") -> "TranscriptTurn":
        speaker = payload["speaker"]
        content = payload["content"]
        created_at = payload["created_at"]
        turn_id = payload.get("turn_id") or derive_turn_id(
            session_id, created_at, str(speaker), content
        )
        return cls(
            speaker=Speaker(speaker),
            content=content,
            created_at=created_at,
            turn_id=turn_id,
        )


@dataclass(slots=True)
class TranscriptRecord:
    session_id: str
    turns: list[TranscriptTurn] = field(default_factory=list)

    def append(self, speaker: Speaker, content: str) -> TranscriptTurn:
        turn = TranscriptTurn(speaker=speaker, content=content)
        self.turns.append(turn)
        return turn

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turns": [turn.to_dict() for turn in self.turns],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TranscriptRecord":
        session_id = payload["session_id"]
        return cls(
            session_id=session_id,
            turns=[
                TranscriptTurn.from_dict(turn, session_id=session_id)
                for turn in payload.get("turns", [])
            ],
        )
