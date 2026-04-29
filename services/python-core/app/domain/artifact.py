from __future__ import annotations

from copy import deepcopy
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
    voice_settings: dict[str, Any] = field(default_factory=dict)
    script_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_script_id: str = field(default="", repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        script_artifacts = deepcopy(self.script_artifacts)
        if self.active_script_id.strip():
            script_artifacts[self.active_script_id] = self._current_script_payload()
        return {
            "session_id": self.session_id,
            "transcript_path": self.transcript_path,
            "audio_path": self.audio_path,
            "provider": self.provider,
            "created_at": self.created_at,
            "takes": [take.to_dict() for take in self.takes],
            "final_take_id": self.final_take_id,
            "voice_settings": dict(self.voice_settings),
            "script_artifacts": script_artifacts,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactRecord":
        takes = _takes_from_payload(payload.get("takes", []))
        script_artifacts_payload = payload.get("script_artifacts", {})
        script_artifacts = (
            {
                str(script_id): _normalize_script_artifact_payload(item)
                for script_id, item in script_artifacts_payload.items()
                if isinstance(item, dict)
            }
            if isinstance(script_artifacts_payload, dict)
            else {}
        )
        return cls(
            session_id=payload["session_id"],
            transcript_path=payload.get("transcript_path", ""),
            audio_path=payload.get("audio_path", ""),
            provider=payload.get("provider", ""),
            created_at=payload["created_at"],
            takes=takes,
            final_take_id=str(payload.get("final_take_id", "")),
            voice_settings=dict(payload.get("voice_settings", {}) if isinstance(payload.get("voice_settings"), dict) else {}),
            script_artifacts=script_artifacts,
        )

    def for_script(self, script_id: str) -> "ArtifactRecord":
        clone = ArtifactRecord.from_dict(self.to_dict())
        cleaned = script_id.strip()
        clone.active_script_id = cleaned
        if not cleaned:
            return clone
        if cleaned in clone.script_artifacts:
            clone._apply_script_payload(clone.script_artifacts[cleaned])
        elif clone.script_artifacts:
            clone._apply_script_payload({})
        return clone

    def script_id_for_take(self, take_id: str) -> str:
        cleaned = take_id.strip()
        if not cleaned:
            return ""
        if any(take.take_id == cleaned for take in self.takes):
            return self.active_script_id
        for script_id, payload in self.script_artifacts.items():
            for take in _takes_from_payload(payload.get("takes", [])):
                if take.take_id == cleaned:
                    return script_id
        return ""

    def _current_script_payload(self) -> dict[str, Any]:
        return {
            "transcript_path": self.transcript_path,
            "audio_path": self.audio_path,
            "provider": self.provider,
            "takes": [take.to_dict() for take in self.takes],
            "final_take_id": self.final_take_id,
            "voice_settings": dict(self.voice_settings),
        }

    def _apply_script_payload(self, payload: dict[str, Any]) -> None:
        normalized = _normalize_script_artifact_payload(payload)
        self.transcript_path = str(normalized.get("transcript_path", ""))
        self.audio_path = str(normalized.get("audio_path", ""))
        self.provider = str(normalized.get("provider", ""))
        self.takes = _takes_from_payload(normalized.get("takes", []))
        self.final_take_id = str(normalized.get("final_take_id", ""))
        self.voice_settings = dict(
            normalized.get("voice_settings", {})
            if isinstance(normalized.get("voice_settings"), dict)
            else {}
        )


def _takes_from_payload(payload: Any) -> list[AudioTakeRecord]:
    return [
        AudioTakeRecord.from_dict(item)
        for item in payload
        if isinstance(item, dict)
    ] if isinstance(payload, list) else []


def _normalize_script_artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "transcript_path": str(payload.get("transcript_path", "")),
        "audio_path": str(payload.get("audio_path", "")),
        "provider": str(payload.get("provider", "")),
        "takes": [
            take.to_dict()
            for take in _takes_from_payload(payload.get("takes", []))
        ],
        "final_take_id": str(payload.get("final_take_id", "")),
        "voice_settings": dict(payload.get("voice_settings", {}) if isinstance(payload.get("voice_settings"), dict) else {}),
    }
