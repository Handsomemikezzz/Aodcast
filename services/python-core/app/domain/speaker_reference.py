from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.common import sha256_json, utc_now_iso


SPEAKER_REFERENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SpeakerReference:
    speaker_reference_id: str
    name: str
    source: str
    audio_path: str
    audio_hash: str
    audio_format: str
    duration_ms: int
    reference_text: str
    language: str = "zh"
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    last_used_at: str | None = None

    @property
    def reference_hash(self) -> str:
        return sha256_json(
            {
                "audio_hash": self.audio_hash,
                "reference_text": self.reference_text,
                "language": self.language,
            }
        )

    def validate(self) -> None:
        if not self.speaker_reference_id.strip() or not self.name.strip():
            raise ValueError("Speaker references require an id and name.")
        if self.source not in {"built_in", "user_saved"}:
            raise ValueError("Speaker reference source must be built_in or user_saved.")
        if not self.audio_path.strip() or len(self.audio_hash) != 64 or self.duration_ms <= 0:
            raise ValueError("Speaker references require valid audio metadata.")
        if not self.reference_text.strip() or not self.language.strip():
            raise ValueError("Speaker references require reference text and language.")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        created_at = self.created_at or utc_now_iso()
        updated_at = self.updated_at or created_at
        return {
            "schema_version": SPEAKER_REFERENCE_SCHEMA_VERSION,
            "speaker_reference_id": self.speaker_reference_id,
            "name": self.name,
            "source": self.source,
            "audio_path": self.audio_path,
            "audio_hash": self.audio_hash,
            "audio_format": self.audio_format,
            "duration_ms": self.duration_ms,
            "reference_text": self.reference_text,
            "language": self.language,
            "reference_hash": self.reference_hash,
            "description": self.description,
            "created_at": created_at,
            "updated_at": updated_at,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpeakerReference":
        if int(payload.get("schema_version", 0)) != SPEAKER_REFERENCE_SCHEMA_VERSION:
            raise ValueError("Unsupported speaker reference schema version.")
        reference = cls(
            speaker_reference_id=str(payload["speaker_reference_id"]),
            name=str(payload["name"]),
            source=str(payload["source"]),
            audio_path=str(payload["audio_path"]),
            audio_hash=str(payload["audio_hash"]),
            audio_format=str(payload["audio_format"]),
            duration_ms=int(payload["duration_ms"]),
            reference_text=str(payload["reference_text"]),
            language=str(payload["language"]),
            description=str(payload.get("description") or ""),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            last_used_at=str(payload["last_used_at"]) if payload.get("last_used_at") else None,
        )
        reference.validate()
        if str(payload.get("reference_hash") or reference.reference_hash) != reference.reference_hash:
            raise ValueError("Speaker reference hash does not match its content.")
        return reference

    def snapshot(self) -> dict[str, str]:
        self.validate()
        return {
            "speaker_reference_id": self.speaker_reference_id,
            "reference_hash": self.reference_hash,
            "audio_path": self.audio_path,
            "audio_hash": self.audio_hash,
            "reference_text": self.reference_text,
            "language": self.language,
        }
