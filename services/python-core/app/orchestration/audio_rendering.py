from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.artifact import ArtifactRecord
from app.domain.common import sha256_text
from app.domain.project import SessionProject
from app.domain.session import SessionState
from app.domain.speaker_reference import SpeakerReference
from app.domain.voice_studio import STANDARD_PREVIEW_TEXT, clamp_speed, resolve_style_preset, resolve_voice_preset
from app.orchestration.podcast_rendering import (
    PodcastRenderProgress,
    PodcastRenderResult,
    PodcastRenderSettings,
    PodcastRenderingPipeline,
)
from app.providers.tts_api.base import TTSGenerationRequest
from app.providers.tts_api.factory import build_tts_provider
from app.providers.tts_local_mlx.capabilities import SupportLevel, capabilities_for_model
from app.providers.tts_local_mlx.model_spec import resolve_model_spec
from app.runtime.task_cancellation import TaskCancellationRequested
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


@dataclass(frozen=True, slots=True)
class AudioRenderResult:
    project: SessionProject
    provider: str
    model: str
    audio_path: str
    transcript_path: str
    affected_segment_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VoiceRenderSettings:
    voice_id: str = "warm_narrator"
    voice_name: str = ""
    style_id: str = "natural"
    style_name: str = ""
    speed: float = 1.0
    language: str = "zh"
    audio_format: str = "wav"
    preview_text: str = ""


@dataclass(frozen=True, slots=True)
class VoicePreviewResult:
    provider: str
    model: str
    audio_path: str
    settings: VoiceRenderSettings


@dataclass(frozen=True, slots=True)
class AudioRenderProgress:
    """Progress snapshot surfaced to the orchestration caller.

    ``percent`` is a 0-100 completion estimate. ``chunk_index`` and
    ``chunks_total`` are 1-based counters describing the current sentence
    being synthesized; values of 0 mean no chunk information was supplied.
    """

    percent: float
    message: str
    chunk_index: int = 0
    chunks_total: int = 0


