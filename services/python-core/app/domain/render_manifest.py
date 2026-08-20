from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.common import sha256_json, utc_now_iso


RENDER_MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SpeechPlanReference:
    plan_id: str
    version: int
    plan_hash: str

    def to_dict(self) -> dict[str, object]:
        return {"plan_id": self.plan_id, "version": self.version, "plan_hash": self.plan_hash}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpeechPlanReference":
        return cls(plan_id=str(payload["plan_id"]), version=int(payload["version"]), plan_hash=str(payload["plan_hash"]))


@dataclass(frozen=True, slots=True)
class PipelineStage:
    stage: str
    provider: str
    model: str
    adapter_version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "provider": self.provider,
            "model": self.model,
            "adapter_version": self.adapter_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PipelineStage":
        return cls(
            stage=str(payload["stage"]),
            provider=str(payload["provider"]),
            model=str(payload["model"]),
            adapter_version=str(payload["adapter_version"]),
        )


@dataclass(frozen=True, slots=True)
class RegenerationWindow:
    target_segment_id: str
    window_segment_ids: tuple[str, ...]
    mode: str = "context_window"

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "target_segment_id": self.target_segment_id,
            "window_segment_ids": list(self.window_segment_ids),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RegenerationWindow":
        return cls(
            mode=str(payload["mode"]),
            target_segment_id=str(payload["target_segment_id"]),
            window_segment_ids=tuple(str(item) for item in payload["window_segment_ids"]),
        )


@dataclass(frozen=True, slots=True)
class RenderedSegment:
    segment_artifact_id: str
    segment_id: str
    position: int
    text_hash: str
    segment_hash: str
    audio_path: str
    audio_hash: str
    duration_ms: int
    generated_by_render_id: str
    seed: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_artifact_id": self.segment_artifact_id,
            "segment_id": self.segment_id,
            "position": self.position,
            "text_hash": self.text_hash,
            "segment_hash": self.segment_hash,
            "audio_path": self.audio_path,
            "audio_hash": self.audio_hash,
            "duration_ms": self.duration_ms,
            "generated_by_render_id": self.generated_by_render_id,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RenderedSegment":
        return cls(
            segment_artifact_id=str(payload["segment_artifact_id"]),
            segment_id=str(payload["segment_id"]),
            position=int(payload["position"]),
            text_hash=str(payload["text_hash"]),
            segment_hash=str(payload["segment_hash"]),
            audio_path=str(payload["audio_path"]),
            audio_hash=str(payload["audio_hash"]),
            duration_ms=int(payload["duration_ms"]),
            generated_by_render_id=str(payload["generated_by_render_id"]),
            seed=int(payload["seed"]) if payload.get("seed") is not None else None,
        )


