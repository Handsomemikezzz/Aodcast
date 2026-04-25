from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.domain.artifact import AudioTakeRecord
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
    ) -> AudioRenderResult:
        return self.render_audio_with_cancellation(
            session_id,
            script_id=script_id,
            override_provider=override_provider,
        )

    def render_audio_with_cancellation(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[AudioRenderProgress], None] | None = None,
    ) -> AudioRenderResult:
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

        settings = VoiceRenderSettings()
        tts_config = self.config_store.load_tts_config()
        if override_provider:
            tts_config.provider = override_provider
        provider = build_tts_provider(tts_config)
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

        request = TTSGenerationRequest(
            session_id=session_id,
            script_text=final_text,
            voice=tts_config.voice,
            audio_format=tts_config.audio_format,
            speed=settings.speed,
            style_id=settings.style_id,
            style_prompt="",
            language=settings.language,
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

    def render_voice_preview(self, settings: VoiceRenderSettings) -> VoicePreviewResult:
        normalized = self._normalize_settings(settings)
        tts_config = self.config_store.load_tts_config()
        tts_config.voice = self._provider_voice_for(normalized)
        tts_config.audio_format = normalized.audio_format or tts_config.audio_format
        provider = build_tts_provider(tts_config)
        style = resolve_style_preset(normalized.style_id)
        preview_text = normalized.preview_text.strip() or STANDARD_PREVIEW_TEXT
        request = TTSGenerationRequest(
            session_id="voice-preview",
            script_text=preview_text,
            voice=tts_config.voice,
            audio_format=tts_config.audio_format,
            speed=normalized.speed,
            style_id=normalized.style_id,
            style_prompt=style.prompt,
            language=normalized.language,
        )
        response = provider.synthesize(request)
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
        tts_config.voice = self._provider_voice_for(normalized)
        tts_config.audio_format = normalized.audio_format or tts_config.audio_format
        provider = build_tts_provider(tts_config)
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
        selected = next((take for take in artifact.takes if take.take_id == take_id), None)
        if selected is None:
            raise ValueError(f"Unknown take_id '{take_id}' for session {session_id}.")
        artifact.final_take_id = selected.take_id
        artifact.audio_path = selected.audio_path
        artifact.transcript_path = selected.transcript_path
        artifact.provider = selected.provider
        project.session.tts_provider = selected.provider
        self.store.save_project(project)
        return project

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

    def _provider_voice_for(self, settings: VoiceRenderSettings) -> str:
        return resolve_voice_preset(settings.voice_id).provider_voice

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