class AudioRenderingService:
    def __init__(
        self,
        store: ProjectStore,
        config_store: ConfigStore,
        artifact_store: ArtifactStore,
    ) -> None:
        self.store = store
        self.config_store = config_store
        self.artifact_store = artifact_store
        self.podcast_pipeline = PodcastRenderingPipeline(config_store, artifact_store)

    def render_audio(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        override_model: str = "",
        settings: VoiceRenderSettings | None = None,
        require_speaker_reference: bool = False,
    ) -> AudioRenderResult:
        return self.render_audio_with_cancellation(
            session_id,
            script_id=script_id,
            override_provider=override_provider,
            override_model=override_model,
            settings=settings,
            require_speaker_reference=require_speaker_reference,
        )

    def render_audio_with_cancellation(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        override_model: str = "",
        settings: VoiceRenderSettings | None = None,
        require_speaker_reference: bool = False,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[AudioRenderProgress], None] | None = None,
    ) -> AudioRenderResult:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        if project.script is None:
            raise ValueError("Cannot render audio without a script record.")
        artifact = project.artifact or ArtifactRecord(
            session_id=session_id,
            transcript_path=f"sessions/{session_id}/transcript.json",
            active_script_id=project.script.script_id,
        )
        project.artifact = artifact
        render_settings = self._resolve_render_settings(artifact, settings)
        script_text = project.script.final.strip() or project.script.draft.strip()
        expected_script_hash = sha256_text(script_text)
        expected_active_render_id = project.render_manifest.render_id if project.render_manifest else ""
        previous_state = self.store.begin_audio_render(session_id)
        project.session.transition(SessionState.AUDIO_RENDERING)
        try:
            pipeline_result = self.podcast_pipeline.render_full(
                project,
                settings=self._podcast_settings(render_settings, override_provider),
                override_provider=override_provider,
                override_model=override_model,
                require_speaker_reference=require_speaker_reference,
                should_cancel=should_cancel,
                on_progress=(
                    (lambda progress: on_progress(_audio_progress(progress)))
                    if on_progress is not None
                    else None
                ),
            )
        except TaskCancellationRequested:
            self.store.restore_after_audio_render(
                session_id,
                previous_state=previous_state,
            )
            raise
        except Exception as exc:
            self.store.restore_after_audio_render(
                session_id,
                previous_state=previous_state,
                error_message=str(exc),
            )
            raise
        try:
            project = self._publish_render_result(
                pipeline_result,
                expected_script_hash=expected_script_hash,
                expected_active_render_id=expected_active_render_id,
                previous_state=previous_state,
                should_cancel=should_cancel,
            )
        except TaskCancellationRequested:
            self.store.restore_after_audio_render(
                session_id,
                previous_state=previous_state,
            )
            raise
        except Exception as exc:
            self.store.restore_after_audio_render(
                session_id,
                previous_state=previous_state,
                error_message=str(exc),
            )
            raise
        return AudioRenderResult(
            project=project,
            provider=pipeline_result.provider,
            model=pipeline_result.model,
            audio_path=pipeline_result.audio_path,
            transcript_path=pipeline_result.transcript_path,
            affected_segment_ids=pipeline_result.affected_segment_ids,
        )

    def regenerate_audio_window_with_cancellation(
        self,
        session_id: str,
        *,
        script_id: str,
        target_segment_id: str,
        expected_plan_id: str,
        expected_render_id: str,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[AudioRenderProgress], None] | None = None,
    ) -> AudioRenderResult:
        project = self.store.load_project_for_script(session_id, script_id)
        if project.artifact is None:
            raise ValueError("Cannot regenerate podcast audio without a rendered artifact.")
        assert project.script is not None
        script_text = project.script.final.strip() or project.script.draft.strip()
        expected_script_hash = sha256_text(script_text)
        expected_active_render_id = project.render_manifest.render_id if project.render_manifest else ""
        settings = self._resolve_render_settings(project.artifact, None)
        previous_state = self.store.begin_audio_render(session_id)
        project.session.transition(SessionState.AUDIO_RENDERING)
        try:
            pipeline_result = self.podcast_pipeline.regenerate_window(
                project,
                target_segment_id=target_segment_id,
                expected_plan_id=expected_plan_id,
                expected_render_id=expected_render_id,
                settings=self._podcast_settings(
                    settings,
                    project.render_manifest.pipeline[0].provider if project.render_manifest else "",
                ),
                should_cancel=should_cancel,
                on_progress=(
                    (lambda progress: on_progress(_audio_progress(progress)))
                    if on_progress is not None
                    else None
                ),
            )
        except TaskCancellationRequested:
            self.store.restore_after_audio_render(
                session_id,
                previous_state=previous_state,
            )
            raise
        except Exception as exc:
            self.store.restore_after_audio_render(
                session_id,
                previous_state=previous_state,
                error_message=str(exc),
            )
            raise
        try:
            project = self._publish_render_result(
                pipeline_result,
                expected_script_hash=expected_script_hash,
                expected_active_render_id=expected_active_render_id,
                previous_state=previous_state,
                should_cancel=should_cancel,
            )
        except TaskCancellationRequested:
            self.store.restore_after_audio_render(
                session_id,
                previous_state=previous_state,
            )
            raise
        except Exception as exc:
            self.store.restore_after_audio_render(
                session_id,
                previous_state=previous_state,
                error_message=str(exc),
            )
            raise
        return AudioRenderResult(
            project=project,
            provider=pipeline_result.provider,
            model=pipeline_result.model,
            audio_path=pipeline_result.audio_path,
            transcript_path=pipeline_result.transcript_path,
            affected_segment_ids=pipeline_result.affected_segment_ids,
        )

    def render_voice_preview(
        self,
        settings: VoiceRenderSettings,
        *,
        override_provider: str = "",
        override_model: str = "",
    ) -> VoicePreviewResult:
        return self.render_voice_preview_with_cancellation(
            settings,
            override_provider=override_provider,
            override_model=override_model,
        )

    def save_voice_settings(
        self,
        session_id: str,
        settings: VoiceRenderSettings,
        *,
        script_id: str = "",
    ) -> SessionProject:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        normalized = self._normalize_settings(settings)
        artifact = self.store.update_script_audio_preferences(
            session_id,
            project.script.script_id if project.script is not None else "",
            voice_settings=self._settings_to_dict(normalized),
        )
        project.artifact = artifact
        return project

    def select_speaker_reference(
        self,
        session_id: str,
        *,
        script_id: str = "",
        reference: SpeakerReference,
    ) -> SessionProject:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        self._validate_reference_audio_path(reference.audio_path)
        artifact = self.store.update_script_audio_preferences(
            session_id,
            project.script.script_id if project.script is not None else "",
            speaker_reference=reference.to_dict(),
            replace_speaker_reference=True,
        )
        project.artifact = artifact
        return project

    def render_voice_preview_with_cancellation(
        self,
        settings: VoiceRenderSettings,
        *,
        override_provider: str = "",
        override_model: str = "",
        speaker_reference: dict[str, object] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[AudioRenderProgress], None] | None = None,
    ) -> VoicePreviewResult:
        normalized = self._normalize_settings(settings)
        tts_config = self.config_store.load_tts_config()
        if override_provider:
            tts_config.provider = override_provider
        if override_model:
            tts_config.model = override_model
            tts_config.local_model_path = ""
        tts_config.voice = self._provider_voice_for(normalized, tts_config.provider)
        tts_config.audio_format = normalized.audio_format or tts_config.audio_format
        provider = build_tts_provider(tts_config)
        style = resolve_style_preset(normalized.style_id)
        request_speed = normalized.speed
        style_prompt = style.prompt
        if tts_config.provider == "local_mlx":
            spec = resolve_model_spec(tts_config.local_model_path or tts_config.model)
            capabilities = capabilities_for_model(spec)
            if capabilities.speed_control == SupportLevel.UNSUPPORTED:
                request_speed = 1.0
            if capabilities.style_instruction == SupportLevel.UNSUPPORTED:
                style_prompt = ""
        preview_text = normalized.preview_text.strip() or STANDARD_PREVIEW_TEXT
        resolved_reference: dict[str, object] = {}
        if tts_config.provider == "local_mlx" and speaker_reference:
            audio_path = str(speaker_reference.get("audio_path") or "")
            if audio_path:
                self._validate_reference_audio_path(audio_path)
                resolved_reference = dict(speaker_reference)

        def raise_if_cancelled() -> None:
            if should_cancel is not None and should_cancel():
                raise TaskCancellationRequested("Voice preview rendering cancelled.")

        def forward_provider_event(event: Any) -> None:
            if on_progress is None:
                return
            snapshot = _translate_provider_event(event)
            if snapshot is not None:
                on_progress(snapshot)

        request = TTSGenerationRequest(
            session_id="voice-preview",
            script_text=preview_text,
            voice=tts_config.voice,
            audio_format=tts_config.audio_format,
            speed=request_speed,
            style_id=normalized.style_id,
            style_prompt=style_prompt,
            language=normalized.language,
            reference_audio_path=str(resolved_reference.get("audio_path") or ""),
            reference_text=str(
                resolved_reference.get("reference_text") or ""
            ),
            voice_lock_id=str(resolved_reference.get("speaker_reference_id") or ""),
            should_cancel=should_cancel,
            on_progress=forward_provider_event,
        )
        raise_if_cancelled()
        if on_progress is not None:
            on_progress(AudioRenderProgress(percent=8.0, message="Preparing voice preview..."))
        response = provider.synthesize(request)
        raise_if_cancelled()
        if on_progress is not None:
            on_progress(AudioRenderProgress(percent=96.0, message="Writing voice preview audio..."))
        audio_path = self.artifact_store.write_preview_audio(response.audio_bytes, response.file_extension)
        return VoicePreviewResult(
            provider=response.provider_name,
            model=response.model_name,
            audio_path=str(audio_path),
            settings=normalized,
        )

    def delete_generated_audio(self, session_id: str, *, script_id: str = "") -> SessionProject:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        artifact = project.artifact
        if artifact is None:
            raise ValueError("Cannot delete audio without an artifact record.")

        if project.script is not None:
            manifests = self.store.list_render_manifests(session_id, project.script.script_id)
            paths = {
                path
                for manifest in manifests
                for path in (
                    *(segment.audio_path for segment in manifest.segments),
                    manifest.output.audio_path,
                    manifest.output.transcript_path,
                )
            }
            for path in paths:
                self._delete_artifact_file(path)
            self.store.delete_render_manifest(session_id, project.script.script_id)
            project.render_manifest = None

        self._delete_artifact_file(artifact.audio_path)
        self._delete_artifact_file(artifact.transcript_path)
        for take in artifact.takes:
            self._delete_artifact_file(take.audio_path)
            self._delete_artifact_file(take.transcript_path)
        artifact.takes = []

        artifact.audio_path = ""
        artifact.transcript_path = ""
        artifact.provider = ""
        artifact.final_take_id = ""
        self.store.save_artifact(artifact)
        return project

    def _resolve_render_settings(
        self,
        artifact: ArtifactRecord,
        settings: VoiceRenderSettings | None,
    ) -> VoiceRenderSettings:
        if settings is not None:
            return self._normalize_settings(settings)
        if artifact.voice_settings:
            return self._normalize_settings(self._settings_from_dict(artifact.voice_settings))
        return self._normalize_settings(VoiceRenderSettings())

    def _normalize_settings(self, settings: VoiceRenderSettings) -> VoiceRenderSettings:
        voice = resolve_voice_preset(settings.voice_id)
        style = resolve_style_preset(settings.style_id)
        return VoiceRenderSettings(
            voice_id=voice.voice_id,
            voice_name=settings.voice_name.strip() or voice.name,
            style_id=style.style_id,
            style_name=settings.style_name.strip() or style.name,
            speed=clamp_speed(float(settings.speed or 1.0)),
            language=settings.language.strip() or "zh",
            audio_format=(settings.audio_format.strip() or "wav").lstrip("."),
            preview_text=settings.preview_text.strip(),
        )

    def _podcast_settings(
        self,
        settings: VoiceRenderSettings,
        provider_override: str = "",
    ) -> PodcastRenderSettings:
        provider = provider_override.strip() or self.config_store.load_tts_config().provider
        style = resolve_style_preset(settings.style_id)
        return PodcastRenderSettings(
            voice_id=settings.voice_id,
            provider_voice=self._provider_voice_for(settings, provider),
            voice_name=settings.voice_name,
            style_id=settings.style_id,
            style_name=settings.style_name,
            style_prompt=style.prompt,
            language=settings.language,
        )

    def _provider_voice_for(self, settings: VoiceRenderSettings, provider: str = "") -> str:
        if provider == "local_mlx":
            return _local_mlx_voice_for(settings.voice_id, settings.language)
        return resolve_voice_preset(settings.voice_id).provider_voice

    def _settings_to_dict(self, settings: VoiceRenderSettings) -> dict[str, object]:
        return {
            "voice_id": settings.voice_id,
            "voice_name": settings.voice_name,
            "style_id": settings.style_id,
            "style_name": settings.style_name,
            "speed": settings.speed,
            "language": settings.language,
            "audio_format": settings.audio_format,
        }

    def _settings_from_dict(self, payload: dict[str, Any]) -> VoiceRenderSettings:
        return VoiceRenderSettings(
            voice_id=str(payload.get("voice_id") or "warm_narrator"),
            voice_name=str(payload.get("voice_name") or ""),
            style_id=str(payload.get("style_id") or "natural"),
            style_name=str(payload.get("style_name") or ""),
            speed=float(payload.get("speed") or 1.0),
            language=str(payload.get("language") or "zh"),
            audio_format=str(payload.get("audio_format") or "wav"),
            preview_text=str(payload.get("preview_text") or ""),
        )

    def _validate_reference_audio_path(self, path: str) -> Path:
        if not path.strip():
            raise ValueError("Cannot lock voice preview without a preview audio path.")
        data_dir = self.artifact_store.exports_dir.parent.resolve()
        target = Path(path).expanduser().resolve()
        if not target.exists():
            raise ValueError("Locked voice preview audio is missing. Re-render and lock a new preview.")
        if not target.is_file():
            raise ValueError("Locked voice preview path must point to an audio file.")
        if not _is_allowed_speaker_reference_path(target, data_dir):
            raise ValueError("Speaker reference audio must be inside the app data directory or packaged reference assets.")
        return target

    def _delete_artifact_file(self, path: str) -> None:
        if not path.strip():
            return
        self.artifact_store.delete_export_file(Path(path))

    def _publish_render_result(
        self,
        result: PodcastRenderResult,
        *,
        expected_script_hash: str,
        expected_active_render_id: str,
        previous_state: SessionState,
        should_cancel: Callable[[], bool] | None,
    ) -> SessionProject:
        if should_cancel is not None and should_cancel():
            self._delete_unpublished_render(result)
            raise TaskCancellationRequested("Podcast audio rendering was cancelled before publication.")
        try:
            return self.store.publish_render(
                result.project,
                expected_script_hash=expected_script_hash,
                expected_active_render_id=expected_active_render_id,
                tts_provider=result.provider,
                next_session_state=_resolve_post_render_state(previous_state),
            )
        except Exception:
            self._delete_unpublished_render(result)
            raise

    def _delete_unpublished_render(self, result: PodcastRenderResult) -> None:
        manifest = result.project.render_manifest
        if manifest is None:
            return
        paths = [
            segment.audio_path
            for segment in manifest.segments
            if segment.generated_by_render_id == manifest.render_id
        ]
        paths.extend((manifest.output.audio_path, manifest.output.transcript_path))
        for path in paths:
            try:
                self._delete_artifact_file(path)
            except (OSError, ValueError):
                continue

