from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domain.project import SessionProject
from app.domain.session import SessionState
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
