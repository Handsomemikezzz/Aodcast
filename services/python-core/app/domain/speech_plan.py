from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.common import sha256_json, sha256_text, utc_now_iso


SPEECH_PLAN_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class TextSpan:
    start: int
    end: int

    def to_dict(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TextSpan":
        return cls(start=int(payload["start"]), end=int(payload["end"]))


@dataclass(frozen=True, slots=True)
class SpeechBreak:
    offset: int
    duration_ms: int

    def to_dict(self) -> dict[str, int]:
        return {"offset": self.offset, "duration_ms": self.duration_ms}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpeechBreak":
        return cls(offset=int(payload["offset"]), duration_ms=int(payload["duration_ms"]))


@dataclass(frozen=True, slots=True)
class EmphasisSpan:
    start: int
    end: int
    level: str

    def to_dict(self) -> dict[str, object]:
        return {"start": self.start, "end": self.end, "level": self.level}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EmphasisSpan":
        return cls(start=int(payload["start"]), end=int(payload["end"]), level=str(payload["level"]))


@dataclass(frozen=True, slots=True)
class PronunciationSpan:
    start: int
    end: int
    spoken_as: str

    def to_dict(self) -> dict[str, object]:
        return {"start": self.start, "end": self.end, "spoken_as": self.spoken_as}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PronunciationSpan":
        return cls(start=int(payload["start"]), end=int(payload["end"]), spoken_as=str(payload["spoken_as"]))


@dataclass(frozen=True, slots=True)
class SpeechDelivery:
    intent: str
    emotion: str
    energy: float
    pace: float

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "emotion": self.emotion,
            "energy": self.energy,
            "pace": self.pace,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpeechDelivery":
        return cls(
            intent=str(payload["intent"]),
            emotion=str(payload["emotion"]),
            energy=float(payload["energy"]),
            pace=float(payload["pace"]),
        )


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    segment_id: str
    position: int
    text: str
    source_span: TextSpan
    delivery: SpeechDelivery
    breaks: tuple[SpeechBreak, ...] = ()
    emphasis: tuple[EmphasisSpan, ...] = ()
    pronunciations: tuple[PronunciationSpan, ...] = ()
    pause_after_ms: int = 0

    @property
    def text_hash(self) -> str:
        return sha256_text(self.text)

    @property
    def segment_hash(self) -> str:
        return sha256_json(self._hash_payload())

    def _hash_payload(self) -> dict[str, object]:
        return {
            "text": self.text,
            "source_span": self.source_span.to_dict(),
            "delivery": self.delivery.to_dict(),
            "breaks": [item.to_dict() for item in self.breaks],
            "emphasis": [item.to_dict() for item in self.emphasis],
            "pronunciations": [item.to_dict() for item in self.pronunciations],
            "pause_after_ms": self.pause_after_ms,
        }

    def validate(self) -> None:
        if not self.segment_id.strip() or not self.text.strip():
            raise ValueError("Speech segments require a stable id and non-empty text.")
        if self.position < 0 or self.source_span.start < 0 or self.source_span.end <= self.source_span.start:
            raise ValueError("Speech segment positions and source spans must be ordered and non-negative.")
        if not 0.0 <= self.delivery.energy <= 1.0 or not 0.5 <= self.delivery.pace <= 2.0:
            raise ValueError("Speech delivery energy or pace is outside the supported range.")
        if not 0 <= self.pause_after_ms <= 10_000:
            raise ValueError("Speech segment pause_after_ms must be between 0 and 10000.")
        for item in self.breaks:
            if item.offset < 0 or item.offset > len(self.text) or not 1 <= item.duration_ms <= 10_000:
                raise ValueError("Speech break is outside the segment text or duration range.")
        for item in (*self.emphasis, *self.pronunciations):
            if item.start < 0 or item.end <= item.start or item.end > len(self.text):
                raise ValueError("Speech annotation span is outside the segment text.")
        ordered_pronunciations = sorted(self.pronunciations, key=lambda item: (item.start, item.end))
        if tuple(ordered_pronunciations) != self.pronunciations:
            raise ValueError("Pronunciation spans must be ordered by source position.")
        for previous, current in zip(ordered_pronunciations, ordered_pronunciations[1:]):
            if current.start < previous.end:
                raise ValueError("Pronunciation spans must not overlap.")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "segment_id": self.segment_id,
            "position": self.position,
            "text": self.text,
            "text_hash": self.text_hash,
            "source_span": self.source_span.to_dict(),
            "delivery": self.delivery.to_dict(),
            "breaks": [item.to_dict() for item in self.breaks],
            "emphasis": [item.to_dict() for item in self.emphasis],
            "pronunciations": [item.to_dict() for item in self.pronunciations],
            "pause_after_ms": self.pause_after_ms,
            "segment_hash": self.segment_hash,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpeechSegment":
        segment = cls(
            segment_id=str(payload["segment_id"]),
            position=int(payload["position"]),
            text=str(payload["text"]),
            source_span=TextSpan.from_dict(dict(payload["source_span"])),
            delivery=SpeechDelivery.from_dict(dict(payload["delivery"])),
            breaks=tuple(SpeechBreak.from_dict(item) for item in payload.get("breaks", []) if isinstance(item, dict)),
            emphasis=tuple(EmphasisSpan.from_dict(item) for item in payload.get("emphasis", []) if isinstance(item, dict)),
            pronunciations=tuple(PronunciationSpan.from_dict(item) for item in payload.get("pronunciations", []) if isinstance(item, dict)),
            pause_after_ms=int(payload.get("pause_after_ms", 0)),
        )
        segment.validate()
        if str(payload.get("text_hash") or segment.text_hash) != segment.text_hash:
            raise ValueError("Speech segment text hash does not match its text.")
        if str(payload.get("segment_hash") or segment.segment_hash) != segment.segment_hash:
            raise ValueError("Speech segment hash does not match its content.")
        return segment


@dataclass(frozen=True, slots=True)
class SpeechPlan:
    plan_id: str
    version: int
    session_id: str
    script_id: str
    script_hash: str
    language: str
    segments: tuple[SpeechSegment, ...]
    director_provider: str
    director_model: str
    prompt_version: str
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def plan_hash(self) -> str:
        return sha256_json(
            {
                "version": self.version,
                "session_id": self.session_id,
                "script_id": self.script_id,
                "script_hash": self.script_hash,
                "language": self.language,
                "segments": [segment.to_dict() for segment in self.segments],
                "director_metadata": self.director_metadata(),
            }
        )

    def director_metadata(self) -> dict[str, str]:
        return {
            "prompt_version": self.prompt_version,
            "provider": self.director_provider,
            "model": self.director_model,
        }

    def is_current_for(self, script_text: str) -> bool:
        return self.script_hash == sha256_text(script_text)

    def segment(self, segment_id: str) -> SpeechSegment:
        for item in self.segments:
            if item.segment_id == segment_id:
                return item
        raise ValueError(f"Unknown speech segment '{segment_id}'.")

    def context_window(self, segment_id: str, *, radius: int = 1) -> tuple[SpeechSegment, ...]:
        if radius < 0:
            raise ValueError("Speech context radius cannot be negative.")
        target = self.segment(segment_id)
        start = max(0, target.position - radius)
        end = min(len(self.segments), target.position + radius + 1)
        return self.segments[start:end]

    def validate(self) -> None:
        if self.version < 1 or not self.plan_id.strip() or not self.segments:
            raise ValueError("Speech plans require an id, positive version, and at least one segment.")
        positions = [segment.position for segment in self.segments]
        if positions != list(range(len(self.segments))):
            raise ValueError("Speech plan segment positions must be contiguous and zero-based.")
        ids = [segment.segment_id for segment in self.segments]
        if len(set(ids)) != len(ids):
            raise ValueError("Speech plan segment ids must be unique.")
        for segment in self.segments:
            segment.validate()

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": SPEECH_PLAN_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "version": self.version,
            "session_id": self.session_id,
            "script_id": self.script_id,
            "script_hash": self.script_hash,
            "plan_hash": self.plan_hash,
            "language": self.language,
            "segments": [segment.to_dict() for segment in self.segments],
            "director_metadata": self.director_metadata(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpeechPlan":
        if int(payload.get("schema_version", 0)) != SPEECH_PLAN_SCHEMA_VERSION:
            raise ValueError("Unsupported speech plan schema version.")
        director = dict(payload["director_metadata"])
        plan = cls(
            plan_id=str(payload["plan_id"]),
            version=int(payload["version"]),
            session_id=str(payload["session_id"]),
            script_id=str(payload["script_id"]),
            script_hash=str(payload["script_hash"]),
            language=str(payload["language"]),
            segments=tuple(SpeechSegment.from_dict(item) for item in payload["segments"] if isinstance(item, dict)),
            director_provider=str(director["provider"]),
            director_model=str(director["model"]),
            prompt_version=str(director["prompt_version"]),
            created_at=str(payload["created_at"]),
        )
        plan.validate()
        if str(payload.get("plan_hash") or plan.plan_hash) != plan.plan_hash:
            raise ValueError("Speech plan hash does not match its content.")
        return plan
