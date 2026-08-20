from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from app.providers.tts_api.base import SpeechBreak
from app.providers.tts_local_mlx.capabilities import (
    CloneMode,
    ModelCapabilities,
    capabilities_for_model,
    validate_request_capabilities,
)
from app.providers.tts_local_mlx.chunker import ScriptChunk
from app.providers.tts_local_mlx.model_spec import ModelSpec


@dataclass(frozen=True, slots=True)
class AdapterRequest:
    voice: str = ""
    speed: float = 1.0
    style_prompt: str = ""
    language: str = "zh"
    reference_audio_path: str = ""
    reference_text: str = ""
    clone_mode: str = CloneMode.AUTO

    def to_payload(self) -> dict[str, object]:
        return {
            "voice": self.voice,
            "speed": self.speed,
            "style_prompt": self.style_prompt,
            "language": self.language,
            "reference_audio_path": self.reference_audio_path,
            "reference_text": self.reference_text,
            "clone_mode": self.clone_mode,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> AdapterRequest:
        return cls(
            voice=str(payload.get("voice") or ""),
            speed=float(payload.get("speed") or 1.0),
            style_prompt=str(payload.get("style_prompt") or ""),
            language=str(payload.get("language") or "zh"),
            reference_audio_path=str(payload.get("reference_audio_path") or ""),
            reference_text=str(payload.get("reference_text") or ""),
            clone_mode=str(payload.get("clone_mode") or CloneMode.AUTO),
        )


@dataclass(frozen=True, slots=True)
class PreparedSegment:
    text: str
    pause_after_ms: int = 0

    def to_payload(self) -> dict[str, object]:
        return {"text": self.text, "pause_after_ms": self.pause_after_ms}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PreparedSegment:
        return cls(
            text=str(payload.get("text") or ""),
            pause_after_ms=max(0, int(payload.get("pause_after_ms") or 0)),
        )


@dataclass(frozen=True, slots=True)
class PreparedSynthesis:
    segments: tuple[PreparedSegment, ...]
    leading_silence_ms: int = 0


Chunker = Callable[[str], list[ScriptChunk]]


class MLXTTSAdapter:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    @property
    def capabilities(self) -> ModelCapabilities:
        return capabilities_for_model(self.spec)

    def validate_request(
        self,
        request: AdapterRequest,
        breaks: tuple[SpeechBreak, ...],
    ) -> CloneMode:
        return validate_request_capabilities(
            self.spec,
            voice=request.voice,
            speed=request.speed,
            style_prompt=request.style_prompt,
            reference_audio_path=request.reference_audio_path,
            reference_text=request.reference_text,
            breaks=breaks,
            clone_mode=request.clone_mode,
        )

    def prepare_synthesis(
        self,
        text: str,
        breaks: Iterable[SpeechBreak],
        chunker: Chunker,
    ) -> PreparedSynthesis:
        normalized_breaks = normalize_breaks(text, breaks)
        return prepare_pcm_pause_synthesis(text, normalized_breaks, chunker)

    def generation_kwargs(
        self,
        text: str,
        request: AdapterRequest,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate(
        self,
        model: Any,
        text: str,
        request: AdapterRequest,
    ) -> Any:
        return model.generate(**self.generation_kwargs(text, request))


def normalize_breaks(
    text: str,
    breaks: Iterable[SpeechBreak],
) -> tuple[SpeechBreak, ...]:
    by_offset: dict[int, int] = {}
    for item in breaks:
        if not isinstance(item, SpeechBreak):
            if isinstance(item, Mapping):
                item = SpeechBreak(
                    offset=int(item.get("offset") or 0),
                    duration_ms=int(item.get("duration_ms") or 0),
                )
            elif hasattr(item, "offset") and hasattr(item, "duration_ms"):
                item = SpeechBreak(
                    offset=int(getattr(item, "offset")),
                    duration_ms=int(getattr(item, "duration_ms")),
                )
            else:
                raise ValueError("breaks must contain SpeechBreak values.")
        if item.offset < 0 or item.offset > len(text):
            raise ValueError(
                f"Speech break offset {item.offset} is outside text length {len(text)}."
            )
        if not 1 <= item.duration_ms <= 10_000:
            raise ValueError(
                "Speech break duration_ms must be between 1 and 10000."
            )
        by_offset[item.offset] = by_offset.get(item.offset, 0) + item.duration_ms
    return tuple(
        SpeechBreak(offset=offset, duration_ms=duration_ms)
        for offset, duration_ms in sorted(by_offset.items())
    )


def prepare_pcm_pause_synthesis(
    text: str,
    breaks: tuple[SpeechBreak, ...],
    chunker: Chunker,
) -> PreparedSynthesis:
    if not breaks:
        return PreparedSynthesis(
            segments=tuple(PreparedSegment(chunk.text) for chunk in chunker(text))
        )

    cursor = 0
    leading_silence_ms = 0
    segments: list[PreparedSegment] = []
    for item in breaks:
        part = text[cursor : item.offset]
        segments.extend(PreparedSegment(chunk.text) for chunk in chunker(part))
        if segments:
            segments[-1] = replace(
                segments[-1],
                pause_after_ms=segments[-1].pause_after_ms + item.duration_ms,
            )
        else:
            leading_silence_ms += item.duration_ms
        cursor = item.offset
    segments.extend(PreparedSegment(chunk.text) for chunk in chunker(text[cursor:]))
    return PreparedSynthesis(
        segments=tuple(segments),
        leading_silence_ms=leading_silence_ms,
    )


def canonical_language(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if normalized in {"zh", "zh-cn", "zh-hans", "cn", "chinese"}:
        return "chinese"
    if normalized in {"en", "en-us", "en-gb", "english"}:
        return "english"
    return normalized or "auto"


def moss_language(value: str) -> str:
    normalized = canonical_language(value)
    if normalized == "auto":
        return ""
    return normalized.title()
