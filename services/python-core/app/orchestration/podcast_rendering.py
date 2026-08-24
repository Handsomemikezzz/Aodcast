from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.domain.artifact import ArtifactRecord, AudioTakeRecord
from app.domain.common import sha256_bytes, sha256_json, sha256_text
from app.domain.project import SessionProject
from app.domain.render_manifest import (
    AssemblySpec,
    PipelineStage,
    RegenerationWindow,
    RenderManifest,
    RenderOutput,
    RenderedSegment,
    SpeechPlanReference,
)
from app.domain.speech_plan import SpeechBreak as PlannedBreak, SpeechPlan, SpeechSegment
from app.domain.voice_studio import resolve_style_preset
from app.orchestration.audio_assembly import PodcastAudioAssembler
from app.orchestration.speech_director import SpeechDirectorService
from app.providers.tts_api.base import SpeechBreak, TTSGenerationRequest, TTSGenerationResponse
from app.providers.tts_api.factory import build_tts_provider
from app.providers.tts_local_mlx.capabilities import SupportLevel, capabilities_for_model
from app.providers.tts_local_mlx.model_spec import resolve_model_spec
from app.runtime.task_cancellation import TaskCancellationRequested
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore


@dataclass(frozen=True, slots=True)
class PodcastRenderSettings:
    voice_id: str
    provider_voice: str
    voice_name: str
    style_id: str
    style_name: str
    style_prompt: str
    language: str = "zh"


@dataclass(frozen=True, slots=True)
class PodcastRenderProgress:
    percent: float
    message: str
    segment_index: int = 0
    segments_total: int = 0


@dataclass(frozen=True, slots=True)
class PodcastRenderResult:
    project: SessionProject
    provider: str
    model: str
    audio_path: str
    transcript_path: str
    affected_segment_ids: tuple[str, ...]


