from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.api.bridge_envelope import (
    build_request_state,
    error_envelope,
    progress_from_request_state,
    success_envelope,
)
from app.api.serializers import (
    serialize_generation_result,
    serialize_project,
    serialize_script_revisions,
    serialize_turn_result,
    serialize_voice_settings,
    serialize_voice_take_result,
    voice_settings_from_payload,
)
from app.config import AppConfig
from app.domain.project import SessionProject
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import TranscriptRecord
from app.domain.voice_studio import STANDARD_PREVIEW_TEXT, STYLE_PRESETS, VOICE_PRESETS
from app.models_catalog import (
    build_models_status,
    delete_voice_model,
    download_voice_model,
    migrate_model_storage,
    model_storage_status,
    reset_model_storage,
)
from app.orchestration.audio_rendering import (
    AudioRenderingService,
    AudioRenderProgress,
)
from app.orchestration.interview_service import InterviewOrchestrator
from app.orchestration.script_generation import ScriptGenerationService
from app.providers.llm.factory import validate_llm_provider
from app.providers.tts_api.factory import validate_tts_provider
from app.providers.tts_local_mlx.presets import DEFAULT_QWEN3_TTS_MODEL
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability
from app.runtime.long_task_state import LongTaskStateManager
from app.runtime.request_state_store import RequestStateStore
from app.runtime.task_cancellation import TaskCancellationRequested
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore

_BOOTSTRAP_TTL_SECONDS = 300.0
DOWNLOAD_PROGRESS_MARKER = "AODCAST_PROGRESS"
TASK_TERMINAL_PHASES = {"succeeded", "failed", "cancelled"}
_DEFAULT_ALLOWED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    }
)


class BridgeTaskCancelledError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        progress_percent: float,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.progress_percent = progress_percent



def _normalize_error_message(exc: Exception, *, fallback: str) -> str:
    message = str(exc).strip()
    return message or fallback



def create_project(topic: str, intent: str) -> SessionProject:
    session = SessionRecord(topic=topic, creation_intent=intent)
    transcript = TranscriptRecord(session_id=session.session_id)
    return SessionProject(
        session=session,
        transcript=transcript,
        script=None,
        artifact=None,
    )


def ensure_session_is_active(project: SessionProject) -> None:
    if project.session.is_deleted():
        raise ValueError("Session is deleted. Restore it before continuing.")


def ensure_script_is_active(project: SessionProject) -> None:
    if project.script is None:
        raise ValueError("Cannot continue without a script record.")
    if project.script.is_deleted():
        raise ValueError("Script is deleted. Restore it before continuing.")


