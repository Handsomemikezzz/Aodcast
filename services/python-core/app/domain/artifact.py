from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.common import utc_now_iso


@dataclass(slots=True)
class ArtifactRecord:
    session_id: str
    transcript_path: str = ""
    audio_path: str = ""
    provider: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "transcript_path": self.transcript_path,
            "audio_path": self.audio_path,
            "provider": self.provider,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactRecord":
        return cls(
            session_id=payload["session_id"],
            transcript_path=payload.get("transcript_path", ""),
            audio_path=payload.get("audio_path", ""),
            provider=payload.get("provider", ""),
            created_at=payload["created_at"],
        )