class PodcastRenderingPipeline:
    def __init__(
        self,
        config_store: ConfigStore,
        artifact_store: ArtifactStore,
    ) -> None:
        self.config_store = config_store
        self.artifact_store = artifact_store
        self.speech_director = SpeechDirectorService(config_store)

    def render_full(
        self,
        project: SessionProject,
        *,
        settings: PodcastRenderSettings,
        override_provider: str = "",
        override_model: str = "",
        require_speaker_reference: bool = False,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[PodcastRenderProgress], None] | None = None,
    ) -> PodcastRenderResult:
        script_text = self._script_text(project)
        self._raise_if_cancelled(should_cancel)
        self._notify(on_progress, 5.0, "Directing pauses, emphasis, and delivery...")
        plan = self.speech_director.create_plan(project)
        project.speech_plan = plan
        return self._render(
            project,
            plan=plan,
            settings=settings,
            override_provider=override_provider,
            override_model=override_model,
            require_speaker_reference=require_speaker_reference,
            target_segment_id=None,
            script_text=script_text,
            should_cancel=should_cancel,
            on_progress=on_progress,
        )

    def regenerate_window(
        self,
        project: SessionProject,
        *,
        target_segment_id: str,
        expected_plan_id: str,
        expected_render_id: str,
        settings: PodcastRenderSettings,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[PodcastRenderProgress], None] | None = None,
    ) -> PodcastRenderResult:
        script_text = self._script_text(project)
        plan = project.speech_plan
        parent = project.render_manifest
        if plan is None or parent is None:
            raise ValueError("Generate the full podcast before regenerating a segment.")
        if plan.plan_id != expected_plan_id or parent.render_id != expected_render_id:
            raise ValueError("Speech plan or render manifest is stale. Refresh the script and try again.")
        if not plan.is_current_for(script_text) or not parent.is_current_for(
            script_hash=sha256_text(script_text),
            speech_plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
        ):
            raise ValueError("The script changed after this audio was rendered. Generate the full podcast again.")
        current_reference = self._speaker_reference_snapshot(
            project.artifact.speaker_reference if project.artifact else {}
        )
        if current_reference != parent.speaker_reference:
            raise ValueError("The selected speaker reference changed. Generate the full podcast again.")
        parent_settings = self._settings_from_manifest(parent, settings, project.artifact)
        pipeline_stage = parent.pipeline[0]
        return self._render(
            project,
            plan=plan,
            settings=parent_settings,
            override_provider=pipeline_stage.provider,
            override_model=pipeline_stage.model,
            require_speaker_reference=parent.speaker_reference is not None,
            target_segment_id=target_segment_id,
            script_text=script_text,
            should_cancel=should_cancel,
            on_progress=on_progress,
        )

    def _render(
        self,
        project: SessionProject,
        *,
        plan: SpeechPlan,
        settings: PodcastRenderSettings,
        override_provider: str,
        override_model: str,
        require_speaker_reference: bool,
        target_segment_id: str | None,
        script_text: str,
        should_cancel: Callable[[], bool] | None,
        on_progress: Callable[[PodcastRenderProgress], None] | None,
    ) -> PodcastRenderResult:
        if project.script is None:
            raise ValueError("Cannot render without a script.")
        artifact = project.artifact or ArtifactRecord(session_id=project.session.session_id)
        project.artifact = artifact
        speaker_reference = self._speaker_reference_snapshot(artifact.speaker_reference)
        if require_speaker_reference and speaker_reference is None:
            raise ValueError("Select a speaker reference before generating podcast audio.")

        tts_config = self.config_store.load_tts_config()
        if override_provider:
            tts_config.provider = override_provider
        if override_model:
            tts_config.model = override_model
            tts_config.local_model_path = ""
        tts_config.audio_format = "wav"
        provider = build_tts_provider(tts_config)
        local_capabilities = None
        if tts_config.provider == "local_mlx":
            local_capabilities = capabilities_for_model(resolve_model_spec(override_model or tts_config.local_model_path or tts_config.model))

        render_id = uuid4().hex
        parent = project.render_manifest if target_segment_id else None
        if target_segment_id:
            window = plan.context_window(target_segment_id, radius=1)
            render_positions = {segment.position for segment in window}
            affected_ids = tuple(segment.segment_id for segment in window)
        else:
            window = plan.segments
            render_positions = {segment.position for segment in plan.segments}
            affected_ids = tuple(segment.segment_id for segment in plan.segments)

        parent_by_position = {segment.position: segment for segment in parent.segments} if parent else {}
        rendered: list[RenderedSegment] = []
        created_paths: list[Path] = []
        provider_name = tts_config.provider
        model_name = override_model or tts_config.model
        adapter_version = "tts-api-v1"
        previous_context: tuple[str, str] | None = None
        assembler = PodcastAudioAssembler(AssemblySpec(target_rms_dbfs=-19.0))
        try:
            for position, segment in enumerate(plan.segments):
                self._raise_if_cancelled(should_cancel)
                if position not in render_positions:
                    previous = parent_by_position.get(position)
                    if previous is None or previous.segment_hash != segment.segment_hash:
                        raise ValueError("A segment outside the regeneration window changed; generate the full podcast again.")
                    self._verified_segment_audio(previous)
                    rendered.append(previous)
                    previous_context = (previous.audio_path, _apply_pronunciations(segment)[0])
                    continue
                start_percent = 10.0 + 72.0 * position / max(1, len(plan.segments))
                self._notify(
                    on_progress,
                    start_percent,
                    f"Rendering speech segment {position + 1} / {len(plan.segments)}...",
                    position + 1,
                    len(plan.segments),
                )
                response = self._render_segment(
                    provider=provider,
                    provider_name=tts_config.provider,
                    session_id=project.session.session_id,
                    segment=segment,
                    settings=settings,
                    speaker_reference=speaker_reference,
                    local_capabilities=local_capabilities,
                    previous_context=previous_context,
                    should_cancel=should_cancel,
                )
                provider_name = response.provider_name
                model_name = response.model_name
                adapter_version = response.adapter_version
                normalized = assembler.normalize_segment(response.audio_bytes)
                segment_artifact_id = uuid4().hex
                audio_path = self.artifact_store.write_segment_audio(
                    project.session.session_id,
                    segment_artifact_id,
                    normalized.audio_bytes,
                )
                created_paths.append(audio_path)
                rendered.append(
                    RenderedSegment(
                        segment_artifact_id=segment_artifact_id,
                        segment_id=segment.segment_id,
                        position=segment.position,
                        text_hash=segment.text_hash,
                        segment_hash=segment.segment_hash,
                        audio_path=str(audio_path),
                        audio_hash=sha256_bytes(normalized.audio_bytes),
                        duration_ms=normalized.duration_ms,
                        generated_by_render_id=render_id,
                        seed=None,
                    )
                )
                previous_context = (str(audio_path), _apply_pronunciations(segment)[0])
            rendered.sort(key=lambda item: item.position)
            self._raise_if_cancelled(should_cancel)
            self._notify(on_progress, 86.0, "Assembling pauses, loudness, and segment boundaries...")
            segment_by_id = {segment.segment_id: segment for segment in plan.segments}
            master = assembler.assemble(
                [
                    (self._verified_segment_audio(item), segment_by_id[item.segment_id].pause_after_ms)
                    for item in rendered
                ]
            )
            audio_path = self.artifact_store.write_render_audio(project.session.session_id, render_id, master.audio_bytes)
            created_paths.append(audio_path)
            transcript_path = self.artifact_store.write_render_transcript(project.session.session_id, render_id, script_text)
            created_paths.append(transcript_path)
            manifest = RenderManifest(
                render_id=render_id,
                session_id=project.session.session_id,
                script_id=project.script.script_id,
                script_hash=plan.script_hash,
                speech_plan=SpeechPlanReference(plan.plan_id, plan.version, plan.plan_hash),
                speaker_reference=speaker_reference,
                pipeline=(PipelineStage("speech_synthesis", provider_name, model_name, adapter_version),),
                parent_render_id=parent.render_id if parent else None,
                regeneration=(
                    RegenerationWindow(target_segment_id, affected_ids)
                    if target_segment_id
                    else None
                ),
                segments=tuple(rendered),
                assembly=assembler.spec,
                output=RenderOutput(
                    audio_path=str(audio_path),
                    audio_hash=sha256_bytes(master.audio_bytes),
                    transcript_path=str(transcript_path),
                    duration_ms=master.duration_ms,
                ),
            )
            manifest.validate()
        except Exception:
            for path in created_paths:
                try:
                    self.artifact_store.delete_export_file(path)
                except (OSError, ValueError):
                    pass
            raise

        project.render_manifest = manifest
        take = AudioTakeRecord(
            take_id=render_id,
            session_id=project.session.session_id,
            script_id=project.script.script_id,
            speech_plan_id=plan.plan_id,
            render_id=render_id,
            audio_path=str(audio_path),
            transcript_path=str(transcript_path),
            provider=provider_name,
            model=model_name,
            voice_id=settings.voice_id,
            voice_name=settings.voice_name,
            style_id=settings.style_id,
            style_name=settings.style_name,
            speed=1.0,
            language=settings.language,
            audio_format="wav",
        )
        retained = [item for item in artifact.takes if artifact.final_take_id and item.take_id == artifact.final_take_id]
        artifact.takes = (retained + [take])[-2:]
        artifact.final_take_id = take.take_id
        artifact.audio_path = take.audio_path
        artifact.transcript_path = take.transcript_path
        artifact.provider = take.provider
        artifact.voice_settings = {
            "voice_id": settings.voice_id,
            "voice_name": settings.voice_name,
            "style_id": settings.style_id,
            "style_name": settings.style_name,
            "speed": 1.0,
            "language": settings.language,
            "audio_format": "wav",
        }
        self._notify(on_progress, 96.0, "Saving podcast render manifest...")
        return PodcastRenderResult(
            project=project,
            provider=provider_name,
            model=model_name,
            audio_path=str(audio_path),
            transcript_path=str(transcript_path),
            affected_segment_ids=affected_ids,
        )

    def _render_segment(
        self,
        *,
        provider: Any,
        provider_name: str,
        session_id: str,
        segment: SpeechSegment,
        settings: PodcastRenderSettings,
        speaker_reference: dict[str, str] | None,
        local_capabilities: Any,
        previous_context: tuple[str, str] | None,
        should_cancel: Callable[[], bool] | None,
    ) -> TTSGenerationResponse:
        provider_text, provider_breaks = _apply_pronunciations(segment)
        style_prompt = ""
        if local_capabilities is None or local_capabilities.style_instruction != SupportLevel.UNSUPPORTED:
            style_prompt = _delivery_prompt(segment, settings.style_prompt)
        reference_audio = speaker_reference["audio_path"] if speaker_reference else ""
        reference_text = speaker_reference["reference_text"] if speaker_reference else ""
        context_audio = ""
        context_text = ""
        if provider_name == "local_mlx" and previous_context is not None:
            context_audio, context_text = previous_context
        if provider_name != "local_mlx" and provider_breaks:
            return self._render_remote_break_units(
                provider=provider,
                session_id=session_id,
                text=provider_text,
                breaks=provider_breaks,
                settings=settings,
                style_prompt=style_prompt,
                reference_audio=reference_audio,
                reference_text=reference_text,
                should_cancel=should_cancel,
            )
        return provider.synthesize(
            TTSGenerationRequest(
                session_id=session_id,
                script_text=provider_text,
                voice=settings.provider_voice,
                audio_format="wav",
                speed=1.0,
                style_id=settings.style_id,
                style_prompt=style_prompt,
                language=settings.language,
                reference_audio_path=reference_audio,
                reference_text=reference_text,
                context_audio_path=context_audio,
                context_text=context_text,
                voice_lock_id=speaker_reference["speaker_reference_id"] if speaker_reference else "",
                breaks=tuple(SpeechBreak(item.offset, item.duration_ms) for item in provider_breaks),
                clone_mode="auto",
                should_cancel=should_cancel,
            )
        )

    def _render_remote_break_units(
        self,
        *,
        provider: Any,
        session_id: str,
        text: str,
        breaks: tuple[PlannedBreak, ...],
        settings: PodcastRenderSettings,
        style_prompt: str,
        reference_audio: str,
        reference_text: str,
        should_cancel: Callable[[], bool] | None,
    ) -> TTSGenerationResponse:
        cursor = 0
        units: list[tuple[bytes, int]] = []
        last_response: TTSGenerationResponse | None = None
        for item in breaks:
            part = text[cursor:item.offset].strip()
            if part:
                last_response = provider.synthesize(
                    TTSGenerationRequest(
                        session_id=session_id,
                        script_text=part,
                        voice=settings.provider_voice,
                        audio_format="wav",
                        style_id=settings.style_id,
                        style_prompt=style_prompt,
                        language=settings.language,
                        reference_audio_path=reference_audio,
                        reference_text=reference_text,
                        should_cancel=should_cancel,
                    )
                )
                units.append((last_response.audio_bytes, item.duration_ms))
            cursor = item.offset
        tail = text[cursor:].strip()
        if tail:
            last_response = provider.synthesize(
                TTSGenerationRequest(
                    session_id=session_id,
                    script_text=tail,
                    voice=settings.provider_voice,
                    audio_format="wav",
                    style_id=settings.style_id,
                    style_prompt=style_prompt,
                    language=settings.language,
                    reference_audio_path=reference_audio,
                    reference_text=reference_text,
                    should_cancel=should_cancel,
                )
            )
            units.append((last_response.audio_bytes, 0))
        if last_response is None:
            raise ValueError("Speech segment contains no renderable text.")
        combined = PodcastAudioAssembler(AssemblySpec(target_rms_dbfs=-19.0)).combine_units(units)
        return TTSGenerationResponse(
            audio_bytes=combined.audio_bytes,
            file_extension="wav",
            provider_name=last_response.provider_name,
            model_name=last_response.model_name,
            adapter_version=last_response.adapter_version,
            sample_rate_hz=48_000,
            channels=1,
        )

    @staticmethod
    def _speaker_reference_snapshot(payload: dict[str, Any] | None) -> dict[str, str] | None:
        if not payload:
            return None
        required = ("speaker_reference_id", "reference_hash", "audio_path", "audio_hash", "reference_text", "language")
        snapshot = {key: str(payload.get(key) or "") for key in required}
        if any(not value for value in snapshot.values()):
            raise ValueError("Selected speaker reference is incomplete. Select it again in Voice Studio.")
        if not Path(snapshot["audio_path"]).is_file():
            raise ValueError("Selected speaker reference audio is missing.")
        audio_hash = sha256_bytes(Path(snapshot["audio_path"]).read_bytes())
        if audio_hash != snapshot["audio_hash"]:
            raise ValueError("Selected speaker reference audio changed after it was saved. Select it again in Voice Studio.")
        reference_hash = sha256_json(
            {
                "audio_hash": snapshot["audio_hash"],
                "reference_text": snapshot["reference_text"],
                "language": snapshot["language"],
            }
        )
        if reference_hash != snapshot["reference_hash"]:
            raise ValueError("Selected speaker reference metadata does not match its hash.")
        return snapshot

    @staticmethod
    def _verified_segment_audio(segment: RenderedSegment) -> bytes:
        path = Path(segment.audio_path)
        if not path.is_file():
            raise ValueError(f"Rendered segment audio is missing: {segment.segment_id}")
        audio_bytes = path.read_bytes()
        if sha256_bytes(audio_bytes) != segment.audio_hash:
            raise ValueError(f"Rendered segment audio hash changed: {segment.segment_id}")
        return audio_bytes

    @staticmethod
    def _settings_from_manifest(
        parent: RenderManifest,
        fallback: PodcastRenderSettings,
        artifact: ArtifactRecord | None,
    ) -> PodcastRenderSettings:
        if artifact is None:
            return fallback
        take = next((item for item in artifact.takes if item.render_id == parent.render_id), None)
        if take is None:
            raise ValueError("The selected render no longer has matching take metadata.")
        return PodcastRenderSettings(
            voice_id=take.voice_id,
            provider_voice=fallback.provider_voice,
            voice_name=take.voice_name,
            style_id=take.style_id,
            style_name=take.style_name,
            style_prompt=resolve_style_preset(take.style_id).prompt,
            language=take.language,
        )

    @staticmethod
    def _script_text(project: SessionProject) -> str:
        if project.script is None:
            raise ValueError("Cannot render without a script.")
        text = project.script.final.strip() or project.script.draft.strip()
        if not text:
            raise ValueError("Cannot render an empty script.")
        return text

    @staticmethod
    def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
        if should_cancel is not None and should_cancel():
            raise TaskCancellationRequested("Podcast audio rendering was cancelled.")

    @staticmethod
    def _notify(
        callback: Callable[[PodcastRenderProgress], None] | None,
        percent: float,
        message: str,
        segment_index: int = 0,
        segments_total: int = 0,
    ) -> None:
        if callback is not None:
            callback(PodcastRenderProgress(percent, message, segment_index, segments_total))