@dataclass(slots=True)
class RuntimeContext:
    cwd: Path
    config: AppConfig
    store: ProjectStore
    config_store: ConfigStore
    artifact_store: ArtifactStore
    request_state_store: RequestStateStore
    orchestrator: InterviewOrchestrator
    script_generation: ScriptGenerationService
    audio_rendering: AudioRenderingService
    runtime_token: str
    bootstrap_nonce: str | None
    bootstrap_created_at: float
    runtime_started_at: float = field(default_factory=time.time)
    runtime_build_token: str = field(default_factory=lambda: uuid.uuid4().hex)
    allowed_origins: frozenset[str] = field(default_factory=frozenset)
    task_lock: threading.Lock = field(default_factory=threading.Lock)
    active_tasks: dict[str, threading.Thread] = field(default_factory=dict)
    bootstrap_nonce_used: bool = False

    def runtime_metadata(self) -> dict[str, object]:
        return {
            "pid": os.getpid(),
            "started_at_unix": self.runtime_started_at,
            "build_token": self.runtime_build_token,
        }

    def get_allowed_origin(self, origin: str | None) -> str | None:
        if not origin:
            return None
        if origin in self.allowed_origins:
            return origin
        return None

    def ensure_bootstrap_token(self, nonce: str) -> dict[str, object]:
        if not self.bootstrap_nonce:
            return success_envelope(
                {"token": self.runtime_token, "expires_in_seconds": int(_BOOTSTRAP_TTL_SECONDS)},
                operation="runtime_bootstrap",
            )
        if self.bootstrap_nonce_used:
            return error_envelope(
                operation="runtime_bootstrap",
                code="bridge_bootstrap_expired",
                message="Runtime bootstrap nonce was already used.",
            )
        if time.time() - self.bootstrap_created_at > _BOOTSTRAP_TTL_SECONDS:
            return error_envelope(
                operation="runtime_bootstrap",
                code="bridge_bootstrap_expired",
                message="Runtime bootstrap nonce expired.",
            )
        if nonce != self.bootstrap_nonce:
            return error_envelope(
                operation="runtime_bootstrap",
                code="bridge_bootstrap_invalid",
                message="Runtime bootstrap nonce is invalid.",
            )
        self.bootstrap_nonce_used = True
        return success_envelope(
            {"token": self.runtime_token, "expires_in_seconds": int(_BOOTSTRAP_TTL_SECONDS)},
            operation="runtime_bootstrap",
        )

    def start_render_audio(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
    ) -> dict[str, object]:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        if project.session.is_deleted():
            raise ValueError("Session is deleted. Restore it before continuing.")
        if project.script is None:
            raise ValueError("Cannot continue without a script record.")
        if project.script.is_deleted():
            raise ValueError("Script is deleted. Restore it before continuing.")

        task_id = f"render_audio:{session_id}"
        with self.task_lock:
            existing_thread = self.active_tasks.get(task_id)
            if existing_thread is not None and existing_thread.is_alive():
                existing_state = self.request_state_store.load(task_id)
                if isinstance(existing_state, dict):
                    return success_envelope(
                        {
                            "project": serialize_project(project),
                            "provider": str(project.session.tts_provider or ""),
                            "model": str(self.config_store.load_tts_config().model or ""),
                            "audio_path": project.artifact.audio_path if project.artifact else "",
                            "transcript_path": project.artifact.transcript_path if project.artifact else "",
                            "task_id": task_id,
                            "run_token": str(existing_state.get("run_token") or ""),
                        },
                        operation="render_audio",
                        message=str(existing_state.get("message") or "Rendering audio..."),
                        phase=str(existing_state.get("phase") or "running"),
                        progress_percent=progress_from_request_state(existing_state, default=5.0),
                        run_token=str(existing_state.get("run_token") or ""),
                    )

            run_token = uuid.uuid4().hex

            def tagged_build_request_state(**kwargs: Any) -> dict[str, object]:
                return build_request_state(run_token=run_token, **kwargs)

            progress = LongTaskStateManager(
                request_state_store=self.request_state_store,
                task_id=task_id,
                operation="render_audio",
                build_request_state=tagged_build_request_state,
                should_cancel=lambda: self.request_state_store.is_cancel_requested(task_id),
            )
            self.request_state_store.clear_cancel_request(task_id)
            progress.start(
                progress_percent=5.0,
                message=f"Rendering audio for session {session_id}...",
            )

            def worker() -> None:
                def on_progress(snapshot: AudioRenderProgress) -> None:
                    progress.set_progress(
                        snapshot.percent,
                        snapshot.message,
                        max_percent=99.0,
                    )

                try:
                    self.audio_rendering.render_audio_with_cancellation(
                        session_id,
                        script_id=script_id,
                        override_provider=override_provider,
                        should_cancel=progress.should_cancel,
                        on_progress=on_progress,
                    )
                except TaskCancellationRequested as exc:
                    self.raise_task_cancelled(
                        progress,
                        task_id=task_id,
                        operation="render_audio",
                        message=str(exc),
                        default_progress=10.0,
                    )
                except Exception as exc:  # pragma: no cover - exercised by integration tests
                    current_phase = progress.current_phase()
                    if self.request_state_store.is_cancel_requested(task_id) or current_phase == "cancelling":
                        self.raise_task_cancelled(
                            progress,
                            task_id=task_id,
                            operation="render_audio",
                            message=f"Audio rendering cancelled for session {session_id}.",
                            default_progress=10.0,
                            source_error=exc,
                        )
                    self.fail_task(
                        progress,
                        task_id=task_id,
                        message=_normalize_error_message(exc, fallback=f"Audio rendering failed for session {session_id}."),
                        fallback_message=f"Audio rendering failed for session {session_id}.",
                    )
                else:
                    self.complete_task_success(
                        progress,
                        task_id=task_id,
                        operation="render_audio",
                        finalizing_progress=99.0,
                        finalizing_message=f"Finalizing rendered artifacts for session {session_id}...",
                        success_message=f"Audio render finished for session {session_id}.",
                        fallback_failure_message=f"Unable to finalize audio render for session {session_id}.",
                        cancellation_message=f"Audio rendering cancelled for session {session_id}.",
                    )
                finally:
                    with self.task_lock:
                        self.active_tasks.pop(task_id, None)

            thread = threading.Thread(target=worker, name=task_id, daemon=True)
            self.active_tasks[task_id] = thread
            thread.start()

        started_state = self.request_state_store.load(task_id)
        return success_envelope(
            {
                "project": serialize_project(project),
                "provider": str(project.session.tts_provider or ""),
                "model": str(self.config_store.load_tts_config().model or ""),
                "audio_path": project.artifact.audio_path if project.artifact else "",
                "transcript_path": project.artifact.transcript_path if project.artifact else "",
                "task_id": task_id,
                "run_token": run_token,
            },
            operation="render_audio",
            message=str((started_state or {}).get("message") or "Rendering audio..."),
            phase=str((started_state or {}).get("phase") or "running"),
            progress_percent=progress_from_request_state(started_state, default=5.0),
            run_token=run_token,
        )

    def start_render_voice_preview(self, settings: VoiceRenderSettings) -> dict[str, object]:
        task_id = "render_voice_preview"
        with self.task_lock:
            existing_thread = self.active_tasks.get(task_id)
            if existing_thread is not None and existing_thread.is_alive():
                existing_state = self.request_state_store.load(task_id)
                if isinstance(existing_state, dict):
                    return success_envelope(
                        {"task_id": task_id},
                        operation="render_voice_preview",
                        message=str(existing_state.get("message") or "Rendering voice preview..."),
                        phase=str(existing_state.get("phase") or "running"),
                        progress_percent=progress_from_request_state(existing_state, default=5.0),
                    )

            progress = LongTaskStateManager(
                request_state_store=self.request_state_store,
                task_id=task_id,
                operation="render_voice_preview",
                build_request_state=build_request_state,
                should_cancel=lambda: self.request_state_store.is_cancel_requested(task_id),
            )
            self.request_state_store.clear_cancel_request(task_id)
            progress.start(progress_percent=5.0, message="Rendering voice preview...")

            def worker() -> None:
                heartbeat_stop, heartbeat_thread = progress.start_heartbeat(
                    start_percent=5.0,
                    max_percent=85.0,
                    step_percent=2.0,
                    interval_seconds=1.0,
                    message="Rendering voice preview...",
                )

                def on_progress(snapshot: AudioRenderProgress) -> None:
                    progress.set_progress(snapshot.percent, snapshot.message, max_percent=98.0)

                try:
                    result = self.audio_rendering.render_voice_preview_with_cancellation(
                        settings,
                        should_cancel=progress.should_cancel,
                        on_progress=on_progress,
                    )
                except TaskCancellationRequested as exc:
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    self.raise_task_cancelled(
                        progress,
                        task_id=task_id,
                        operation="render_voice_preview",
                        message=str(exc),
                        default_progress=10.0,
                    )
                except Exception as exc:  # pragma: no cover - exercised by integration tests
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    if self.request_state_store.is_cancel_requested(task_id) or progress.current_phase() == "cancelling":
                        self.raise_task_cancelled(
                            progress,
                            task_id=task_id,
                            operation="render_voice_preview",
                            message="Voice preview rendering cancelled.",
                            default_progress=10.0,
                            source_error=exc,
                        )
                    self.fail_task(
                        progress,
                        task_id=task_id,
                        message=_normalize_error_message(exc, fallback="Voice preview rendering failed."),
                        fallback_message="Voice preview rendering failed.",
                    )
                else:
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    progress.save_finalizing(progress_percent=99.0, message="Finalizing voice preview...")
                    self.request_state_store.save_if_current_phase(
                        task_id,
                        {
                            **build_request_state(
                                operation="render_voice_preview",
                                phase="succeeded",
                                progress_percent=100.0,
                                message="Voice preview render finished.",
                            ),
                            "audio_path": result.audio_path,
                            "provider": result.provider,
                            "model": result.model,
                            "settings": serialize_voice_settings(result.settings),
                        },
                        allowed_phases={"running"},
                    )
                    self.request_state_store.clear_cancel_request(task_id)
                finally:
                    with self.task_lock:
                        self.active_tasks.pop(task_id, None)

            thread = threading.Thread(target=worker, name=task_id, daemon=True)
            self.active_tasks[task_id] = thread
            thread.start()

        started_state = self.request_state_store.load(task_id)
        return success_envelope(
            {"task_id": task_id},
            operation="render_voice_preview",
            message=str((started_state or {}).get("message") or "Rendering voice preview..."),
            phase=str((started_state or {}).get("phase") or "running"),
            progress_percent=progress_from_request_state(started_state, default=5.0),
        )

    def start_render_voice_take(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        settings: VoiceRenderSettings,
    ) -> dict[str, object]:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        if project.session.is_deleted():
            raise ValueError("Session is deleted. Restore it before continuing.")
        if project.script is None:
            raise ValueError("Cannot continue without a script record.")
        if project.script.is_deleted():
            raise ValueError("Script is deleted. Restore it before continuing.")

        task_id = f"render_voice_take:{session_id}"
        with self.task_lock:
            existing_thread = self.active_tasks.get(task_id)
            if existing_thread is not None and existing_thread.is_alive():
                existing_state = self.request_state_store.load(task_id)
                if isinstance(existing_state, dict):
                    return success_envelope(
                        {
                            "project": serialize_project(project),
                            "provider": str(project.session.tts_provider or ""),
                            "model": str(self.config_store.load_tts_config().model or ""),
                            "audio_path": project.artifact.audio_path if project.artifact else "",
                            "transcript_path": project.artifact.transcript_path if project.artifact else "",
                            "task_id": task_id,
                            "run_token": str(existing_state.get("run_token") or ""),
                        },
                        operation="render_voice_take",
                        message=str(existing_state.get("message") or "Rendering voice take..."),
                        phase=str(existing_state.get("phase") or "running"),
                        progress_percent=progress_from_request_state(existing_state, default=5.0),
                        run_token=str(existing_state.get("run_token") or ""),
                    )

            run_token = uuid.uuid4().hex

            def tagged_build_request_state(**kwargs: Any) -> dict[str, object]:
                return build_request_state(run_token=run_token, **kwargs)

            progress = LongTaskStateManager(
                request_state_store=self.request_state_store,
                task_id=task_id,
                operation="render_voice_take",
                build_request_state=tagged_build_request_state,
                should_cancel=lambda: self.request_state_store.is_cancel_requested(task_id),
            )
            self.request_state_store.clear_cancel_request(task_id)
            progress.start(progress_percent=5.0, message=f"Rendering voice take for session {session_id}...")

            def worker() -> None:
                def on_progress(snapshot: AudioRenderProgress) -> None:
                    progress.set_progress(snapshot.percent, snapshot.message, max_percent=99.0)

                try:
                    self.audio_rendering.render_voice_take_with_cancellation(
                        session_id,
                        script_id=script_id,
                        override_provider=override_provider,
                        settings=settings,
                        should_cancel=progress.should_cancel,
                        on_progress=on_progress,
                    )
                except TaskCancellationRequested as exc:
                    self.raise_task_cancelled(
                        progress,
                        task_id=task_id,
                        operation="render_voice_take",
                        message=str(exc),
                        default_progress=10.0,
                    )
                except Exception as exc:  # pragma: no cover - exercised by integration tests
                    current_phase = progress.current_phase()
                    if self.request_state_store.is_cancel_requested(task_id) or current_phase == "cancelling":
                        self.raise_task_cancelled(
                            progress,
                            task_id=task_id,
                            operation="render_voice_take",
                            message=f"Voice take rendering cancelled for session {session_id}.",
                            default_progress=10.0,
                            source_error=exc,
                        )
                    self.fail_task(
                        progress,
                        task_id=task_id,
                        message=_normalize_error_message(exc, fallback=f"Voice take rendering failed for session {session_id}."),
                        fallback_message=f"Voice take rendering failed for session {session_id}.",
                    )
                else:
                    self.complete_task_success(
                        progress,
                        task_id=task_id,
                        operation="render_voice_take",
                        finalizing_progress=99.0,
                        finalizing_message=f"Finalizing voice take for session {session_id}...",
                        success_message=f"Voice take render finished for session {session_id}.",
                        fallback_failure_message=f"Unable to finalize voice take for session {session_id}.",
                        cancellation_message=f"Voice take rendering cancelled for session {session_id}.",
                    )
                finally:
                    with self.task_lock:
                        self.active_tasks.pop(task_id, None)

            thread = threading.Thread(target=worker, name=task_id, daemon=True)
            self.active_tasks[task_id] = thread
            thread.start()

        started_state = self.request_state_store.load(task_id)
        return success_envelope(
            {
                "project": serialize_project(project),
                "provider": str(project.session.tts_provider or ""),
                "model": str(self.config_store.load_tts_config().model or ""),
                "audio_path": project.artifact.audio_path if project.artifact else "",
                "transcript_path": project.artifact.transcript_path if project.artifact else "",
                "task_id": task_id,
                "run_token": run_token,
            },
            operation="render_voice_take",
            message=str((started_state or {}).get("message") or "Rendering voice take..."),
            phase=str((started_state or {}).get("phase") or "running"),
            progress_percent=progress_from_request_state(started_state, default=5.0),
            run_token=run_token,
        )

    def start_download_model(self, model_name: str) -> dict[str, object]:
        task_id = f"download_model:{model_name}"
        existing_state = self.request_state_store.load(task_id)
        with self.task_lock:
            existing_thread = self.active_tasks.get(task_id)
            if existing_thread is not None and existing_thread.is_alive() and isinstance(existing_state, dict):
                return success_envelope(
                    {"message": f"Downloading model {model_name}...", "task_id": task_id},
                    operation="download_model",
                    message=str(existing_state.get("message") or f"Downloading model {model_name}..."),
                    phase=str(existing_state.get("phase") or "running"),
                    progress_percent=progress_from_request_state(existing_state, default=5.0),
                )

            progress = LongTaskStateManager(
                request_state_store=self.request_state_store,
                task_id=task_id,
                operation="download_model",
                build_request_state=build_request_state,
                should_cancel=lambda: self.request_state_store.is_cancel_requested(task_id),
            )
            self.request_state_store.clear_cancel_request(task_id)
            progress.start(progress_percent=5.0, message=f"Downloading model {model_name}...")

            def worker() -> None:
                heartbeat_stop, heartbeat_thread = progress.start_heartbeat(
                    start_percent=5.0,
                    max_percent=95.0,
                    step_percent=1.5,
                    interval_seconds=1.2,
                    message=f"Downloading model {model_name}...",
                )

                progress_pattern = __import__("re").compile(rf"{DOWNLOAD_PROGRESS_MARKER}\s+(\d{{1,3}})")

                def on_download_output_line(line: str) -> None:
                    match = progress_pattern.search(line)
                    if match is None:
                        return
                    parsed = int(match.group(1))
                    progress.update_running(
                        float(max(5, min(95, parsed))),
                        f"Downloading model {model_name}... {parsed}%",
                        max_percent=95.0,
                    )

                try:
                    download_voice_model(
                        self.cwd,
                        model_name,
                        config_store=self.config_store,
                        on_output_line=on_download_output_line,
                        should_cancel=progress.should_cancel,
                    )
                except TaskCancellationRequested as exc:
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    self.raise_task_cancelled(
                        progress,
                        task_id=task_id,
                        operation="download_model",
                        message=str(exc),
                        default_progress=5.0,
                    )
                except Exception as exc:  # pragma: no cover - exercised by integration tests
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    if self.request_state_store.is_cancel_requested(task_id) or progress.current_phase() == "cancelling":
                        self.raise_task_cancelled(
                            progress,
                            task_id=task_id,
                            operation="download_model",
                            message=f"Model {model_name} download cancelled.",
                            default_progress=5.0,
                            source_error=exc,
                        )
                    self.fail_task(
                        progress,
                        task_id=task_id,
                        message=str(exc),
                        fallback_message=f"Model {model_name} download failed.",
                    )
                else:
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    self.complete_task_success(
                        progress,
                        task_id=task_id,
                        operation="download_model",
                        finalizing_progress=98.0,
                        finalizing_message=f"Finalizing model {model_name}...",
                        success_message=f"Model {model_name} is ready.",
                        fallback_failure_message=f"Unable to finalize download state for {model_name}.",
                        cancellation_message=f"Model {model_name} download cancelled.",
                    )
                finally:
                    with self.task_lock:
                        self.active_tasks.pop(task_id, None)

            thread = threading.Thread(target=worker, name=task_id, daemon=True)
            self.active_tasks[task_id] = thread
            thread.start()

        started_state = self.request_state_store.load(task_id)
        return success_envelope(
            {"message": f"Downloading model {model_name}...", "task_id": task_id},
            operation="download_model",
            message=str((started_state or {}).get("message") or f"Downloading model {model_name}..."),
            phase=str((started_state or {}).get("phase") or "running"),
            progress_percent=progress_from_request_state(started_state, default=5.0),
        )

    def start_migrate_model_storage(self, destination: str) -> dict[str, object]:
        if not destination.strip():
            raise ValueError("Field 'destination' is required.")
        destination_path = Path(destination).expanduser()
        task_id = "migrate_model_storage"
        existing_state = self.request_state_store.load(task_id)
        with self.task_lock:
            existing_thread = self.active_tasks.get(task_id)
            if existing_thread is not None and existing_thread.is_alive() and isinstance(existing_state, dict):
                return success_envelope(
                    {"message": "Migrating model storage...", "task_id": task_id},
                    operation="migrate_model_storage",
                    message=str(existing_state.get("message") or "Migrating model storage..."),
                    phase=str(existing_state.get("phase") or "running"),
                    progress_percent=progress_from_request_state(existing_state, default=5.0),
                )

            progress = LongTaskStateManager(
                request_state_store=self.request_state_store,
                task_id=task_id,
                operation="migrate_model_storage",
                build_request_state=build_request_state,
                should_cancel=lambda: self.request_state_store.is_cancel_requested(task_id),
            )
            self.request_state_store.clear_cancel_request(task_id)
            progress.start(progress_percent=5.0, message="Preparing model storage migration...")

            def worker() -> None:
                def on_progress(current: int, total: int, filename: str) -> None:
                    percent = 5.0 if total <= 0 else 5.0 + min(90.0, (current / total) * 90.0)
                    progress.update_running(
                        percent,
                        f"Migrating model storage... {filename}",
                        max_percent=95.0,
                    )

                try:
                    migrate_model_storage(
                        self.config_store,
                        self.cwd,
                        destination_path,
                        on_progress=on_progress,
                        should_cancel=progress.should_cancel,
                    )
                except TaskCancellationRequested as exc:
                    self.raise_task_cancelled(
                        progress,
                        task_id=task_id,
                        operation="migrate_model_storage",
                        message=str(exc),
                        default_progress=5.0,
                    )
                except Exception as exc:  # pragma: no cover - exercised by integration tests
                    if self.request_state_store.is_cancel_requested(task_id) or progress.current_phase() == "cancelling":
                        self.raise_task_cancelled(
                            progress,
                            task_id=task_id,
                            operation="migrate_model_storage",
                            message="Model storage migration cancelled.",
                            default_progress=5.0,
                            source_error=exc,
                        )
                    self.fail_task(
                        progress,
                        task_id=task_id,
                        message=_normalize_error_message(exc, fallback="Model storage migration failed."),
                        fallback_message="Model storage migration failed.",
                    )
                else:
                    self.complete_task_success(
                        progress,
                        task_id=task_id,
                        operation="migrate_model_storage",
                        finalizing_progress=98.0,
                        finalizing_message="Finalizing model storage migration...",
                        success_message=f"Model storage migrated to {destination_path.expanduser().resolve()}.",
                        fallback_failure_message="Unable to finalize model storage migration.",
                        cancellation_message="Model storage migration cancelled.",
                    )
                finally:
                    with self.task_lock:
                        self.active_tasks.pop(task_id, None)

            thread = threading.Thread(target=worker, name=task_id, daemon=True)
            self.active_tasks[task_id] = thread
            thread.start()

        started_state = self.request_state_store.load(task_id)
        return success_envelope(
            {"message": "Migrating model storage...", "task_id": task_id},
            operation="migrate_model_storage",
            message=str((started_state or {}).get("message") or "Migrating model storage..."),
            phase=str((started_state or {}).get("phase") or "running"),
            progress_percent=progress_from_request_state(started_state, default=5.0),
        )

    def raise_task_cancelled(
        self,
        progress: LongTaskStateManager,
        *,
        task_id: str,
        operation: str,
        message: str,
        default_progress: float,
        source_error: Exception | None = None,
    ) -> None:
        cancel_progress = progress.current_progress(default=default_progress)
        progress.save_cancelled(progress_percent=cancel_progress, message=message)
        self.request_state_store.clear_cancel_request(task_id)
        error = BridgeTaskCancelledError(
            message,
            operation=operation,
            progress_percent=cancel_progress,
        )
        if source_error is not None:
            raise error from source_error
        raise error

    def fail_task(
        self,
        progress: LongTaskStateManager,
        *,
        task_id: str,
        message: str,
        fallback_message: str,
    ) -> None:
        normalized_message = message.strip() or fallback_message
        progress.save_failed(message=normalized_message)
        self.request_state_store.clear_cancel_request(task_id)

    def complete_task_success(
        self,
        progress: LongTaskStateManager,
        *,
        task_id: str,
        operation: str,
        finalizing_progress: float,
        finalizing_message: str,
        success_message: str,
        fallback_failure_message: str,
        cancellation_message: str,
    ) -> None:
        progress.save_finalizing(
            progress_percent=finalizing_progress,
            message=finalizing_message,
        )
        saved_succeeded = progress.save_succeeded(message=success_message)
        if not saved_succeeded:
            if self.request_state_store.is_cancel_requested(task_id) or progress.current_phase() == "cancelling":
                self.raise_task_cancelled(
                    progress,
                    task_id=task_id,
                    operation=operation,
                    message=cancellation_message,
                    default_progress=finalizing_progress,
                )
            self.fail_task(
                progress,
                task_id=task_id,
                message=fallback_failure_message,
                fallback_message=fallback_failure_message,
            )
            return
        self.request_state_store.clear_cancel_request(task_id)

    def list_projects_payload(self, *, include_deleted: bool = False, search_query: str = "") -> dict[str, object]:
        projects = sorted(
            self.store.list_projects(include_deleted=include_deleted, search_query=search_query),
            key=lambda project: project.session.updated_at,
            reverse=True,
        )
        return success_envelope({"projects": [serialize_project(project) for project in projects]}, operation="list_projects")

    def create_session_payload(self, *, topic: str, creation_intent: str) -> dict[str, object]:
        project = create_project(topic, creation_intent)
        self.store.save_project(project)
        return success_envelope({"project": serialize_project(project)}, operation="create_session")


