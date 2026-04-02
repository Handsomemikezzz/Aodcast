from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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

    def render_audio(self, session_id: str, *, override_provider: str = "") -> AudioRenderResult:
        return self.render_audio_with_cancellation(session_id, override_provider=override_provider)

    def render_audio_with_cancellation(
        self,
        session_id: str,
        *,
        override_provider: str = "",
        should_cancel: Callable[[], bool] | None = None,
    ) -> AudioRenderResult:
        project = self.store.load_project(session_id)
        script = project.script
        artifact = project.artifact
        if script is None or artifact is None:
            raise ValueError("Cannot render audio without script and artifact records.")
        if project.session.state not in (
            SessionState.SCRIPT_GENERATED,
            SessionState.SCRIPT_EDITED,
            SessionState.FAILED,
        ):
            raise ValueError(
                f"Session must be in script_generated, script_edited, or failed state before audio rendering, got '{project.session.state.value}'."
            )

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

        request = TTSGenerationRequest(
            session_id=session_id,
            script_text=final_text,
            voice=tts_config.voice,
            audio_format=tts_config.audio_format,
        )
        try:
            raise_if_cancelled()
            response = provider.synthesize(request)
            raise_if_cancelled()
            transcript_path = self.artifact_store.write_transcript(session_id, final_text)
            audio_path = self.artifact_store.write_audio(
                session_id,
                response.audio_bytes,
                response.file_extension,
            )
        except TaskCancellationRequested:
            raise
        except Exception as exc:
            project.session.set_error(str(exc))
            self.store.save_project(project)
            raise

        artifact.transcript_path = str(transcript_path)
        artifact.audio_path = str(audio_path)
        artifact.provider = response.provider_name
        project.session.tts_provider = response.provider_name
        project.session.transition(SessionState.COMPLETED)
        self.store.save_project(project)

        return AudioRenderResult(
            project=project,
            provider=response.provider_name,
            model=response.model_name,
            audio_path=str(audio_path),
            transcript_path=str(transcript_path),
        )