_PROVIDER_RENDER_WINDOW = (10.0, 90.0)

_PRESERVED_SESSION_STATES = {
    SessionState.TOPIC_DEFINED,
    SessionState.INTERVIEW_IN_PROGRESS,
    SessionState.READINESS_EVALUATION,
    SessionState.READY_TO_GENERATE,
}


def _should_preserve_session_state(previous_state: SessionState) -> bool:
    return previous_state in _PRESERVED_SESSION_STATES


def _resolve_post_render_state(previous_state: SessionState) -> SessionState:
    if _should_preserve_session_state(previous_state):
        return previous_state
    return SessionState.COMPLETED


def _translate_provider_event(event: Any) -> AudioRenderProgress | None:
    """Convert a provider-specific progress event into a task snapshot.

    We currently understand the :class:`ChunkProgressEvent` emitted by the
    local MLX runner; other providers that do not emit progress produce no
    snapshot and the heartbeat / phase markers drive the UI instead.
    """

    phase = getattr(event, "phase", None)
    index = getattr(event, "index", None)
    total = getattr(event, "total", None)
    if not isinstance(phase, str) or not isinstance(index, int) or not isinstance(total, int):
        return None
    if total <= 0:
        return None

    start, end = _PROVIDER_RENDER_WINDOW
    span = max(end - start, 0.1)

    if phase == "chunk_started":
        fraction = index / total
        message = f"Synthesizing chunk {index + 1} / {total}"
    elif phase == "chunk_done":
        completed = index + 1
        fraction = completed / total
        message = f"Rendered chunk {completed} / {total}"
    else:
        return None

    fraction = max(0.0, min(1.0, fraction))
    percent = start + span * fraction
    return AudioRenderProgress(
        percent=percent,
        message=message,
        chunk_index=index + 1,
        chunks_total=total,
    )