def _delivery_prompt(segment: SpeechSegment, base_prompt: str) -> str:
    emphasized = [segment.text[item.start:item.end] for item in segment.emphasis]
    pieces = [
        base_prompt.strip(),
        "Deliver this as a skilled, natural Chinese solo podcast host.",
        f"Intent: {segment.delivery.intent}.",
        f"Emotion: {segment.delivery.emotion}; keep it restrained and non-theatrical.",
        f"Energy: {segment.delivery.energy:.2f}. Pace: {segment.delivery.pace:.2f}.",
    ]
    if emphasized:
        pieces.append("Gently emphasize: " + "、".join(emphasized) + ".")
    return " ".join(piece for piece in pieces if piece)


def _apply_pronunciations(segment: SpeechSegment) -> tuple[str, tuple[PlannedBreak, ...]]:
    replacements = sorted(segment.pronunciations, key=lambda item: item.start)
    if not replacements:
        return segment.text, segment.breaks
    output: list[str] = []
    cursor = 0
    mapped_breaks: list[PlannedBreak] = []
    break_index = 0
    output_length = 0
    for replacement in replacements:
        prefix = segment.text[cursor:replacement.start]
        while break_index < len(segment.breaks) and segment.breaks[break_index].offset <= replacement.start:
            item = segment.breaks[break_index]
            mapped_breaks.append(PlannedBreak(output_length + item.offset - cursor, item.duration_ms))
            break_index += 1
        output.append(prefix)
        output_length += len(prefix)
        output.append(replacement.spoken_as)
        output_length += len(replacement.spoken_as)
        while break_index < len(segment.breaks) and segment.breaks[break_index].offset <= replacement.end:
            item = segment.breaks[break_index]
            mapped_breaks.append(PlannedBreak(output_length, item.duration_ms))
            break_index += 1
        cursor = replacement.end
    suffix = segment.text[cursor:]
    output.append(suffix)
    while break_index < len(segment.breaks):
        item = segment.breaks[break_index]
        mapped_breaks.append(PlannedBreak(output_length + item.offset - cursor, item.duration_ms))
        break_index += 1
    return "".join(output), tuple(mapped_breaks)
