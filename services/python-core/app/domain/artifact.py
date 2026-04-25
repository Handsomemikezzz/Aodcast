from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.common import utc_now_iso


@dataclass(slots=True)
class AudioTakeRecord:
    take_id: str
    session_id: str
    script_id: str = ""
    audio_path: str = ""
    transcript_path: str = ""
    provider: str = ""
    model: str = ""
    voice_id: str = ""
    voice_name: str = ""
    style_id: str = ""
    style_name: str = ""
    speed: float = 1.0
    language: str = "zh"
    audio_format: str = "wav"
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "take_id": self.take_id,
            "session_id": self.session_id,
            "script_id": self.script_id,
            "audio_path": self.audio_path,
            "transcript_path": self.transcript_path,
            "provider": self.provider,
            "model": self.model,
            "voice_id": self.voice_id,
            "voice_name": self.voice_name,
            "style_id": self.style_id,
            "style_name": self.style_name,
            "speed": self.speed,
            "language": self.language,
            "audio_format": self.audio_format,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AudioTakeRecord":
        return cls(
            take_id=str(payload["take_id"]),
            session_id=str(payload["session_id"]),
            script_id=str(payload.get("script_id", "")),
            audio_path=str(payload.get("audio_path", "")),
            transcript_path=str(payload.get("transcript_path", "")),
            provider=str(payload.get("provider", "")),
            model=str(payload.get("model", "")),
            voice_id=str(payload.get("voice_id", "")),
            voice_name=str(payload.get("voice_name", "")),
            style_id=str(payload.get("style_id", "")),
            style_name=str(payload.get("style_name", "")),
            speed=float(payload.get("speed", 1.0) or 1.0),
            language=str(payload.get("language", "zh")),
            audio_format=str(payload.get("audio_format", "wav")),
            created_at=str(payload["created_at"]),
        )


@dataclass(slots=True)
class ArtifactRecord:
    session_id: str
    transcript_path: str = ""
    audio_path: str = ""
    provider: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    takes: list[AudioTakeRecord] = field(default_factory=list)
    final_take_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "transcript_path": self.transcript_path,
            "audio_path": self.audio_path,
            "provider": self.provider,
            "created_at": self.created_at,
            "takes": [take.to_dict() for take in self.takes],
            "final_take_id": self.final_take_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactRecord":
        takes_payload = payload.get("takes", [])
        takes = [
            AudioTakeRecord.from_dict(item)
            for item in takes_payload
            if isinstance(item, dict)
        ] if isinstance(takes_payload, list) else []
        return cls(
            session_id=payload["session_id"],
            transcript_path=payload.get("transcript_path", ""),
            audio_path=payload.get("audio_path", ""),
            provider=payload.get("provider", ""),
            created_at=payload["created_at"],
            takes=takes,
            final_take_id=str(payload.get("final_take_id", "")),
        )