def _audio_progress(progress: PodcastRenderProgress) -> AudioRenderProgress:
    return AudioRenderProgress(
        percent=progress.percent,
        message=progress.message,
        chunk_index=progress.segment_index,
        chunks_total=progress.segments_total,
    )


_LOCAL_MLX_CHINESE_VOICES = {
    "warm_narrator": "Vivian",
    "news_anchor": "Serena",
    "casual_chat": "Dylan",
    "deep_story": "Uncle_Fu",
    "bright_energy": "Eric",
}

_LOCAL_MLX_ENGLISH_VOICES = {
    "warm_narrator": "Ryan",
    "news_anchor": "Ryan",
    "casual_chat": "Aiden",
    "deep_story": "Ryan",
    "bright_energy": "Aiden",
}


def _local_mlx_voice_for(voice_id: str, language: str) -> str:
    language_key = language.strip().lower().replace("_", "-")
    if language_key.startswith("en"):
        return _LOCAL_MLX_ENGLISH_VOICES.get(voice_id, "Ryan")
    return _LOCAL_MLX_CHINESE_VOICES.get(voice_id, "Vivian")


def _is_allowed_speaker_reference_path(target: Path, data_dir: Path) -> bool:
    try:
        target.relative_to(data_dir)
        return True
    except ValueError:
        pass
    assets_dir = Path(__file__).resolve().parents[1] / "assets" / "speaker-references"
    try:
        target.relative_to(assets_dir)
        return True
    except ValueError:
        return False
