from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.common import utc_now_iso


@dataclass(frozen=True, slots=True)
class VoiceProfileRecord:
    voice_profile_id: str
    name: str
    source: str
    audio_path: str
    preview_text: str
    provider: str
    model: str
    voice_id: str
    voice_name: str = ""
    style_id: str = "natural"
    style_name: str = ""
    speed: float = 1.0
    language: str = "zh"
    audio_format: str = "wav"
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    last_used_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at or utc_now_iso()
        updated_at = self.updated_at or created_at
        return {
            "voice_profile_id": self.voice_profile_id,
            "name": self.name,
            "source": self.source,
            "audio_path": self.audio_path,
            "preview_text": self.preview_text,
            "provider": self.provider,
            "model": self.model,
            "voice_id": self.voice_id,
            "voice_name": self.voice_name,
            "style_id": self.style_id,
            "style_name": self.style_name,
            "speed": self.speed,
            "language": self.language,
            "audio_format": self.audio_format,
            "description": self.description,
            "created_at": created_at,
            "updated_at": updated_at,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VoiceProfileRecord":
        return cls(
            voice_profile_id=str(payload["voice_profile_id"]),
            name=str(payload.get("name") or "Untitled voice"),
            source=str(payload.get("source") or "user_saved"),
            audio_path=str(payload.get("audio_path") or ""),
            preview_text=str(payload.get("preview_text") or ""),
            provider=str(payload.get("provider") or "local_mlx"),
            model=str(payload.get("model") or ""),
            voice_id=str(payload.get("voice_id") or "warm_narrator"),
            voice_name=str(payload.get("voice_name") or ""),
            style_id=str(payload.get("style_id") or "natural"),
            style_name=str(payload.get("style_name") or ""),
            speed=float(payload.get("speed") or 1.0),
            language=str(payload.get("language") or "zh"),
            audio_format=str(payload.get("audio_format") or "wav"),
            description=str(payload.get("description") or ""),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or utc_now_iso()),
            last_used_at=str(payload.get("last_used_at") or ""),
        )