def _query_flag(query: dict[str, list[str]], key: str) -> bool:
    values = query.get(key)
    if not values:
        return False
    return values[-1].strip().lower() in {"1", "true", "yes", "on"}


class RuntimeRequestHandler(BaseHTTPRequestHandler):
    server: "RuntimeHttpServer"

    def do_OPTIONS(self) -> None:  # noqa: N802
        origin = self._check_origin(preflight=True)
        if origin is False:
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers(origin)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    @property
    def context(self) -> RuntimeContext:
        return self.server.runtime_context

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/healthz":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "status": "ready",
                    "service": "aodcast-python-core-http",
                    "runtime": self.context.runtime_metadata(),
                },
            )
            return

        origin = self._check_origin(preflight=False)
        if origin is False:
            return
        if not self._check_auth(path, origin):
            return

        try:
            body = self._read_json_body() if self.command in {"POST", "PATCH", "PUT"} else {}
            query = parse_qs(parsed.query, keep_blank_values=True)
            self._route(path, query, body, origin)
        except ValueError as exc:
            self._send_bridge_envelope(
                error_envelope(
                    operation=self._infer_operation(path),
                    code="python_core_error",
                    message=_normalize_error_message(exc, fallback="HTTP runtime request failed."),
                ),
                origin=origin,
            )
        except Exception as exc:  # pragma: no cover - exercised by integration tests
            self._send_bridge_envelope(
                error_envelope(
                    operation=self._infer_operation(path),
                    code="python_core_error",
                    message=_normalize_error_message(exc, fallback="HTTP runtime request failed."),
                    details={"exception_type": exc.__class__.__name__},
                ),
                origin=origin,
            )

    def _load_script_project(
        self,
        session_id: str,
        *,
        script_id: str = "",
        require_active_script: bool = True,
    ) -> SessionProject:
        project = self.context.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.context.store.load_project(session_id)
        ensure_session_is_active(project)
        if require_active_script:
            ensure_script_is_active(project)
        return project

    def _save_script_final(
        self,
        session_id: str,
        *,
        final_text: str,
        origin: str | None,
        script_id: str = "",
    ) -> None:
        if not final_text.strip():
            raise ValueError("Field 'final_text' is required.")
        project = self._load_script_project(session_id, script_id=script_id)
        project.script.save_final(final_text)
        project.session.transition(SessionState.SCRIPT_EDITED)
        self.context.store.save_project(project)
        self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="save_script"), origin=origin)

    def _delete_script(
        self,
        session_id: str,
        *,
        origin: str | None,
        script_id: str = "",
    ) -> None:
        project = self._load_script_project(session_id, script_id=script_id)
        if project.script.is_deleted():
            raise ValueError("Script is already deleted.")
        project.script.soft_delete()
        self.context.store.save_project(project)
        self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="delete_script"), origin=origin)

    def _restore_script(
        self,
        session_id: str,
        *,
        origin: str | None,
        script_id: str = "",
    ) -> None:
        project = self._load_script_project(session_id, script_id=script_id, require_active_script=False)
        if project.script is None:
            raise ValueError("Cannot restore script because no script record exists.")
        if not project.script.is_deleted():
            raise ValueError("Script is not deleted.")
        project.script.restore()
        self.context.store.save_project(project)
        self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="restore_script"), origin=origin)

    def _list_script_revisions(
        self,
        session_id: str,
        *,
        origin: str | None,
        script_id: str = "",
    ) -> None:
        project = self._load_script_project(session_id, script_id=script_id, require_active_script=False)
        if project.script is None:
            raise ValueError("Cannot list revisions because no script record exists.")
        payload = {
            "session_id": session_id,
            "revisions": serialize_script_revisions(project),
        }
        if script_id.strip():
            payload["script_id"] = script_id
        self._send_bridge_envelope(
            success_envelope(payload, operation="list_script_revisions"),
            origin=origin,
        )

    def _rollback_script_revision(
        self,
        session_id: str,
        *,
        revision_id: str,
        origin: str | None,
        script_id: str = "",
    ) -> None:
        project = self._load_script_project(session_id, script_id=script_id)
        project.script.rollback_to_revision(revision_id)
        project.session.transition(SessionState.SCRIPT_EDITED)
        self.context.store.save_project(project)
        self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="rollback_script_revision"), origin=origin)

    def _route(
        self,
        path: str,
        query: dict[str, list[str]],
        body: dict[str, Any],
        origin: str | None,
    ) -> None:
        session_script_revision_prefix = "/api/v1/sessions/"
        if self.command == "GET" and path == "/api/v1/projects":
            search = (query.get("search") or [""])[-1].strip()
            self._send_bridge_envelope(
                self.context.list_projects_payload(
                    include_deleted=_query_flag(query, "include_deleted"),
                    search_query=search,
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/api/v1/sessions":
            topic = str(body.get("topic") or "").strip()
            creation_intent = str(body.get("creation_intent") or "").strip()
            if not topic:
                raise ValueError("Field 'topic' is required.")
            if not creation_intent:
                raise ValueError("Field 'creation_intent' is required.")
            self._send_bridge_envelope(
                self.context.create_session_payload(topic=topic, creation_intent=creation_intent),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/api/v1/runtime/bootstrap":
            nonce = str(body.get("nonce") or "")
            self._send_bridge_envelope(self.context.ensure_bootstrap_token(nonce), origin=origin)
            return
        if self.command == "GET" and path == "/api/v1/runtime/tts/local-capability":
            capability = detect_local_mlx_capability(self.context.config_store.load_tts_config()).to_dict()
            self._send_bridge_envelope(success_envelope({"tts_capability": capability}, operation="show_local_tts_capability"), origin=origin)
            return
        if self.command == "GET" and path == "/api/v1/voice-studio/presets":
            self._send_bridge_envelope(
                success_envelope(
                    {
                        "voices": [voice.to_dict() for voice in VOICE_PRESETS],
                        "styles": [style.to_dict() for style in STYLE_PRESETS],
                        "standard_preview_text": STANDARD_PREVIEW_TEXT,
                    },
                    operation="list_voice_presets",
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/api/v1/voice-studio/preview":
            self._send_bridge_envelope(
                self.context.start_render_voice_preview(voice_settings_from_payload(body)),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/artifacts/audio":
            self._serve_artifact_audio(query, origin=origin)
            return
        if self.command == "GET" and path == "/api/v1/config/llm":
            self._send_bridge_envelope(
                success_envelope({"llm_config": self.context.config_store.load_llm_config().to_dict()}, operation="show_llm_config"),
                origin=origin,
            )
            return
        if self.command == "PUT" and path == "/api/v1/config/llm":
            provider = str(body.get("provider") or "").strip()
            if not provider:
                raise ValueError("Field 'provider' is required.")
            validate_llm_provider(provider)
            llm_config = self.context.config_store.load_llm_config()
            llm_config.provider = provider
            if "model" in body:
                llm_config.model = str(body.get("model") or "")
            if "base_url" in body:
                llm_config.base_url = str(body.get("base_url") or "")
            if "api_key" in body:
                llm_config.api_key = str(body.get("api_key") or "")
            path_obj = self.context.config_store.save_llm_config(llm_config)
            self._send_bridge_envelope(
                success_envelope(
                    {"path": str(path_obj), "llm_config": llm_config.to_dict()},
                    operation="configure_llm_provider",
                ),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/config/tts":
            self._send_bridge_envelope(
                success_envelope({"tts_config": self.context.config_store.load_tts_config().to_dict()}, operation="show_tts_config"),
                origin=origin,
            )
            return
        if self.command == "PUT" and path == "/api/v1/config/tts":
            provider = str(body.get("provider") or "").strip()
            if not provider:
                raise ValueError("Field 'provider' is required.")
            validate_tts_provider(provider)
            tts_config = self.context.config_store.load_tts_config()
            tts_config.provider = provider
            if "model" in body:
                model_value = str(body.get("model") or "")
                if provider == "local_mlx" and model_value == "":
                    tts_config.model = DEFAULT_QWEN3_TTS_MODEL
                else:
                    tts_config.model = model_value
            elif provider == "local_mlx" and tts_config.model in {"", "mock-voice"}:
                tts_config.model = DEFAULT_QWEN3_TTS_MODEL
            if "base_url" in body:
                tts_config.base_url = str(body.get("base_url") or "")
            if "api_key" in body:
                tts_config.api_key = str(body.get("api_key") or "")
            if "voice" in body:
                tts_config.voice = str(body.get("voice") or "")
            if "audio_format" in body:
                tts_config.audio_format = str(body.get("audio_format") or "")
            if "local_runtime" in body:
                tts_config.local_runtime = str(body.get("local_runtime") or "")
            if body.get("clear_local_model_path"):
                tts_config.local_model_path = ""
            elif "local_model_path" in body:
                tts_config.local_model_path = str(body.get("local_model_path") or "")
            if "local_ref_audio_path" in body:
                tts_config.local_ref_audio_path = str(body.get("local_ref_audio_path") or "")
            path_obj = self.context.config_store.save_tts_config(tts_config)
            self._send_bridge_envelope(
                success_envelope(
                    {"path": str(path_obj), "tts_config": tts_config.to_dict()},
                    operation="configure_tts_provider",
                ),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/models":
            self._send_bridge_envelope(
                success_envelope({"models": build_models_status(self.context.config_store, self.context.cwd)}, operation="list_models_status"),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/models/storage":
            self._send_bridge_envelope(
                success_envelope(
                    {"model_storage": model_storage_status(self.context.config_store, self.context.cwd)},
                    operation="show_model_storage",
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/api/v1/models/storage:migrate":
            destination = str(body.get("destination") or "").strip()
            self._send_bridge_envelope(self.context.start_migrate_model_storage(destination), origin=origin)
            return
        if self.command == "POST" and path == "/api/v1/models/storage:reset":
            self._send_bridge_envelope(
                success_envelope(
                    {"model_storage": reset_model_storage(self.context.config_store, self.context.cwd)},
                    operation="reset_model_storage",
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and path.startswith("/api/v1/models/") and path.endswith(":download"):
            model_name = path.removeprefix("/api/v1/models/").removesuffix(":download")
            self._send_bridge_envelope(self.context.start_download_model(model_name), origin=origin)
            return
        if self.command == "POST" and path.startswith("/api/v1/models/") and path.endswith(":delete"):
            model_name = path.removeprefix("/api/v1/models/").removesuffix(":delete")
            self._send_bridge_envelope(
                success_envelope(delete_voice_model(self.context.cwd, model_name, self.context.config_store), operation="delete_model"),
                origin=origin,
            )
            return
        if self.command == "GET" and path.startswith("/api/v1/tasks/"):
            task_id = path.removeprefix("/api/v1/tasks/")
            self._send_bridge_envelope(
                success_envelope(
                    {"task_id": task_id, "task_state": self.context.request_state_store.load(task_id)},
                    operation="show_task_state",
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and path.startswith("/api/v1/tasks/") and path.endswith(":cancel"):
            task_id = path.removeprefix("/api/v1/tasks/").removesuffix(":cancel")
            task_state = self.context.request_state_store.load(task_id)
            if task_state is None:
                self.context.request_state_store.clear_cancel_request(task_id)
                self._send_bridge_envelope(
                    success_envelope(
                        {"task_id": task_id, "task_state": None},
                        operation="cancel_task",
                        message="task_not_found",
                    ),
                    origin=origin,
                )
                return
            phase = str(task_state.get("phase", "")).strip().lower()
            if phase in TASK_TERMINAL_PHASES:
                self.context.request_state_store.clear_cancel_request(task_id)
                self._send_bridge_envelope(
                    success_envelope(
                        {"task_id": task_id, "task_state": task_state},
                        operation="cancel_task",
                        message="task_already_terminal",
                    ),
                    origin=origin,
                )
                return
            operation = str(task_state.get("operation") or "task")
            progress_percent = progress_from_request_state(task_state)
            run_token = str(task_state.get("run_token") or "").strip() or None
            self.context.request_state_store.request_cancel(task_id)
            cancelling_state = build_request_state(
                operation=operation,
                phase="cancelling",
                progress_percent=progress_percent,
                message=f"Cancellation requested for {task_id}.",
                run_token=run_token,
            )
            self.context.request_state_store.save(task_id, cancelling_state)
            self._send_bridge_envelope(
                success_envelope(
                    {"task_id": task_id, "task_state": cancelling_state},
                    operation="cancel_task",
                    message="cancellation_requested",
                    run_token=run_token,
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/admin/shutdown":
            self._send_json(HTTPStatus.OK, {"ok": True, "status": "shutting_down"}, origin=origin)
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        if not path.startswith(session_script_revision_prefix):
            raise ValueError(f"Unknown route: {path}")
        remainder = path[len(session_script_revision_prefix) :]
        session_id, _, suffix = remainder.partition("/")
        suffix = f"/{suffix}" if suffix else ""
        # Support colon-style session actions like /api/v1/sessions/{id}:delete.
        if not suffix and ":" in session_id:
            raw_session_id, raw_action = session_id.rsplit(":", 1)
            if raw_session_id and raw_action:
                session_id = raw_session_id
                suffix = f":{raw_action}"

        if self.command == "GET" and not suffix:
            project = self.context.store.load_project(session_id)
            if project.session.is_deleted() and not _query_flag(query, "include_deleted"):
                raise ValueError("Session is deleted. Pass include_deleted to inspect it.")
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="show_session"), origin=origin)
            return
        if self.command == "PATCH" and not suffix:
            topic = str(body.get("topic") or "").strip()
            if not topic:
                raise ValueError("Field 'topic' is required.")
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            project.session.rename_topic(topic)
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="rename_session"), origin=origin)
            return
        if self.command == "POST" and suffix == ":delete":
            project = self.context.store.load_project(session_id)
            if project.session.is_deleted():
                raise ValueError("Session is already deleted.")
            project.session.soft_delete()
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="delete_session"), origin=origin)
            return
        if self.command == "POST" and suffix == ":restore":
            project = self.context.store.load_project(session_id)
            if not project.session.is_deleted():
                raise ValueError("Session is not deleted.")
            project.session.restore()
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="restore_session"), origin=origin)
            return
        if self.command == "POST" and suffix == "/interview:start":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            result = self.context.orchestrator.start_interview(session_id)
            self._send_bridge_envelope(success_envelope(serialize_turn_result(result), operation="start_interview"), origin=origin)
            return
        if self.command == "POST" and suffix == "/interview:reply":
            message = str(body.get("message") or "").strip()
            if not message:
                raise ValueError("Field 'message' is required.")
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            result = self.context.orchestrator.submit_user_response(
                session_id,
                message,
                user_requested_finish=bool(body.get("user_requested_finish")),
            )
            self._send_bridge_envelope(success_envelope(serialize_turn_result(result), operation="submit_reply"), origin=origin)
            return
        if self.command == "POST" and suffix == "/interview:reply-stream":
            self._handle_stream_reply(session_id, body, origin)
            return
        if self.command == "POST" and suffix == "/interview:finish":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            result = self.context.orchestrator.request_finish(session_id)
            self._send_bridge_envelope(success_envelope(serialize_turn_result(result), operation="request_finish"), origin=origin)
            return
        if self.command == "GET" and suffix == "/scripts":
            ensure_session_is_active(self.context.store.load_project(session_id))
            scripts = self.context.store.list_scripts(session_id)
            self._send_bridge_envelope(
                success_envelope({"session_id": session_id, "scripts": [s.to_dict() for s in scripts]}, operation="list_scripts"),
                origin=origin,
            )
            return
        if self.command == "GET" and suffix == "/scripts/latest":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="show_latest_script"), origin=origin)
            return
        if self.command == "GET" and suffix.startswith("/scripts/"):
            rest = suffix.removeprefix("/scripts/").strip("/")
            if rest and "/" not in rest:
                project = self.context.store.load_project_for_script(session_id, rest)
                ensure_session_is_active(project)
                self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="show_script"), origin=origin)
                return
        if self.command == "POST" and suffix.startswith("/scripts/") and suffix.endswith("/voice-takes:render"):
            script_id = suffix.removeprefix("/scripts/").removesuffix("/voice-takes:render").strip("/")
            provider = str(body.get("provider_override") or "")
            self._send_bridge_envelope(
                self.context.start_render_voice_take(
                    session_id,
                    script_id=script_id,
                    override_provider=provider,
                    settings=voice_settings_from_payload(body),
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and suffix.startswith("/voice-takes/") and suffix.endswith(":final"):
            take_id = suffix.removeprefix("/voice-takes/").removesuffix(":final").strip("/")
            project = self.context.audio_rendering.set_final_voice_take(session_id, take_id)
            self._send_bridge_envelope(
                success_envelope({"project": serialize_project(project)}, operation="set_final_voice_take"),
                origin=origin,
            )
            return
        if self.command == "PUT" and suffix.startswith("/scripts/") and suffix.endswith("/final"):
            rest = suffix.removeprefix("/scripts/").removesuffix("/final").strip("/")
            self._save_script_final(session_id, final_text=str(body.get("final_text") or ""), origin=origin, script_id=rest)
            return
        if self.command == "GET" and suffix.startswith("/scripts/") and "/revisions" in suffix:
            # /scripts/{id}/revisions
            rest = suffix.removeprefix("/scripts/").strip("/")
            if not rest.endswith("/revisions"):
                raise ValueError(f"Unknown route: {path}")
            script_id = rest[: -len("/revisions")].strip("/")
            self._list_script_revisions(session_id, origin=origin, script_id=script_id)
            return
        if self.command == "POST" and suffix.startswith("/scripts/") and "/revisions/" in suffix and suffix.endswith(":rollback"):
            rest = suffix.removeprefix("/scripts/").strip("/")
            # {script_id}/revisions/{rev}:rollback
            mid, _, revpart = rest.partition("/revisions/")
            revision_id = revpart.removesuffix(":rollback")
            self._rollback_script_revision(session_id, revision_id=revision_id, origin=origin, script_id=mid)
            return
        if self.command == "POST" and suffix.startswith("/scripts/") and suffix.endswith(":delete"):
            script_id = suffix.removeprefix("/scripts/").removesuffix(":delete").strip("/")
            self._delete_script(session_id, origin=origin, script_id=script_id)
            return
        if self.command == "POST" and suffix.startswith("/scripts/") and suffix.endswith(":restore"):
            script_id = suffix.removeprefix("/scripts/").removesuffix(":restore").strip("/")
            self._restore_script(session_id, origin=origin, script_id=script_id)
            return
        if self.command == "POST" and suffix == "/script:generate":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            result = self.context.script_generation.generate_draft(session_id)
            self._send_bridge_envelope(success_envelope(serialize_generation_result(result), operation="generate_script"), origin=origin)
            return
        if self.command == "POST" and suffix == "/audio:render":
            provider = str(body.get("provider_override") or "")
            script_id = str(body.get("script_id") or "").strip()
            self._send_bridge_envelope(
                self.context.start_render_audio(session_id, script_id=script_id, override_provider=provider),
                origin=origin,
            )
            return
        if self.command == "PUT" and suffix == "/script/final":
            self._save_script_final(session_id, final_text=str(body.get("final_text") or ""), origin=origin)
            return
        if self.command == "POST" and suffix == "/script:delete":
            self._delete_script(session_id, origin=origin)
            return
        if self.command == "POST" and suffix == "/script:restore":
            self._restore_script(session_id, origin=origin)
            return
        if self.command == "GET" and suffix == "/script/revisions":
            self._list_script_revisions(session_id, origin=origin)
            return
        if self.command == "POST" and suffix.startswith("/script/revisions/") and suffix.endswith(":rollback"):
            revision_id = suffix.removeprefix("/script/revisions/").removesuffix(":rollback")
            self._rollback_script_revision(session_id, revision_id=revision_id, origin=origin)
            return
        raise ValueError(f"Unknown route: {path}")

    def _handle_stream_reply(self, session_id: str, body: dict[str, Any], origin: str | None) -> None:
        message = str(body.get("message") or "").strip()
        if not message:
            raise ValueError("Field 'message' is required.")
        project = self.context.store.load_project(session_id)
        if project.session.is_deleted():
            raise ValueError("Session is deleted. Restore it before continuing.")
        user_requested_finish = bool(body.get("user_requested_finish"))

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._send_cors_headers(origin)
        self.end_headers()

        try:
            final_result: InterviewTurnResult | None = None
            for chunk in self.context.orchestrator.submit_user_response_stream(
                session_id,
                message,
                user_requested_finish=user_requested_finish,
            ):
                if isinstance(chunk, InterviewTurnResult):
                    final_result = chunk
                    continue
                self._write_sse_event("chunk", {"ok": True, "type": "chunk", "delta": chunk})
            if final_result is None:
                raise RuntimeError("Streaming finished without a final result record.")
            final_payload = success_envelope(
                serialize_turn_result(final_result),
                operation="submit_reply",
            )
            self._write_sse_event("final", final_payload)
        except BrokenPipeError:
            return
        except Exception as exc:  # pragma: no cover - exercised by integration tests
            error_payload = error_envelope(
                operation="submit_reply",
                code="python_core_error",
                message=str(exc),
                details={"exception_type": exc.__class__.__name__},
            )
            try:
                self._write_sse_event("final", error_payload)
            except BrokenPipeError:
                return

    def _write_sse_event(self, event: str, payload: dict[str, object]) -> None:
        data = json.dumps(payload)
        self.wfile.write(f"event: {event}\n".encode("utf-8"))
        for line in data.splitlines() or [data]:
            self.wfile.write(f"data: {line}\n".encode("utf-8"))
        self.wfile.write(b"\n")
        self.wfile.flush()

    def _serve_artifact_audio(self, query: dict[str, list[str]], *, origin: str | None) -> None:
        raw_path = (query.get("path") or [""])[-1].strip()
        if not raw_path:
            raise ValueError("Query parameter 'path' is required.")

        exports_dir = self.context.artifact_store.exports_dir.resolve()
        audio_path = Path(raw_path).resolve(strict=True)
        try:
            audio_path.relative_to(exports_dir)
        except ValueError as exc:
            raise ValueError("Artifact audio path must be inside the exports directory.") from exc
        if not audio_path.is_file():
            raise ValueError("Artifact audio path does not point to a file.")

        content_type = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".mp4": "audio/mp4",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }.get(audio_path.suffix.lower(), "application/octet-stream")
        self._send_binary(HTTPStatus.OK, audio_path.read_bytes(), content_type=content_type, origin=origin)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length") or "0")
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON request body must be an object.")
        return payload

    def _check_origin(self, *, preflight: bool) -> str | None | bool:
        if self.path == "/healthz":
            return None
        origin = self.headers.get("Origin")
        allowed_origin = self.context.get_allowed_origin(origin)
        if origin and allowed_origin is None:
            self._send_bridge_envelope(
                error_envelope(
                    operation=self._infer_operation(urlparse(self.path).path),
                    code="bridge_origin_rejected",
                    message=f"Origin '{origin}' is not allowed.",
                ),
                status=HTTPStatus.FORBIDDEN,
                origin=None,
            )
            return False
        return allowed_origin

    def _check_auth(self, path: str, origin: str | None) -> bool:
        protected = path.startswith("/api/v1/config/") or path.startswith("/admin/")
        if not protected:
            return True
        if not self.context.runtime_token:
            return True
        token = self.headers.get("X-AOD-Runtime-Token", "")
        if not token:
            self._send_bridge_envelope(
                error_envelope(
                    operation=self._infer_operation(path),
                    code="bridge_auth_required",
                    message="Runtime token is required for this endpoint.",
                ),
                status=HTTPStatus.UNAUTHORIZED,
                origin=origin,
            )
            return False
        if token != self.context.runtime_token:
            self._send_bridge_envelope(
                error_envelope(
                    operation=self._infer_operation(path),
                    code="bridge_auth_invalid",
                    message="Runtime token is invalid.",
                ),
                status=HTTPStatus.FORBIDDEN,
                origin=origin,
            )
            return False
        return True

    def _infer_operation(self, path: str) -> str:
        if path.startswith("/api/v1/projects"):
            return "list_projects"
        if path == "/api/v1/sessions":
            return "create_session"
        if "/interview:reply" in path:
            return "submit_reply"
        if "/interview:start" in path:
            return "start_interview"
        if "/interview:finish" in path:
            return "request_finish"
        if "/script:generate" in path:
            return "generate_script"
        if "/audio:render" in path:
            return "render_audio"
        if path == "/api/v1/voice-studio/presets":
            return "list_voice_presets"
        if path == "/api/v1/voice-studio/preview":
            return "render_voice_preview"
        if path == "/api/v1/artifacts/audio":
            return "serve_artifact_audio"
        if "/voice-takes:render" in path:
            return "render_voice_take"
        if "/voice-takes/" in path and path.endswith(":final"):
            return "set_final_voice_take"
        if path.startswith("/api/v1/tasks/") and path.endswith(":cancel"):
            return "cancel_task"
        if path.startswith("/api/v1/tasks/"):
            return "show_task_state"
        if path == "/api/v1/models/storage":
            return "show_model_storage"
        if path == "/api/v1/models/storage:migrate":
            return "migrate_model_storage"
        if path == "/api/v1/models/storage:reset":
            return "reset_model_storage"
        if path.startswith("/api/v1/models/") and path.endswith(":download"):
            return "download_model"
        if path.startswith("/api/v1/models/") and path.endswith(":delete"):
            return "delete_model"
        if path.startswith("/api/v1/config/llm"):
            return "configure_llm_provider" if self.command == "PUT" else "show_llm_config"
        if path.startswith("/api/v1/config/tts"):
            return "configure_tts_provider" if self.command == "PUT" else "show_tts_config"
        if path.startswith("/api/v1/runtime/bootstrap"):
            return "runtime_bootstrap"
        if path.startswith("/api/v1/runtime/tts/local-capability"):
            return "show_local_tts_capability"
        return "http_runtime"

    def _send_bridge_envelope(
        self,
        payload: dict[str, object],
        *,
        status: HTTPStatus | None = None,
        origin: str | None,
    ) -> None:
        payload_with_runtime = dict(payload)
        runtime_metadata = self.context.runtime_metadata()
        if payload_with_runtime.get("ok") is False:
            error = payload_with_runtime.get("error")
            if isinstance(error, dict):
                details = error.get("details")
                details_dict = dict(details) if isinstance(details, dict) else {}
                details_dict.setdefault("runtime", runtime_metadata)
                error["details"] = details_dict
        else:
            payload_with_runtime["runtime"] = runtime_metadata
        resolved_status = status or self._status_for_payload(payload_with_runtime)
        self._send_json(resolved_status, payload_with_runtime, origin=origin)

    def _status_for_payload(self, payload: dict[str, object]) -> HTTPStatus:
        if payload.get("ok") is True:
            return HTTPStatus.OK
        error = payload.get("error")
        if not isinstance(error, dict):
            return HTTPStatus.INTERNAL_SERVER_ERROR
        code = str(error.get("code") or "")
        if code in {"bridge_origin_rejected", "bridge_auth_invalid"}:
            return HTTPStatus.FORBIDDEN
        if code in {"bridge_auth_required", "bridge_bootstrap_unavailable", "bridge_bootstrap_invalid", "bridge_bootstrap_expired"}:
            return HTTPStatus.UNAUTHORIZED
        if code == "task_cancelled":
            return HTTPStatus.CONFLICT
        if code == "python_core_error":
            return HTTPStatus.BAD_REQUEST
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def _send_json(self, status: HTTPStatus, payload: dict[str, object], *, origin: str | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers(origin)
        self.end_headers()
        self.wfile.write(body)

    def _send_binary(self, status: HTTPStatus, body: bytes, *, content_type: str, origin: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_cors_headers(origin)
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self, origin: str | None) -> None:
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,PUT,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-AOD-Runtime-Token")


class RuntimeHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], runtime_context: RuntimeContext) -> None:
        super().__init__(server_address, RuntimeRequestHandler)
        self.runtime_context = runtime_context


def _normalize_allowed_origins(raw_origins: str | None) -> frozenset[str]:
    if not raw_origins:
        return _DEFAULT_ALLOWED_ORIGINS
    values = [item.strip() for item in raw_origins.split(",")]
    filtered = {item for item in values if item}
    return frozenset(filtered) if filtered else _DEFAULT_ALLOWED_ORIGINS


def serve_http(
    *,
    cwd: Path,
    host: str,
    port: int,
    runtime_token: str | None = None,
    allowed_origins: str | None = None,
    bootstrap_nonce: str | None = None,
) -> int:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("HTTP runtime must bind to 127.0.0.1 or ::1 only.")

    config = AppConfig.from_cwd(cwd)
    store = ProjectStore(config.data_dir)
    config_store = ConfigStore(config.config_dir)
    artifact_store = ArtifactStore(config.data_dir)
    request_state_store = RequestStateStore(config.data_dir)
    orchestrator = InterviewOrchestrator(store, config_store)
    script_generation = ScriptGenerationService(store, config_store)
    audio_rendering = AudioRenderingService(store, config_store, artifact_store)

    store.bootstrap()
    config_store.bootstrap()
    artifact_store.bootstrap()
    request_state_store.bootstrap()

    context = RuntimeContext(
        cwd=cwd,
        config=config,
        store=store,
        config_store=config_store,
        artifact_store=artifact_store,
        request_state_store=request_state_store,
        orchestrator=orchestrator,
        script_generation=script_generation,
        audio_rendering=audio_rendering,
        runtime_token=runtime_token or "",
        bootstrap_nonce=bootstrap_nonce,
        bootstrap_created_at=time.time(),
        runtime_started_at=time.time(),
        runtime_build_token=uuid.uuid4().hex,
        allowed_origins=_normalize_allowed_origins(allowed_origins),
    )

    server = RuntimeHttpServer((host, port), context)
    print(
        json.dumps(
            {
                "ok": True,
                "status": "ready",
                "host": host,
                "port": port,
                "base_url": f"http://{host}:{port}",
                "service": "aodcast-python-core-http",
            }
        )
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:  # pragma: no cover - manual stop path
        pass
    finally:
        server.server_close()
    return 0