@dataclass(frozen=True, slots=True)
class AssemblySpec:
    sample_rate_hz: int = 48_000
    channels: int = 1
    sample_width_bits: int = 16
    target_rms_dbfs: float = -16.0
    peak_ceiling_dbfs: float = -1.0
    edge_fade_ms: int = 12
    audio_format: str = "wav"

    def to_dict(self) -> dict[str, object]:
        return {
            "audio_format": self.audio_format,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "sample_width_bits": self.sample_width_bits,
            "target_rms_dbfs": self.target_rms_dbfs,
            "peak_ceiling_dbfs": self.peak_ceiling_dbfs,
            "edge_fade_ms": self.edge_fade_ms,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AssemblySpec":
        return cls(
            audio_format=str(payload["audio_format"]),
            sample_rate_hz=int(payload["sample_rate_hz"]),
            channels=int(payload["channels"]),
            sample_width_bits=int(payload["sample_width_bits"]),
            target_rms_dbfs=float(payload["target_rms_dbfs"]),
            peak_ceiling_dbfs=float(payload["peak_ceiling_dbfs"]),
            edge_fade_ms=int(payload["edge_fade_ms"]),
        )


@dataclass(frozen=True, slots=True)
class RenderOutput:
    audio_path: str
    audio_hash: str
    transcript_path: str
    duration_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "audio_path": self.audio_path,
            "audio_hash": self.audio_hash,
            "transcript_path": self.transcript_path,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RenderOutput":
        return cls(
            audio_path=str(payload["audio_path"]),
            audio_hash=str(payload["audio_hash"]),
            transcript_path=str(payload["transcript_path"]),
            duration_ms=int(payload["duration_ms"]),
        )


@dataclass(frozen=True, slots=True)
class RenderManifest:
    render_id: str
    session_id: str
    script_id: str
    script_hash: str
    speech_plan: SpeechPlanReference
    speaker_reference: dict[str, str] | None
    pipeline: tuple[PipelineStage, ...]
    segments: tuple[RenderedSegment, ...]
    assembly: AssemblySpec
    output: RenderOutput
    parent_render_id: str | None = None
    regeneration: RegenerationWindow | None = None
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def pipeline_hash(self) -> str:
        return sha256_json([stage.to_dict() for stage in self.pipeline])

    def validate(self) -> None:
        if not self.render_id.strip() or not self.pipeline or not self.segments:
            raise ValueError("Render manifests require an id, pipeline, and rendered segments.")
        positions = [segment.position for segment in self.segments]
        if positions != list(range(len(self.segments))):
            raise ValueError("Rendered segment positions must be contiguous and zero-based.")
        if self.regeneration is not None:
            known_ids = {segment.segment_id for segment in self.segments}
            if not self.regeneration.window_segment_ids or not set(self.regeneration.window_segment_ids) <= known_ids:
                raise ValueError("Regeneration window must reference rendered segments.")

    def is_current_for(self, *, script_hash: str, speech_plan_id: str, plan_hash: str) -> bool:
        return (
            self.script_hash == script_hash
            and self.speech_plan.plan_id == speech_plan_id
            and self.speech_plan.plan_hash == plan_hash
        )

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": RENDER_MANIFEST_SCHEMA_VERSION,
            "render_id": self.render_id,
            "session_id": self.session_id,
            "script_id": self.script_id,
            "script_hash": self.script_hash,
            "speech_plan": self.speech_plan.to_dict(),
            "speaker_reference": dict(self.speaker_reference) if self.speaker_reference else None,
            "pipeline": [stage.to_dict() for stage in self.pipeline],
            "pipeline_hash": self.pipeline_hash,
            "parent_render_id": self.parent_render_id,
            "regeneration": self.regeneration.to_dict() if self.regeneration else None,
            "segments": [segment.to_dict() for segment in self.segments],
            "assembly": self.assembly.to_dict(),
            "output": self.output.to_dict(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RenderManifest":
        if int(payload.get("schema_version", 0)) != RENDER_MANIFEST_SCHEMA_VERSION:
            raise ValueError("Unsupported render manifest schema version.")
        manifest = cls(
            render_id=str(payload["render_id"]),
            session_id=str(payload["session_id"]),
            script_id=str(payload["script_id"]),
            script_hash=str(payload["script_hash"]),
            speech_plan=SpeechPlanReference.from_dict(dict(payload["speech_plan"])),
            speaker_reference=(
                {str(k): str(v) for k, v in dict(payload["speaker_reference"]).items()}
                if isinstance(payload.get("speaker_reference"), dict)
                else None
            ),
            pipeline=tuple(PipelineStage.from_dict(item) for item in payload["pipeline"] if isinstance(item, dict)),
            parent_render_id=str(payload["parent_render_id"]) if payload.get("parent_render_id") else None,
            regeneration=RegenerationWindow.from_dict(dict(payload["regeneration"])) if isinstance(payload.get("regeneration"), dict) else None,
            segments=tuple(RenderedSegment.from_dict(item) for item in payload["segments"] if isinstance(item, dict)),
            assembly=AssemblySpec.from_dict(dict(payload["assembly"])),
            output=RenderOutput.from_dict(dict(payload["output"])),
            created_at=str(payload["created_at"]),
        )
        manifest.validate()
        if str(payload.get("pipeline_hash") or manifest.pipeline_hash) != manifest.pipeline_hash:
            raise ValueError("Render pipeline hash does not match its stages.")
        return manifest
