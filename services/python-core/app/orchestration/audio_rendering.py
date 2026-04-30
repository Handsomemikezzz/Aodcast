from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.domain.artifact import ArtifactRecord, AudioTakeRecord
from app.domain.common import utc_now_iso
from app.domain.project import SessionProject
from app.domain.session import SessionState
from app.domain.voice_studio import STANDARD_PREVIEW_TEXT, clamp_speed, resolve_style_preset, resolve_voice_preset
from app.providers.tts_api.base import TTSGenerationRequest
from app.providers.tts_api.factory import build_tts_provider
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
class VoiceTakeRenderResult(AudioRenderResult):
    take: AudioTakeRecord


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

    def render_audio(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        settings: VoiceRenderSettings | None = None,
    ) -> AudioRenderResult:
        return self.render_audio_with_cancellation(
            session_id,
            script_id=script_id,
            override_provider=override_provider,
            settings=settings,
        )

    def render_audio_with_cancellation(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        settings: VoiceRenderSettings | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[AudioRenderProgress], None] | None = None,
    ) -> AudioRenderResult:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        script = project.script
        artifact = project.artifact
        if script is None:
            raise ValueError("Cannot render audio without a script record.")
        if artifact is None:
            artifact = ArtifactRecord(
                session_id=session_id,
                transcript_path=f"sessions/{session_id}/transcript.json",
                active_script_id=script.script_id,
            )
            project.artifact = artifact
            self.store.save_project(project)
        if project.session.state == SessionState.AUDIO_RENDERING:
            raise ValueError("Cannot render audio while another audio render is already in progress.")

        final_text = script.final.strip() or script.draft.strip()
        if not final_text:
            raise ValueError("Cannot render audio without script content.")

        render_settings = self._resolve_render_settings(artifact, settings)
        tts_config = self.config_store.load_tts_config()
        if override_provider:
            tts_config.provider = override_provider
        tts_config.voice = self._provider_voice_for(render_settings, tts_config.provider)
        tts_config.audio_format = render_settings.audio_format or tts_config.audio_format
        provider = build_tts_provider(tts_config)
        voice_reference = self._voice_reference_for(artifact, tts_config.provider)
        previous_state = project.session.state

        project.session.transition(SessionState.AUDIO_RENDERING)
        self.store.save_project(project)

        def raise_if_cancelled() -> None:
            if should_cancel is None or not should_cancel():
                return
            project.session.transition(previous_state)
            self.store.save_project(project)
            raise TaskCancellationRequested(f"Audio rendering cancelled for session {session_id}.")

        def forward_provider_event(event: Any) -> None:
            if on_progress is None:
                return
            snapshot = _translate_provider_event(event)
            if snapshot is None:
                return
            on_progress(snapshot)

        style = resolve_style_preset(render_settings.style_id)
        request = TTSGenerationRequest(
            session_id=session_id,
            script_text=final_text,
            voice=tts_config.voice,
            audio_format=tts_config.audio_format,
            speed=render_settings.speed,
            style_id=render_settings.style_id,
            style_prompt=style.prompt,
            language=render_settings.language,
            reference_audio_path=str(voice_reference.get("audio_path") or ""),
            reference_text=str(voice_reference.get("preview_text") or ""),
            voice_lock_id=str(voice_reference.get("lock_id") or ""),
            should_cancel=should_cancel,
            on_progress=forward_provider_event,
        )
        try:
            raise_if_cancelled()
            if on_progress is not None:
                on_progress(AudioRenderProgress(percent=7.0, message="Loading voice model..."))
            response = provider.synthesize(request)
            raise_if_cancelled()
            if on_progress is not None:
                on_progress(
                    AudioRenderProgress(percent=95.0, message="Writing transcript and audio artifacts...")
                )
            transcript_path = self.artifact_store.write_transcript(session_id, final_text)
            audio_path = self.artifact_store.write_audio(
                session_id,
                response.audio_bytes,
                response.file_extension,
            )
        except TaskCancellationRequested:
            project.session.transition(previous_state)
            self.store.save_project(project)
            raise
        except Exception as exc:
            if _should_preserve_session_state(previous_state):
                project.session.transition(previous_state)
                project.session.record_error(str(exc))
            else:
                project.session.set_error(str(exc))
            self.store.save_project(project)
            raise

        artifact.transcript_path = str(transcript_path)
        artifact.audio_path = str(audio_path)
        artifact.provider = response.provider_name
        artifact.voice_settings = self._settings_to_dict(render_settings)
        artifact.final_take_id = ""
        project.session.tts_provider = response.provider_name
        project.session.transition(_resolve_post_render_state(previous_state))
        self.store.save_project(project)

        return AudioRenderResult(
            project=project,
            provider=response.provider_name,
            model=response.model_name,
            audio_path=str(audio_path),
            transcript_path=str(transcript_path),
        )

    def render_voice_preview(
        self,
        settings: VoiceRenderSettings,
        *,
        override_provider: str = "",
    ) -> VoicePreviewResult:
        return self.render_voice_preview_with_cancellation(settings, override_provider=override_provider)

    def save_voice_settings(
        self,
        session_id: str,
        settings: VoiceRenderSettings,
        *,
        script_id: str = "",
    ) -> SessionProject:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        artifact = project.artifact
        if artifact is None:
            artifact = ArtifactRecord(
                session_id=session_id,
                transcript_path=f"sessions/{session_id}/transcript.json",
                active_script_id=project.script.script_id if project.script is not None else "",
            )
            project.artifact = artifact
        normalized = self._normalize_settings(settings)
        artifact.voice_settings = self._settings_to_dict(normalized)
        self.store.save_project(project)
        return project

    def lock_voice_preview(
        self,
        session_id: str,
        *,
        script_id: str = "",
        preview_audio_path: str,
        settings: VoiceRenderSettings,
        provider: str,
        model: str,
    ) -> SessionProject:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        artifact = project.artifact
        if artifact is None:
            artifact = ArtifactRecord(
                session_id=session_id,
                transcript_path=f"sessions/{session_id}/transcript.json",
                active_script_id=project.script.script_id if project.script is not None else "",
            )
            project.artifact = artifact

        normalized = self._normalize_settings(settings)
        reference_audio = self._validate_reference_audio_path(preview_audio_path)
        preview_text = normalized.preview_text.strip() or STANDARD_PREVIEW_TEXT
        artifact.voice_settings = self._settings_to_dict(normalized)
        artifact.voice_reference = {
            "lock_id": uuid4().hex,
            "audio_path": str(reference_audio),
            "preview_text": preview_text,
            "provider": provider.strip(),
            "model": model.strip(),
            "voice_id": normalized.voice_id,
            "voice_name": normalized.voice_name,
            "style_id": normalized.style_id,
            "style_name": normalized.style_name,
            "speed": normalized.speed,
            "language": normalized.language,
            "audio_format": normalized.audio_format,
            "created_at": utc_now_iso(),
        }
        self.store.save_project(project)
        return project

    def render_voice_preview_with_cancellation(
        self,
        settings: VoiceRenderSettings,
        *,
        override_provider: str = "",
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[AudioRenderProgress], None] | None = None,
    ) -> VoicePreviewResult:
        normalized = self._normalize_settings(settings)
        tts_config = self.config_store.load_tts_config()
        if override_provider:
            tts_config.provider = override_provider
        tts_config.voice = self._provider_voice_for(normalized, tts_config.provider)
        tts_config.audio_format = normalized.audio_format or tts_config.audio_format
        provider = build_tts_provider(tts_config)
        style = resolve_style_preset(normalized.style_id)
        preview_text = normalized.preview_text.strip() or STANDARD_PREVIEW_TEXT

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
            speed=normalized.speed,
            style_id=normalized.style_id,
            style_prompt=style.prompt,
            language=normalized.language,
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

    def render_voice_take(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        settings: VoiceRenderSettings,
    ) -> VoiceTakeRenderResult:
        return self.render_voice_take_with_cancellation(
            session_id,
            script_id=script_id,
            override_provider=override_provider,
            settings=settings,
        )

    def render_voice_take_with_cancellation(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        settings: VoiceRenderSettings,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[AudioRenderProgress], None] | None = None,
    ) -> VoiceTakeRenderResult:
        normalized = self._normalize_settings(settings)
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        script = project.script
        artifact = project.artifact
        if script is None or artifact is None:
            raise ValueError("Cannot render audio without script and artifact records.")
        if project.session.state == SessionState.AUDIO_RENDERING:
            raise ValueError("Cannot render audio while another audio render is already in progress.")

        final_text = script.final.strip() or script.draft.strip()
        if not final_text:
            raise ValueError("Cannot render audio without script content.")

        tts_config = self.config_store.load_tts_config()
        if override_provider:
            tts_config.provider = override_provider
        tts_config.voice = self._provider_voice_for(normalized, tts_config.provider)
        tts_config.audio_format = normalized.audio_format or tts_config.audio_format
        provider = build_tts_provider(tts_config)
        voice_reference = self._voice_reference_for(artifact, tts_config.provider)
        previous_state = project.session.state

        project.session.transition(SessionState.AUDIO_RENDERING)
        self.store.save_project(project)

        def raise_if_cancelled() -> None:
            if should_cancel is None or not should_cancel():
                return
            project.session.transition(previous_state)
            self.store.save_project(project)
            raise TaskCancellationRequested(f"Audio rendering cancelled for session {session_id}.")

        def forward_provider_event(event: Any) -> None:
            if on_progress is None:
                return
            snapshot = _translate_provider_event(event)
            if snapshot is not None:
                on_progress(snapshot)

        style = resolve_style_preset(normalized.style_id)
        request = TTSGenerationRequest(
            session_id=session_id,
            script_text=final_text,
            voice=tts_config.voice,
            audio_format=tts_config.audio_format,
            speed=normalized.speed,
            style_id=normalized.style_id,
            style_prompt=style.prompt,
            language=normalized.language,
            reference_audio_path=str(voice_reference.get("audio_path") or ""),
            reference_text=str(voice_reference.get("preview_text") or ""),
            voice_lock_id=str(voice_reference.get("lock_id") or ""),
            should_cancel=should_cancel,
            on_progress=forward_provider_event,
        )
        take_id = uuid4().hex
        try:
            raise_if_cancelled()
            if on_progress is not None:
                on_progress(AudioRenderProgress(percent=7.0, message="Loading voice model..."))
            response = provider.synthesize(request)
            raise_if_cancelled()
            if on_progress is not None:
                on_progress(AudioRenderProgress(percent=95.0, message="Writing take artifacts..."))
            transcript_path = self.artifact_store.write_named_transcript(session_id, final_text, f"transcript-{take_id}")
            audio_path = self.artifact_store.write_named_audio(session_id, response.audio_bytes, response.file_extension, f"audio-{take_id}")
        except TaskCancellationRequested:
            project.session.transition(previous_state)
            self.store.save_project(project)
            raise
        except Exception as exc:
            if _should_preserve_session_state(previous_state):
                project.session.transition(previous_state)
                project.session.record_error(str(exc))
            else:
                project.session.set_error(str(exc))
            self.store.save_project(project)
            raise

        take = AudioTakeRecord(
            take_id=take_id,
            session_id=session_id,
            script_id=script.script_id,
            audio_path=str(audio_path),
            transcript_path=str(transcript_path),
            provider=response.provider_name,
            model=response.model_name,
            voice_id=normalized.voice_id,
            voice_name=normalized.voice_name,
            style_id=normalized.style_id,
            style_name=normalized.style_name,
            speed=normalized.speed,
            language=normalized.language,
            audio_format=response.file_extension,
        )
        artifact.takes = self._append_take_with_retention(artifact.takes, artifact.final_take_id, take)
        artifact.final_take_id = take.take_id
        artifact.audio_path = take.audio_path
        artifact.transcript_path = take.transcript_path
        artifact.provider = take.provider
        artifact.voice_settings = self._settings_to_dict(normalized)
        project.session.tts_provider = response.provider_name
        project.session.transition(_resolve_post_render_state(previous_state))
        self.store.save_project(project)

        return VoiceTakeRenderResult(
            project=project,
            provider=response.provider_name,
            model=response.model_name,
            audio_path=str(audio_path),
            transcript_path=str(transcript_path),
            take=take,
        )

    def set_final_voice_take(self, session_id: str, take_id: str) -> SessionProject:
        project = self.store.load_project(session_id)
        artifact = project.artifact
        if artifact is None:
            raise ValueError("Cannot set final audio without an artifact record.")
        take_script_id = artifact.script_id_for_take(take_id)
        if take_script_id and project.script is not None and take_script_id != project.script.script_id:
            project = self.store.load_project_for_script(session_id, take_script_id)
            artifact = project.artifact
            if artifact is None:
                raise ValueError("Cannot set final audio without an artifact record.")
        selected = next((take for take in artifact.takes if take.take_id == take_id), None)
        if selected is None:
            raise ValueError(f"Unknown take_id '{take_id}' for session {session_id}.")
        artifact.final_take_id = selected.take_id
        artifact.audio_path = selected.audio_path
        artifact.transcript_path = selected.transcript_path
        artifact.provider = selected.provider
        artifact.voice_settings = self._settings_to_dict(self._settings_from_take(selected))
        project.session.tts_provider = selected.provider
        self.store.save_project(project)
        return project

    def delete_generated_audio(self, session_id: str, *, script_id: str = "") -> SessionProject:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        artifact = project.artifact
        if artifact is None:
            raise ValueError("Cannot delete audio without an artifact record.")

        self._delete_artifact_file(artifact.audio_path)
        self._delete_artifact_file(artifact.transcript_path)
        if artifact.final_take_id:
            selected = next((take for take in artifact.takes if take.take_id == artifact.final_take_id), None)
            if selected is not None:
                self._delete_artifact_file(selected.audio_path)
                self._delete_artifact_file(selected.transcript_path)
            artifact.takes = [take for take in artifact.takes if take.take_id != artifact.final_take_id]

        artifact.audio_path = ""
        artifact.transcript_path = ""
        artifact.provider = ""
        artifact.final_take_id = ""
        self.store.save_project(project)
        return project

    def delete_voice_take(self, session_id: str, take_id: str) -> SessionProject:
        project = self.store.load_project(session_id)
        artifact = project.artifact
        if artifact is None:
            raise ValueError("Cannot delete take without an artifact record.")
        take_script_id = artifact.script_id_for_take(take_id)
        if take_script_id and project.script is not None and take_script_id != project.script.script_id:
            project = self.store.load_project_for_script(session_id, take_script_id)
            artifact = project.artifact
            if artifact is None:
                raise ValueError("Cannot delete take without an artifact record.")
        selected = next((take for take in artifact.takes if take.take_id == take_id), None)
        if selected is None:
            raise ValueError(f"Unknown take_id '{take_id}' for session {session_id}.")

        self._delete_artifact_file(selected.audio_path)
        self._delete_artifact_file(selected.transcript_path)
        artifact.takes = [take for take in artifact.takes if take.take_id != take_id]
        if artifact.final_take_id == take_id:
            artifact.final_take_id = ""
            artifact.audio_path = ""
            artifact.transcript_path = ""
            artifact.provider = ""
        self.store.save_project(project)
        return project

    def clear_voice_reference_for_audio(self, audio_path: str) -> int:
        if not audio_path.strip():
            return 0
        target = Path(audio_path).expanduser().resolve()
        cleared = 0
        for session in self.store.list_sessions(include_deleted=True):
            try:
                artifact = self.store.load_artifact(session.session_id)
            except OSError:
                continue
            changed = False
            if _voice_reference_matches_path(artifact.voice_reference, target):
                artifact.voice_reference = {}
                cleared += 1
                changed = True
            for payload in artifact.script_artifacts.values():
                if _voice_reference_matches_path(payload.get("voice_reference"), target):
                    payload["voice_reference"] = {}
                    cleared += 1
                    changed = True
            if changed:
                self.store.save_artifact(artifact)
        return cleared

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

    def _settings_from_take(self, take: AudioTakeRecord) -> VoiceRenderSettings:
        return VoiceRenderSettings(
            voice_id=take.voice_id,
            voice_name=take.voice_name,
            style_id=take.style_id,
            style_name=take.style_name,
            speed=take.speed,
            language=take.language,
            audio_format=take.audio_format,
        )

    def _voice_reference_for(self, artifact: ArtifactRecord, provider: str) -> dict[str, object]:
        if provider != "local_mlx":
            return {}
        reference = artifact.voice_reference if isinstance(artifact.voice_reference, dict) else {}
        if not reference:
            return {}
        audio_path = str(reference.get("audio_path") or "")
        if not audio_path:
            return {}
        self._validate_reference_audio_path(audio_path)
        return dict(reference)

    def _validate_reference_audio_path(self, path: str) -> Path:
        if not path.strip():
            raise ValueError("Cannot lock voice preview without a preview audio path.")
        exports_dir = self.artifact_store.exports_dir.resolve()
        target = Path(path).expanduser().resolve()
        try:
            target.relative_to(exports_dir)
        except ValueError as exc:
            raise ValueError("Voice preview audio must be inside the app exports directory.") from exc
        if not target.exists():
            raise ValueError("Locked voice preview audio is missing. Re-render and lock a new preview.")
        if not target.is_file():
            raise ValueError("Locked voice preview path must point to an audio file.")
        return target

    def _delete_artifact_file(self, path: str) -> None:
        if not path.strip():
            return
        self.artifact_store.delete_export_file(Path(path))

    def _append_take_with_retention(
        self,
        takes: list[AudioTakeRecord],
        final_take_id: str,
        new_take: AudioTakeRecord,
    ) -> list[AudioTakeRecord]:
        retained = [take for take in takes if final_take_id and take.take_id == final_take_id]
        retained.append(new_take)
        return retained[-2:]


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


def _voice_reference_matches_path(reference: Any, target: Path) -> bool:
    if not isinstance(reference, dict):
        return False
    raw = str(reference.get("audio_path") or "")
    if not raw.strip():
        return False
    return Path(raw).expanduser().resolve() == target
