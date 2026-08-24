from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
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
    serialize_memory_entry,
    serialize_memory_overview,
    serialize_project,
    serialize_script_revisions,
    serialize_turn_result,
    serialize_voice_settings,
    voice_settings_from_payload,
)
from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.episode_source import (
    EpisodeSource,
    SourceConversionMode,
    SourceImportKind,
    SourceTargetLength,
)
from app.domain.project import SessionProject
from app.domain.session import CreationMode, SessionRecord, SessionState
from app.domain.transcript import Speaker, TranscriptRecord
from app.domain.voice_studio import STANDARD_PREVIEW_TEXT, STYLE_PRESETS, VOICE_PRESETS
from app.models_catalog import (
    build_models_status,
    delete_voice_model,
    download_voice_model,
    migrate_model_storage,
    model_storage_status,
    reset_model_storage,
    resolve_voice_model_id,
    stop_download_process,
    voice_model_is_downloaded,
)
from app.orchestration.audio_rendering import (
    AudioRenderingService,
    AudioRenderProgress,
)
from app.orchestration.interview_service import InterviewOrchestrator, InterviewTurnResult
from app.orchestration.memory_service import MemoryService
from app.orchestration.script_generation import ScriptGenerationService
from app.providers.llm.factory import validate_llm_provider
from app.providers.llm.preflight import check_llm_config
from app.providers.llm.codex_app_server import codex_provider_status, start_codex_login
from app.providers.tts_api.factory import validate_tts_provider
from app.providers.tts_local_mlx.presets import DEFAULT_LOCAL_TTS_MODEL
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability
from app.runtime.long_task_state import LongTaskStateManager
from app.runtime.request_state_store import RequestStateStore
from app.runtime.task_cancellation import TaskCancellationRequested
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore
from app.storage.speaker_reference_store import SpeakerReferenceStore

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


@dataclass(frozen=True, slots=True)
class MultipartFile:
    filename: str
    content_type: str
    content: bytes



def _normalize_error_message(exc: Exception, *, fallback: str) -> str:
    message = str(exc).strip()
    return message or fallback



def create_project(topic: str, intent: str) -> SessionProject:
    session = SessionRecord(topic=topic, creation_intent=intent)
    transcript = TranscriptRecord(session_id=session.session_id)
    artifact = ArtifactRecord(
        session_id=session.session_id,
        transcript_path=f"sessions/{session.session_id}/transcript.json",
    )
    return SessionProject(
        session=session,
        transcript=transcript,
        script=None,
        artifact=artifact,
    )


def create_markdown_project(
    *,
    raw_markdown: str,
    name: str,
    import_kind: str,
    conversion_mode: str,
    target_length: str,
    focus_instructions: str,
) -> SessionProject:
    session = SessionRecord(
        topic="Imported Markdown",
        creation_intent="Turn an imported Markdown article into a solo podcast.",
        creation_mode=CreationMode.MARKDOWN,
        memory_mode="disabled",
    )
    source = EpisodeSource.from_markdown(
        session_id=session.session_id,
        raw_markdown=raw_markdown,
        name=name,
        import_kind=SourceImportKind(import_kind),
        conversion_mode=SourceConversionMode(conversion_mode),
        target_length=SourceTargetLength(target_length),
        focus_instructions=focus_instructions,
    )
    session.rename_topic(source.title)
    session.transition(SessionState.READY_TO_GENERATE)
    return SessionProject(
        session=session,
        source=source,
        transcript=None,
        script=None,
        artifact=ArtifactRecord(session_id=session.session_id),
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
    active_download_processes: dict[str, subprocess.Popen[str]] = field(default_factory=dict)
    bootstrap_nonce_used: bool = False
    speaker_reference_store: SpeakerReferenceStore | None = None
    memory_service: MemoryService | None = None

    def runtime_metadata(self) -> dict[str, object]:
        return {
            "pid": os.getpid(),
            "started_at_unix": self.runtime_started_at,
            "build_token": self.runtime_build_token,
        }

    def register_download_process(self, task_id: str, proc: subprocess.Popen[str]) -> None:
        with self.task_lock:
            self.active_download_processes[task_id] = proc

    def unregister_download_process(self, task_id: str, proc: subprocess.Popen[str]) -> None:
        with self.task_lock:
            current = self.active_download_processes.get(task_id)
            if current is proc:
                self.active_download_processes.pop(task_id, None)

    def shutdown_download_processes(self, *, mark_failed: bool = True) -> None:
        """Kill tracked download process groups and clear sticky running markers.

        Download children use ``start_new_session=True``, so killing only the
        runtime PID leaves orphans. Runtime stop paths (SIGTERM/SIGINT/finally)
        must call this so ownership stays with the HTTP process.
        """

        with self.task_lock:
            procs = list(self.active_download_processes.items())
            self.active_download_processes.clear()
        for task_id, proc in procs:
            stop_download_process(proc)
            if not mark_failed:
                continue
            existing = self.request_state_store.load(task_id)
            phase = ""
            if isinstance(existing, dict):
                phase = str(existing.get("phase") or "").strip().lower()
            if phase not in {"running", "cancelling"}:
                continue
            self.request_state_store.save(
                task_id,
                build_request_state(
                    operation=str(existing.get("operation") or "download_model"),
                    phase="failed",
                    progress_percent=progress_from_request_state(existing, default=5.0),
                    message=(
                        "Download interrupted because the runtime stopped. "
                        "Retry the download to resume."
                    ),
                    run_token=str(existing.get("run_token") or "") or None,
                ),
            )

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

    def get_speaker_reference_store(self) -> SpeakerReferenceStore:
        if self.speaker_reference_store is None:
            self.speaker_reference_store = SpeakerReferenceStore(self.config.data_dir, self.artifact_store)
            self.speaker_reference_store.bootstrap()
        return self.speaker_reference_store

    def get_memory_service(self) -> MemoryService:
        if self.memory_service is None:
            self.memory_service = MemoryService(self.config.data_dir, self.store, self.config_store)
            self.memory_service.bootstrap()
        return self.memory_service

    def is_task_worker_alive(self, task_id: str) -> bool:
        with self.task_lock:
            thread = self.active_tasks.get(task_id)
            return thread is not None and thread.is_alive()

    def reconcile_inactive_task(
        self,
        task_id: str,
        *,
        prefer_cancelled: bool = False,
    ) -> dict[str, object] | None:
        """Force a terminal phase when disk says active but no live worker remains.

        Cooperative cancel alone leaves ``cancelling`` forever after OOM / crash.
        Returns the terminal request_state when reconciliation happened, else None.
        """
        state = self.request_state_store.load(task_id)
        if not isinstance(state, dict):
            return None
        phase = str(state.get("phase") or "").strip().lower()
        if phase not in {"running", "cancelling"}:
            return None
        if self.is_task_worker_alive(task_id):
            return None

        with self.task_lock:
            self.active_tasks.pop(task_id, None)

        run_token = str(state.get("run_token") or "").strip()
        cancel_requested = (
            prefer_cancelled
            or phase == "cancelling"
            or self.request_state_store.is_cancel_requested(task_id, run_token=run_token)
        )
        operation = str(state.get("operation") or "task")
        progress_percent = progress_from_request_state(state, default=0.0)
        if cancel_requested:
            terminal = build_request_state(
                operation=operation,
                phase="cancelled",
                progress_percent=progress_percent,
                message="Render cancelled.",
                run_token=run_token or None,
            )
        else:
            terminal = build_request_state(
                operation=operation,
                phase="failed",
                progress_percent=progress_percent,
                message=(
                    "Render stopped unexpectedly. The worker is no longer running. "
                    "Try generating again."
                ),
                run_token=run_token or None,
            )
        self.request_state_store.save(task_id, terminal)
        self.request_state_store.clear_cancel_request(task_id, run_token=run_token)
        self._release_session_for_render_task(task_id, message=str(terminal.get("message") or ""))
        return terminal

    def _release_session_for_render_task(self, task_id: str, *, message: str) -> None:
        if not task_id.startswith("render_audio:"):
            return
        parts = task_id.split(":", 2)
        if len(parts) < 2 or not parts[1].strip():
            return
        try:
            self.store.release_stuck_audio_render(parts[1].strip(), message=message)
        except Exception:
            # Session may be missing; task state is still finalized for the UI.
            return

    def start_render_audio(
        self,
        session_id: str,
        *,
        script_id: str = "",
        override_provider: str = "",
        override_model: str = "",
        settings: VoiceRenderSettings | None = None,
        require_speaker_reference: bool = False,
    ) -> dict[str, object]:
        project = self.store.load_project_for_script(session_id, script_id) if script_id.strip() else self.store.load_project(session_id)
        if project.session.is_deleted():
            raise ValueError("Session is deleted. Restore it before continuing.")
        if project.script is None:
            raise ValueError("Cannot continue without a script record.")
        if project.script.is_deleted():
            raise ValueError("Script is deleted. Restore it before continuing.")
        script_id = project.script.script_id
        if override_model and not voice_model_is_downloaded(self.cwd, override_model, self.config_store):
            raise ValueError("The selected local TTS model is not downloaded. Install it from Models first.")
        task_id = f"render_audio:{session_id}:{script_id}"
        with self.task_lock:
            existing_thread = self.active_tasks.get(task_id)
            if existing_thread is not None and existing_thread.is_alive():
                existing_state = self.request_state_store.load(task_id)
                if isinstance(existing_state, dict):
                    return success_envelope(
                        {
                            "project": serialize_project(project),
                            "provider": str(project.session.tts_provider or ""),
                            "model": str(override_model or self.config_store.load_tts_config().model or ""),
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

        # Orphaned running/cancelling marker after OOM or crash — clear before a new run.
        self.reconcile_inactive_task(task_id)

        with self.task_lock:
            run_token = uuid.uuid4().hex

            def tagged_build_request_state(**kwargs: Any) -> dict[str, object]:
                return build_request_state(run_token=run_token, **kwargs)

            progress = LongTaskStateManager(
                request_state_store=self.request_state_store,
                task_id=task_id,
                operation="render_audio",
                build_request_state=tagged_build_request_state,
                should_cancel=lambda: self.request_state_store.is_cancel_requested(task_id, run_token=run_token),
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
                        override_model=override_model,
                        settings=settings,
                        require_speaker_reference=require_speaker_reference,
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
                    if self.request_state_store.is_cancel_requested(task_id, run_token=run_token) or current_phase == "cancelling":
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
                "model": str(override_model or self.config_store.load_tts_config().model or ""),
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

    def start_regenerate_audio_window(
        self,
        session_id: str,
        *,
        script_id: str,
        target_segment_id: str,
        expected_plan_id: str,
        expected_render_id: str,
    ) -> dict[str, object]:
        project = self.store.load_project_for_script(session_id, script_id)
        ensure_session_is_active(project)
        ensure_script_is_active(project)
        if project.speech_plan is None or project.render_manifest is None:
            raise ValueError("Generate the full podcast before regenerating a segment.")
        if project.speech_plan.plan_id != expected_plan_id or project.render_manifest.render_id != expected_render_id:
            raise ValueError("Speech plan or render manifest is stale. Refresh and try again.")
        affected_segment_ids = [
            segment.segment_id
            for segment in project.speech_plan.context_window(target_segment_id, radius=1)
        ]
        task_id = f"render_audio:{session_id}:{script_id}"
        with self.task_lock:
            existing_thread = self.active_tasks.get(task_id)
            if existing_thread is not None and existing_thread.is_alive():
                existing_state = self.request_state_store.load(task_id) or {}
                return success_envelope(
                    {
                        "project": serialize_project(project),
                        "task_id": task_id,
                        "run_token": str(existing_state.get("run_token") or ""),
                        "affected_segment_ids": affected_segment_ids,
                    },
                    operation="regenerate_audio_window",
                    message=str(existing_state.get("message") or "Rendering audio..."),
                    phase=str(existing_state.get("phase") or "running"),
                    progress_percent=progress_from_request_state(existing_state, default=5.0),
                    run_token=str(existing_state.get("run_token") or ""),
                )

        self.reconcile_inactive_task(task_id)

        with self.task_lock:
            run_token = uuid.uuid4().hex

            def tagged_build_request_state(**kwargs: Any) -> dict[str, object]:
                return build_request_state(run_token=run_token, **kwargs)

            progress = LongTaskStateManager(
                request_state_store=self.request_state_store,
                task_id=task_id,
                operation="regenerate_audio_window",
                build_request_state=tagged_build_request_state,
                should_cancel=lambda: self.request_state_store.is_cancel_requested(task_id, run_token=run_token),
            )
            self.request_state_store.clear_cancel_request(task_id)
            progress.start(
                progress_percent=5.0,
                message=f"Regenerating {len(affected_segment_ids)} context segments...",
            )

            def worker() -> None:
                def on_progress(snapshot: AudioRenderProgress) -> None:
                    progress.set_progress(snapshot.percent, snapshot.message, max_percent=99.0)

                try:
                    self.audio_rendering.regenerate_audio_window_with_cancellation(
                        session_id,
                        script_id=script_id,
                        target_segment_id=target_segment_id,
                        expected_plan_id=expected_plan_id,
                        expected_render_id=expected_render_id,
                        should_cancel=progress.should_cancel,
                        on_progress=on_progress,
                    )
                except TaskCancellationRequested as exc:
                    self.raise_task_cancelled(
                        progress,
                        task_id=task_id,
                        operation="regenerate_audio_window",
                        message=str(exc),
                        default_progress=10.0,
                    )
                except Exception as exc:  # pragma: no cover - integration coverage
                    if self.request_state_store.is_cancel_requested(task_id, run_token=run_token) or progress.current_phase() == "cancelling":
                        self.raise_task_cancelled(
                            progress,
                            task_id=task_id,
                            operation="regenerate_audio_window",
                            message=f"Audio regeneration cancelled for session {session_id}.",
                            default_progress=10.0,
                            source_error=exc,
                        )
                    self.fail_task(
                        progress,
                        task_id=task_id,
                        message=_normalize_error_message(exc, fallback="Audio regeneration failed."),
                        fallback_message="Audio regeneration failed.",
                    )
                else:
                    self.complete_task_success(
                        progress,
                        task_id=task_id,
                        operation="regenerate_audio_window",
                        finalizing_progress=99.0,
                        finalizing_message="Publishing regenerated podcast audio...",
                        success_message="Audio regeneration finished.",
                        fallback_failure_message="Unable to finalize regenerated audio.",
                        cancellation_message="Audio regeneration cancelled.",
                    )
                finally:
                    with self.task_lock:
                        self.active_tasks.pop(task_id, None)

            thread = threading.Thread(target=worker, name=task_id, daemon=True)
            self.active_tasks[task_id] = thread
            thread.start()

        started_state = self.request_state_store.load(task_id) or {}
        return success_envelope(
            {
                "project": serialize_project(project),
                "task_id": task_id,
                "run_token": run_token,
                "affected_segment_ids": affected_segment_ids,
            },
            operation="regenerate_audio_window",
            message=str(started_state.get("message") or "Regenerating audio..."),
            phase=str(started_state.get("phase") or "running"),
            progress_percent=progress_from_request_state(started_state, default=5.0),
            run_token=run_token,
        )

    def start_render_voice_preview(
        self,
        settings: VoiceRenderSettings,
        *,
        session_id: str = "",
        script_id: str = "",
        override_provider: str = "",
        override_model: str = "",
        speaker_reference_id: str = "",
    ) -> dict[str, object]:
        self.request_state_store.cleanup_terminal_states(
            prefix="render_voice_preview:",
            max_age_seconds=6 * 60 * 60,
        )
        if override_model and not voice_model_is_downloaded(self.cwd, override_model, self.config_store):
            raise ValueError("The selected local TTS model is not downloaded. Install it from Models first.")
        run_token = uuid.uuid4().hex
        task_id = f"render_voice_preview:{run_token}"
        def tagged_build_request_state(**kwargs: Any) -> dict[str, object]:
            state = build_request_state(run_token=run_token, **kwargs)
            state["task_id"] = task_id
            return state

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
                        run_token=str(existing_state.get("run_token") or run_token),
                    )

            progress = LongTaskStateManager(
                request_state_store=self.request_state_store,
                task_id=task_id,
                operation="render_voice_preview",
                build_request_state=tagged_build_request_state,
                should_cancel=lambda: self.request_state_store.is_cancel_requested(task_id, run_token=run_token),
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
                    speaker_reference: dict[str, object] | None = None
                    if speaker_reference_id.strip():
                        reference = self.get_speaker_reference_store().get_reference(speaker_reference_id)
                        speaker_reference = reference.to_dict()
                    result = self.audio_rendering.render_voice_preview_with_cancellation(
                        settings,
                        override_provider=override_provider,
                        override_model=override_model,
                        speaker_reference=speaker_reference,
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
                    if self.request_state_store.is_cancel_requested(task_id, run_token=run_token) or progress.current_phase() == "cancelling":
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
                                run_token=run_token,
                            ),
                            "task_id": task_id,
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
        envelope = success_envelope(
            {"task_id": task_id},
            operation="render_voice_preview",
            message=str((started_state or {}).get("message") or "Rendering voice preview..."),
            phase=str((started_state or {}).get("phase") or "running"),
            progress_percent=progress_from_request_state(started_state, default=5.0),
            run_token=run_token,
        )
        if isinstance(started_state, dict):
            envelope["data"]["request_state"] = started_state  # type: ignore[index]
        return envelope

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

            # Runtime restart can leave a running marker with no live worker.
            if isinstance(existing_state, dict):
                stale_phase = str(existing_state.get("phase") or "").strip().lower()
                if stale_phase in {"running", "cancelling"}:
                    self.request_state_store.save(
                        task_id,
                        build_request_state(
                            operation="download_model",
                            phase="failed",
                            progress_percent=progress_from_request_state(existing_state, default=5.0),
                            message=(
                                f"Previous download for {model_name} was interrupted by a runtime restart. "
                                "Retry the download to resume."
                            ),
                        ),
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
                    max_percent=65.0,
                    step_percent=0.8,
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
                        on_process_started=lambda proc: self.register_download_process(task_id, proc),
                        on_process_finished=lambda proc: self.unregister_download_process(task_id, proc),
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

    def create_session_payload(
        self,
        *,
        topic: str,
        creation_intent: str,
        source_input: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        if source_input is None:
            project = create_project(topic, creation_intent)
        else:
            project = create_markdown_project(
                raw_markdown=str(source_input.get("raw_markdown") or ""),
                name=str(source_input.get("name") or "Pasted Markdown"),
                import_kind=str(source_input.get("import_kind") or "paste"),
                conversion_mode=str(source_input.get("conversion_mode") or "adapt"),
                target_length=str(source_input.get("target_length") or "auto"),
                focus_instructions=str(source_input.get("focus_instructions") or ""),
            )
        self.store.save_project(project)
        return success_envelope({"project": serialize_project(project)}, operation="create_session")

    def update_source_payload(self, session_id: str, source_input: dict[str, Any]) -> dict[str, object]:
        project = self.store.load_project(session_id)
        ensure_session_is_active(project)
        if project.session.creation_mode != CreationMode.MARKDOWN or project.source is None:
            raise ValueError("This episode does not have a Markdown source.")
        project.source = self.store.replace_source(
            session_id=session_id,
            raw_markdown=str(source_input.get("raw_markdown") or ""),
            name=str(source_input.get("name") or project.source.name),
            import_kind=SourceImportKind(str(source_input.get("import_kind") or project.source.import_kind.value)),
            conversion_mode=SourceConversionMode(str(source_input.get("conversion_mode") or project.source.conversion_mode.value)),
            target_length=SourceTargetLength(str(source_input.get("target_length") or project.source.target_length.value)),
            focus_instructions=str(source_input.get("focus_instructions") or ""),
        )
        project.session.updated_at = project.source.updated_at
        self.store.save_session(project.session)
        return success_envelope({"project": serialize_project(project)}, operation="update_episode_source")


def _query_flag(query: dict[str, list[str]], key: str) -> bool:
    values = query.get(key)
    if not values:
        return False
    return values[-1].strip().lower() in {"1", "true", "yes", "on"}


def _body_flag(body: dict[str, Any], key: str) -> bool:
    value = body.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    if value is None:
        return False
    return bool(value)


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

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch()

    def log_message(self, _format: str, *args: Any) -> None:
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
            body = (
                {}
                if self._is_multipart_request()
                else self._read_json_body() if self.command in {"POST", "PATCH", "PUT"} else {}
            )
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
        self.context.store.save_script_and_session(project.session, project.script)
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
        self.context.store.save_script_and_session(project.session, project.script)
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
        self.context.store.save_script_and_session(project.session, project.script)
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
        self.context.store.save_script_and_session(project.session, project.script)
        self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="rollback_script_revision"), origin=origin)

    def _route_memory(
        self,
        path: str,
        query: dict[str, list[str]],
        body: dict[str, Any],
        origin: str | None,
    ) -> None:
        memory = self.context.get_memory_service()

        def send_overview(operation: str) -> None:
            self._send_bridge_envelope(
                success_envelope(
                    {"memory": serialize_memory_overview(memory.get_overview())},
                    operation=operation,
                ),
                origin=origin,
            )

        if self.command == "GET" and path == "/api/v1/memory":
            send_overview("show_memory_overview")
            return
        if self.command == "PATCH" and path == "/api/v1/memory/settings":
            writing = body.get("writing_enabled")
            usage = body.get("usage_enabled")
            memory.update_settings(
                writing_enabled=bool(writing) if writing is not None else None,
                usage_enabled=bool(usage) if usage is not None else None,
            )
            send_overview("update_memory_settings")
            return
        if self.command == "POST" and path == "/api/v1/memory:acknowledge":
            memory.acknowledge_first_run()
            send_overview("acknowledge_memory")
            return
        if self.command == "POST" and path == "/api/v1/memory:clear":
            memory.clear_all()
            send_overview("clear_memory")
            return
        if self.command == "POST" and path == "/api/v1/memory:maintain":
            memory.run_maintenance_now()
            send_overview("run_memory_maintenance")
            return
        if self.command == "GET" and path == "/api/v1/memory/superseded":
            items = [serialize_memory_entry(entry) for entry in memory.list_superseded()]
            self._send_bridge_envelope(
                success_envelope({"items": items}, operation="list_memory_superseded"),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/memory/usage":
            self._send_bridge_envelope(
                success_envelope(
                    {"events": self._collect_memory_usage_events()},
                    operation="list_memory_usage",
                ),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/memory/items":
            search = (query.get("search") or [""])[-1].strip() or None
            mem_type = (query.get("type") or [""])[-1].strip() or None
            items = [serialize_memory_entry(entry) for entry in memory.list_memories(search=search, type=mem_type)]
            self._send_bridge_envelope(
                success_envelope({"items": items}, operation="list_memory_items"),
                origin=origin,
            )
            return
        if path.startswith("/api/v1/memory/items/"):
            memory_id = unquote(path.removeprefix("/api/v1/memory/items/")).strip("/")
            if self.command == "GET":
                entry = memory.get_memory(memory_id)
                if entry is None:
                    raise ValueError(f"Unknown memory id '{memory_id}'.")
                self._send_bridge_envelope(
                    success_envelope({"item": serialize_memory_entry(entry)}, operation="show_memory_item"),
                    origin=origin,
                )
                return
            if self.command == "DELETE":
                deleted = memory.delete_memory(memory_id)
                self._send_bridge_envelope(
                    success_envelope(
                        {"memory_id": memory_id, "deleted": deleted},
                        operation="delete_memory_item",
                    ),
                    origin=origin,
                )
                return
        # §10.4: list active memories matching a free-text query (forget disambiguation).
        if self.command == "GET" and path == "/api/v1/memory/forget-candidates":
            q = (query.get("q") or [""])[-1].strip()
            candidates = memory.find_forget_candidates(q)
            self._send_bridge_envelope(
                success_envelope(
                    {"candidates": [serialize_memory_entry(e) for e in candidates]},
                    operation="list_forget_candidates",
                ),
                origin=origin,
            )
            return
        # §10.3: user-confirmed supersede of a specific memory (correction disambiguation).
        if self.command == "POST" and path == "/api/v1/memory:supersede":
            memory_id = str(body.get("memory_id") or "").strip()
            if not memory_id:
                raise ValueError("Field 'memory_id' is required.")
            ok = memory.supersede_memory(memory_id)
            self._send_bridge_envelope(
                success_envelope(
                    {"memory_id": memory_id, "superseded": ok},
                    operation="supersede_memory",
                ),
                origin=origin,
            )
            return
        raise ValueError(f"Unsupported memory route: {self.command} {path}")

    def _notify_memory_session_event(self, session_id: str, *, deleted: bool) -> None:
        """Best-effort §15.4 source-lifecycle hook. Never blocks the response."""
        if self.context.memory_service is None:
            return
        try:
            if deleted:
                self.context.memory_service.on_session_deleted(session_id)
            else:
                self.context.memory_service.on_session_restored(session_id)
        except Exception:
            pass

    def _collect_memory_usage_events(self, *, limit: int = 50) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        for session in self.context.store.list_sessions(include_deleted=True):
            for event in session.memory_usage_events:
                events.append(
                    {
                        "session_id": session.session_id,
                        "session_topic": session.topic,
                        "operation": event.get("operation", ""),
                        "memory_ids": event.get("memory_ids", []),
                        "used_at": event.get("used_at", ""),
                    }
                )
        events.sort(key=lambda item: str(item.get("used_at") or ""), reverse=True)
        return events[:limit]

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
            source_payload = body.get("source")
            if source_payload is not None and not isinstance(source_payload, dict):
                raise ValueError("Field 'source' must be an object.")
            self._send_bridge_envelope(
                self.context.create_session_payload(
                    topic=topic,
                    creation_intent=creation_intent,
                    source_input=source_payload,
                ),
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
        if path == "/api/v1/memory" or path.startswith("/api/v1/memory/") or path.startswith("/api/v1/memory:"):
            self._route_memory(path, query, body, origin)
            return
        if self.command == "GET" and path == "/api/v1/speaker-references":
            references = [
                reference.to_dict()
                for reference in self.context.get_speaker_reference_store().list_references()
            ]
            self._send_bridge_envelope(
                success_envelope({"speaker_references": references}, operation="list_speaker_references"),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/api/v1/speaker-references":
            fields, files = self._read_multipart_form()
            sample = files.get("audio")
            if sample is None:
                raise ValueError("Multipart field 'audio' is required.")
            suffix = Path(sample.filename).suffix.lower() or f".{fields.get('audio_format', 'wav').lstrip('.')}"
            with tempfile.NamedTemporaryFile(prefix="aodcast-speaker-reference-", suffix=suffix, delete=False) as temp_file:
                temp_file.write(sample.content)
                temp_path = Path(temp_file.name)
            try:
                reference = self.context.get_speaker_reference_store().create_user_reference(
                    name=fields.get("name", ""),
                    source_audio_path=temp_path,
                    reference_text=fields.get("reference_text", ""),
                    language=fields.get("language", "zh"),
                    audio_format=fields.get("audio_format", ""),
                )
            finally:
                temp_path.unlink(missing_ok=True)
            self._send_bridge_envelope(
                success_envelope({"speaker_reference": reference.to_dict()}, operation="create_speaker_reference"),
                origin=origin,
            )
            return
        if path.startswith("/api/v1/speaker-references/"):
            reference_id = unquote(path.removeprefix("/api/v1/speaker-references/")).strip("/")
            reference_store = self.context.get_speaker_reference_store()
            if self.command == "PATCH":
                fields: dict[str, str] = {}
                sample_path: Path | None = None
                if self._is_multipart_request():
                    fields, files = self._read_multipart_form()
                    sample = files.get("audio")
                    if sample is not None:
                        suffix = Path(sample.filename).suffix.lower() or f".{fields.get('audio_format', 'wav').lstrip('.')}"
                        with tempfile.NamedTemporaryFile(prefix="aodcast-speaker-reference-update-", suffix=suffix, delete=False) as temp_file:
                            temp_file.write(sample.content)
                            sample_path = Path(temp_file.name)
                else:
                    fields = {str(key): str(value) for key, value in body.items() if value is not None}
                try:
                    reference = reference_store.update_reference(
                        reference_id,
                        name=fields.get("name"),
                        reference_text=fields.get("reference_text"),
                        source_audio_path=sample_path,
                        language=fields.get("language"),
                        audio_format=fields.get("audio_format", ""),
                    )
                finally:
                    if sample_path is not None:
                        sample_path.unlink(missing_ok=True)
                self._send_bridge_envelope(
                    success_envelope({"speaker_reference": reference.to_dict()}, operation="update_speaker_reference"),
                    origin=origin,
                )
                return
            if self.command == "DELETE":
                reference = reference_store.get_reference(reference_id)
                dependent_count = self.context.store.count_speaker_reference_dependencies(reference_id)
                if dependent_count:
                    raise ValueError(
                        f"Speaker Reference is still used by {dependent_count} script selection(s) or render(s). "
                        "Select another reference and delete dependent audio first."
                    )
                deleted = reference_store.delete_reference(reference_id)
                self._send_bridge_envelope(
                    success_envelope(
                        {
                            "speaker_reference_id": reference_id,
                            "deleted": deleted,
                        },
                        operation="delete_speaker_reference",
                    ),
                    origin=origin,
                )
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
            session_id = str(body.get("session_id") or "").strip()
            script_id = str(body.get("script_id") or "").strip()
            provider = str(body.get("provider_override") or "").strip()
            raw_model_id = str(body.get("model_id") or "").strip()
            model_id = resolve_voice_model_id(raw_model_id) if raw_model_id else ""
            speaker_reference_id = str(body.get("speaker_reference_id") or "").strip()
            self._send_bridge_envelope(
                self.context.start_render_voice_preview(
                    voice_settings_from_payload(body),
                    session_id=session_id,
                    script_id=script_id,
                    override_provider=provider,
                    override_model=model_id,
                    speaker_reference_id=speaker_reference_id,
                ),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/artifacts/audio":
            self._serve_artifact_audio(query, origin=origin)
            return
        if self.command == "DELETE" and path == "/api/v1/artifacts/audio":
            self._delete_artifact_audio(query, origin=origin)
            return
        if self.command == "GET" and path == "/api/v1/config/llm":
            self._send_bridge_envelope(
                success_envelope({"llm_config": self.context.config_store.load_llm_config().to_dict()}, operation="show_llm_config"),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/config/llm/status":
            self._send_bridge_envelope(
                success_envelope(
                    {"llm_provider_status": codex_provider_status().to_dict()},
                    operation="show_llm_provider_status",
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/api/v1/config/llm/auth:start":
            provider = str(body.get("provider") or "").strip()
            if provider != "codex_subscription":
                raise ValueError("ChatGPT login is only supported for the codex_subscription provider.")
            login = start_codex_login()
            self._send_bridge_envelope(
                success_envelope(
                    {"llm_auth": login.to_dict()},
                    operation="start_llm_provider_login",
                ),
                origin=origin,
            )
            return
        if self.command == "GET" and path == "/api/v1/config/llm/preflight":
            preflight = check_llm_config(self.context.config_store.load_llm_config())
            self._send_bridge_envelope(
                success_envelope({"llm_preflight": preflight.to_dict()}, operation="check_llm_config"),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/api/v1/config/llm/test":
            provider = str(body.get("provider") or "").strip()
            model = str(body.get("model") or "").strip()
            reasoning_effort = str(body.get("reasoning_effort") or "auto").strip().lower()
            base_url = str(body.get("base_url") or "").strip()
            api_key = str(body.get("api_key") or "").strip()
            if provider == "mock":
                self._send_bridge_envelope(
                    success_envelope(
                        {"status": "success", "latency_ms": 0, "message": "Mock connection successful."},
                        operation="test_llm_connection"
                    ),
                    origin=origin,
                )
                return
            if provider == "openai_compatible":
                if not base_url:
                    raise ValueError("Field 'base_url' is required.")
                if not model:
                    raise ValueError("Field 'model' is required.")
                if not api_key:
                    raise ValueError("Field 'api_key' is required.")
                import time
                from openai import OpenAI
                try:
                    client = OpenAI(base_url=base_url, api_key=api_key)
                    start_time = time.perf_counter()
                    client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=1,
                    )
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    self._send_bridge_envelope(
                        success_envelope(
                            {"status": "success", "latency_ms": latency_ms, "message": f"Connection successful. (Latency: {latency_ms}ms)"},
                            operation="test_llm_connection"
                        ),
                        origin=origin,
                    )
                except Exception as exc:
                    self._send_bridge_envelope(
                        error_envelope(
                            operation="test_llm_connection",
                            code="llm_connection_failed",
                            message=f"Connection failed: {str(exc)}",
                        ),
                        origin=origin,
                    )
                return
            if provider == "codex_subscription":
                provider_status = codex_provider_status()
                if not provider_status.installed or not provider_status.authenticated:
                    self._send_bridge_envelope(
                        error_envelope(
                            operation="test_llm_connection",
                            code="llm_connection_failed",
                            message=provider_status.message,
                        ),
                        origin=origin,
                    )
                    return
                available_models = {item.id for item in provider_status.models}
                if model and model not in available_models:
                    self._send_bridge_envelope(
                        error_envelope(
                            operation="test_llm_connection",
                            code="llm_connection_failed",
                            message=f"Codex model '{model}' is not available for this ChatGPT account.",
                        ),
                        origin=origin,
                    )
                    return
                selected_model = (
                    next((item for item in provider_status.models if item.id == model), None)
                    if model
                    else next(
                        (item for item in provider_status.models if item.is_default),
                        provider_status.models[0] if provider_status.models else None,
                    )
                )
                if (
                    reasoning_effort != "auto"
                    and selected_model is not None
                    and reasoning_effort not in selected_model.supported_reasoning_efforts
                ):
                    self._send_bridge_envelope(
                        error_envelope(
                            operation="test_llm_connection",
                            code="llm_connection_failed",
                            message=(
                                f"Reasoning effort '{reasoning_effort}' is not supported by "
                                f"Codex model '{selected_model.id}'."
                            ),
                        ),
                        origin=origin,
                    )
                    return
                self._send_bridge_envelope(
                    success_envelope(
                        {
                            "status": "success",
                            "latency_ms": 0,
                            "message": provider_status.message,
                        },
                        operation="test_llm_connection",
                    ),
                    origin=origin,
                )
                return
            raise ValueError(f"Unsupported provider '{provider}' for LLM connection testing.")
        if self.command == "POST" and path == "/api/v1/config/tts/test":
            provider = str(body.get("provider") or "").strip()
            model = str(body.get("model") or "").strip()
            base_url = str(body.get("base_url") or "").strip()
            api_key = str(body.get("api_key") or "").strip()
            voice = str(body.get("voice") or "alloy").strip()
            audio_format = str(body.get("audio_format") or "wav").strip()
            if provider == "local_mlx":
                capability = detect_local_mlx_capability(self.context.config_store.load_tts_config())
                if capability.available:
                    self._send_bridge_envelope(
                        success_envelope(
                            {"status": "success", "latency_ms": 0, "message": "Local MLX runtime is healthy."},
                            operation="test_tts_connection"
                        ),
                        origin=origin,
                    )
                else:
                    self._send_bridge_envelope(
                        error_envelope(
                            operation="test_tts_connection",
                            code="tts_connection_failed",
                            message=f"Local MLX is unavailable: {' '.join(capability.reasons)}",
                        ),
                        origin=origin,
                    )
                return
            if provider == "openai_compatible":
                if not base_url:
                    raise ValueError("Field 'base_url' is required.")
                if not model:
                    raise ValueError("Field 'model' is required.")
                if not api_key:
                    raise ValueError("Field 'api_key' is required.")
                import time
                from urllib import request as urllib_request
                import json
                try:
                    payload = {
                        "model": model,
                        "voice": voice,
                        "input": "ping",
                        "response_format": "mp3",
                    }
                    req = urllib_request.Request(
                        url=base_url.rstrip("/") + "/audio/speech",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}",
                        },
                        method="POST",
                    )
                    start_time = time.perf_counter()
                    with urllib_request.urlopen(req, timeout=10) as response:
                        _ = response.read()
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    self._send_bridge_envelope(
                        success_envelope(
                            {"status": "success", "latency_ms": latency_ms, "message": f"Connection successful. (Latency: {latency_ms}ms)"},
                            operation="test_tts_connection"
                        ),
                        origin=origin,
                    )
                except Exception as exc:
                    self._send_bridge_envelope(
                        error_envelope(
                            operation="test_tts_connection",
                            code="tts_connection_failed",
                            message=f"Connection failed: {str(exc)}",
                        ),
                        origin=origin,
                    )
                return
            raise ValueError(f"Unsupported provider '{provider}' for TTS connection testing.")
        if self.command == "PUT" and path == "/api/v1/config/llm":
            provider = str(body.get("provider") or "").strip()
            if not provider:
                raise ValueError("Field 'provider' is required.")
            validate_llm_provider(provider)
            llm_config = self.context.config_store.load_llm_config()
            llm_config.provider = provider
            if "model" in body:
                llm_config.model = str(body.get("model") or "")
            if "reasoning_effort" in body:
                llm_config.reasoning_effort = (
                    str(body.get("reasoning_effort") or "auto").strip().lower() or "auto"
                )
            if "base_url" in body:
                llm_config.base_url = str(body.get("base_url") or "")
            if "api_key" in body:
                llm_config.api_key = str(body.get("api_key") or "")
            if provider == "codex_subscription":
                llm_config.base_url = ""
                llm_config.api_key = ""
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
                    tts_config.model = DEFAULT_LOCAL_TTS_MODEL
                else:
                    tts_config.model = model_value
            elif provider == "local_mlx" and tts_config.model in {"", "mock-voice"}:
                tts_config.model = DEFAULT_LOCAL_TTS_MODEL
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
            task_state = self.context.reconcile_inactive_task(task_id) or self.context.request_state_store.load(task_id)
            self._send_bridge_envelope(
                success_envelope(
                    {"task_id": task_id, "task_state": task_state},
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
            requested_run_token = str(body.get("run_token") or "").strip()
            if run_token and requested_run_token != run_token:
                raise ValueError("stale_task_run")
            self.context.request_state_store.request_cancel(
                task_id,
                run_token=requested_run_token,
            )
            cancelling_state = build_request_state(
                operation=operation,
                phase="cancelling",
                progress_percent=progress_percent,
                message=f"Cancellation requested for {task_id}.",
                run_token=run_token,
            )
            self.context.request_state_store.save(task_id, cancelling_state)
            # Dead/orphaned workers never observe cooperative cancel — finalize now.
            finalized = self.context.reconcile_inactive_task(task_id, prefer_cancelled=True)
            response_state = finalized or cancelling_state
            self._send_bridge_envelope(
                success_envelope(
                    {"task_id": task_id, "task_state": response_state},
                    operation="cancel_task",
                    message="cancellation_completed" if finalized else "cancellation_requested",
                    run_token=run_token,
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and path == "/admin/shutdown":
            self._send_json(HTTPStatus.OK, {"ok": True, "status": "shutting_down"}, origin=origin)
            self.context.shutdown_download_processes()
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
            
        if self.command == "POST" and path == "/api/v1/artifacts/audio/export":
            audio_path_str = str(body.get("audio_path") or "").strip()
            target_format = str(body.get("format") or "m4a").strip().lower().replace(".", "")
            bitrate = str(body.get("bitrate") or "128k").strip().lower()
            custom_filename = str(body.get("filename") or "").strip()

            if not audio_path_str:
                raise ValueError("Field 'audio_path' is required.")
            if target_format not in {"wav", "mp3", "m4a"}:
                raise ValueError(f"Unsupported export format '{target_format}'. Supported formats: wav, mp3, m4a.")

            # Bitrate normalization
            bitrate_val = bitrate.rstrip("bps").rstrip("b")
            if bitrate_val.endswith("k"):
                bitrate_numeric = int(bitrate_val.rstrip("k")) * 1000
            else:
                try:
                    bitrate_numeric = int(bitrate_val)
                    if bitrate_numeric < 1000:
                        bitrate_numeric = bitrate_numeric * 1000
                except ValueError:
                    bitrate_numeric = 128000

            bitrate_str = f"{bitrate_numeric // 1000}k"

            # Check safety
            exports_dir = self.context.artifact_store.exports_dir.resolve()
            source_path = Path(audio_path_str).resolve(strict=True)
            if not _path_is_within(source_path, exports_dir):
                raise ValueError("Source audio file must be inside the exports directory.")
            if not source_path.is_file():
                raise ValueError("Source audio file does not exist.")

            # Compile sanitized filename
            import re
            import shutil
            import subprocess
            from urllib.parse import quote

            if custom_filename:
                sanitized_name = re.sub(r"[^\w\s-]", "", custom_filename).strip()
                sanitized_name = re.sub(r"[-\s]+", "-", sanitized_name)
            else:
                sanitized_name = source_path.stem

            if not sanitized_name:
                sanitized_name = "podcast-episode"

            output_filename = f"{sanitized_name}.{target_format}"
            # Keep the delivery file next to the WAV take and overwrite on repeat export.
            target_path = source_path.parent / output_filename
            if target_path.resolve() == source_path:
                audio_url = f"/api/v1/artifacts/audio?path={quote(str(source_path))}"
                self._send_bridge_envelope(
                    success_envelope(
                        {
                            "audio_url": audio_url,
                            "file_name": source_path.name,
                            "audio_path": str(source_path),
                        },
                        operation="export_podcast_audio",
                    ),
                    origin=origin,
                )
                return

            # Run encoding process
            if target_format == "wav":
                shutil.copy2(source_path, target_path)
            else:
                ffmpeg_bin = shutil.which("ffmpeg")
                if ffmpeg_bin:
                    codec = "libmp3lame" if target_format == "mp3" else "aac"
                    cmd = [
                        ffmpeg_bin,
                        "-y",
                        "-i",
                        str(source_path),
                        "-codec:a",
                        codec,
                        "-b:a",
                        bitrate_str,
                        str(target_path),
                    ]
                    try:
                        subprocess.run(cmd, check=True, capture_output=True, text=True)
                    except subprocess.CalledProcessError as exc:
                        error_detail = (exc.stderr or exc.stdout or "").strip()
                        raise RuntimeError(f"FFmpeg conversion failed: {error_detail}")
                else:
                    afconvert_bin = shutil.which("afconvert")
                    if afconvert_bin and target_format == "m4a":
                        cmd = [
                            afconvert_bin,
                            "-f",
                            "m4af",
                            "-d",
                            "aac",
                            "-b",
                            str(bitrate_numeric),
                            str(source_path),
                            str(target_path),
                        ]
                        try:
                            subprocess.run(cmd, check=True, capture_output=True, text=True)
                        except subprocess.CalledProcessError as exc:
                            error_detail = (exc.stderr or exc.stdout or "").strip()
                            raise RuntimeError(f"afconvert conversion failed: {error_detail}")
                    else:
                        if target_format == "mp3":
                            raise RuntimeError(
                                "FFmpeg is required to export to MP3 on this system. "
                                "Please install FFmpeg (for example, 'brew install ffmpeg') and try again."
                            )
                        else:
                            raise RuntimeError(
                                "Neither FFmpeg nor afconvert is available on this system to encode M4A. "
                                "Please install FFmpeg to enable audio compression."
                            )

            audio_url = f"/api/v1/artifacts/audio?path={quote(str(target_path))}"

            self._send_bridge_envelope(
                success_envelope(
                    {
                        "audio_url": audio_url,
                        "file_name": output_filename,
                        "audio_path": str(target_path),
                    },
                    operation="export_podcast_audio",
                ),
                origin=origin,
            )
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
            self.context.store.save_session(project.session)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="rename_session"), origin=origin)
            return
        if self.command == "PUT" and suffix == "/source":
            self._send_bridge_envelope(
                self.context.update_source_payload(session_id, body),
                origin=origin,
            )
            return
        if self.command == "POST" and suffix == ":delete":
            project = self.context.store.load_project(session_id)
            if project.session.is_deleted():
                raise ValueError("Session is already deleted.")
            project.session.soft_delete()
            self.context.store.save_session(project.session)
            self._notify_memory_session_event(session_id, deleted=True)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="delete_session"), origin=origin)
            return
        if self.command == "POST" and suffix == ":restore":
            project = self.context.store.load_project(session_id)
            if not project.session.is_deleted():
                raise ValueError("Session is not deleted.")
            project.session.restore()
            self.context.store.save_session(project.session)
            self._notify_memory_session_event(session_id, deleted=False)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="restore_session"), origin=origin)
            return
        if self.command == "POST" and suffix == ":memory-mode":
            mode = str(body.get("mode") or "").strip()
            if mode not in ("enabled", "disabled"):
                raise ValueError("Field 'mode' must be 'enabled' or 'disabled'.")
            project = self.context.store.load_project(session_id)
            was_disabled = not project.session.memory_enabled()
            project.session.set_memory_mode(mode)
            if mode == "enabled" and was_disabled:
                # Re-enabling never backfills the closed period: jump the cursor
                # to the latest user turn so only new turns are processed.
                transcript = project.transcript
                if transcript and transcript.turns:
                    user_turns = [t for t in transcript.turns if t.speaker == Speaker.USER]
                    if user_turns:
                        project.session.advance_memory_cursor(user_turns[-1].turn_id)
            self.context.store.save_session(project.session)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="set_session_memory_mode"), origin=origin)
            return
        if self.command == "GET" and suffix == "/memory-candidates":
            memory = self.context.get_memory_service()
            session = self.context.store.load_session(session_id)
            candidates = [
                serialize_memory_entry(entry)
                for entry in memory.list_authorization_candidates(session)
            ]
            self._send_bridge_envelope(
                success_envelope({"candidates": candidates}, operation="list_memory_candidates"),
                origin=origin,
            )
            return
        if self.command == "POST" and suffix == "/memory:authorize":
            memory_id = str(body.get("memory_id") or "").strip()
            if not memory_id:
                raise ValueError("Field 'memory_id' is required.")
            memory = self.context.get_memory_service()
            memory.authorize(session_id, memory_id)
            project = self.context.store.load_project(session_id)
            self._send_bridge_envelope(
                success_envelope({"project": serialize_project(project)}, operation="authorize_memory"),
                origin=origin,
            )
            return
        if self.command == "POST" and suffix == "/interview:start":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            result = self.context.orchestrator.start_interview(session_id)
            self._send_bridge_envelope(success_envelope(serialize_turn_result(result), operation="start_interview"), origin=origin)
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
        if self.command == "POST" and suffix.startswith("/scripts/") and suffix.endswith("/speaker-reference:select"):
            script_id = suffix.removeprefix("/scripts/").removesuffix("/speaker-reference:select").strip("/")
            reference_id = str(body.get("speaker_reference_id") or "").strip()
            if not reference_id:
                raise ValueError("Field 'speaker_reference_id' is required.")
            reference_store = self.context.get_speaker_reference_store()
            reference = reference_store.get_reference(reference_id)
            project = self.context.audio_rendering.select_speaker_reference(
                session_id,
                script_id=script_id,
                reference=reference,
            )
            reference_store.mark_used(reference_id)
            self._send_bridge_envelope(
                success_envelope({"project": serialize_project(project)}, operation="select_speaker_reference"),
                origin=origin,
            )
            return
        if (
            self.command == "POST"
            and suffix.startswith("/scripts/")
            and "/audio/segments/" in suffix
            and suffix.endswith(":regenerate")
        ):
            route = suffix.removeprefix("/scripts/").removesuffix(":regenerate")
            script_id, marker, segment_id = route.partition("/audio/segments/")
            if not marker or not script_id.strip() or not segment_id.strip():
                raise ValueError("Invalid audio segment regeneration route.")
            self._send_bridge_envelope(
                self.context.start_regenerate_audio_window(
                    session_id,
                    script_id=script_id.strip(),
                    target_segment_id=segment_id.strip(),
                    expected_plan_id=str(body.get("speech_plan_id") or ""),
                    expected_render_id=str(body.get("render_manifest_id") or ""),
                ),
                origin=origin,
            )
            return
        if self.command == "DELETE" and suffix == "/audio":
            script_id = (query.get("script_id") or [""])[-1].strip()
            project = self.context.audio_rendering.delete_generated_audio(session_id, script_id=script_id)
            self._send_bridge_envelope(
                success_envelope({"project": serialize_project(project)}, operation="delete_generated_audio"),
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
            raw_model_id = str(body.get("model_id") or "").strip()
            model_id = resolve_voice_model_id(raw_model_id) if raw_model_id else ""
            script_id = str(body.get("script_id") or "").strip()
            settings_payload = body.get("voice_settings")
            settings = voice_settings_from_payload(settings_payload) if isinstance(settings_payload, dict) else None
            require_speaker_reference = _body_flag(body, "require_speaker_reference")
            self._send_bridge_envelope(
                self.context.start_render_audio(
                    session_id,
                    script_id=script_id,
                    override_provider=provider,
                    override_model=model_id,
                    settings=settings,
                    require_speaker_reference=require_speaker_reference,
                ),
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
        builtin_reference_dir = Path(__file__).resolve().parents[1] / "assets" / "speaker-references"
        audio_path = Path(raw_path).resolve(strict=True)
        if not _path_is_within(audio_path, exports_dir) and not _path_is_within(audio_path, builtin_reference_dir):
            raise ValueError("Artifact audio path must be inside the exports directory or packaged speaker reference assets.")
        if not audio_path.is_file():
            raise ValueError("Artifact audio path does not point to a file.")

        content_type = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".mp4": "audio/mp4",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
            ".flac": "audio/flac",
        }.get(audio_path.suffix.lower(), "application/octet-stream")
        self._send_binary(HTTPStatus.OK, audio_path.read_bytes(), content_type=content_type, origin=origin)

    def _delete_artifact_audio(self, query: dict[str, list[str]], *, origin: str | None) -> None:
        raw_path = (query.get("path") or [""])[-1].strip()
        if not raw_path:
            raise ValueError("Query parameter 'path' is required.")
        target = Path(raw_path).expanduser().resolve()
        previews_dir = (self.context.artifact_store.exports_dir / "_previews").resolve()
        if not _path_is_within(target, previews_dir):
            raise ValueError(
                "Only disposable Voice Studio preview audio can be deleted through this endpoint."
            )
        deleted = self.context.artifact_store.delete_export_file(raw_path)
        self._send_bridge_envelope(
            success_envelope(
                {
                    "path": raw_path,
                    "deleted": deleted,
                },
                operation="delete_artifact_audio",
            ),
            origin=origin,
        )

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

    def _is_multipart_request(self) -> bool:
        return self.headers.get("Content-Type", "").lower().startswith("multipart/form-data")

    def _read_multipart_form(self) -> tuple[dict[str, str], dict[str, MultipartFile]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("Multipart form data is required.")
        content_length = int(self.headers.get("Content-Length") or "0")
        if content_length <= 0:
            raise ValueError("Multipart request body is required.")
        raw = self.rfile.read(content_length)
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw
        )
        fields: dict[str, str] = {}
        files: dict[str, MultipartFile] = {}
        if not message.is_multipart():
            raise ValueError("Multipart request body is invalid.")
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_filename()
            content = part.get_payload(decode=True) or b""
            if filename:
                files[str(name)] = MultipartFile(
                    filename=str(filename),
                    content_type=str(part.get_content_type() or "application/octet-stream"),
                    content=content,
                )
            else:
                fields[str(name)] = content.decode(part.get_content_charset() or "utf-8").strip()
        return fields, files

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
        if "/interview:reply-stream" in path:
            return "submit_reply"
        if "/interview:start" in path:
            return "start_interview"
        if "/interview:finish" in path:
            return "request_finish"
        if "/script:generate" in path:
            return "generate_script"
        if path.endswith("/source"):
            return "update_episode_source"
        if "/audio:render" in path:
            return "render_audio"
        if path == "/api/v1/voice-studio/presets":
            return "list_voice_presets"
        if path == "/api/v1/voice-studio/preview":
            return "render_voice_preview"
        if path == "/api/v1/speaker-references":
            if self.command == "POST":
                return "create_speaker_reference"
            return "list_speaker_references"
        if path.startswith("/api/v1/speaker-references/"):
            if self.command == "DELETE":
                return "delete_speaker_reference"
            return "update_speaker_reference"
        if "/speaker-reference:select" in path:
            return "select_speaker_reference"
        if "/audio/segments/" in path and path.endswith(":regenerate"):
            return "regenerate_audio_window"
        if path == "/api/v1/artifacts/audio":
            return "serve_artifact_audio"
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
        if path == "/api/v1/config/llm/test":
            return "test_llm_connection"
        if path == "/api/v1/config/llm/auth:start":
            return "start_llm_provider_login"
        if path == "/api/v1/config/llm/status":
            return "show_llm_provider_status"
        if path == "/api/v1/config/tts/test":
            return "test_tts_connection"
        if path == "/api/v1/config/llm/preflight":
            return "check_llm_config"
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
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,PUT,DELETE,OPTIONS")
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


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def install_runtime_stop_handlers(
    *,
    on_stop: Callable[[], None],
) -> Callable[[], None]:
    """Install SIGTERM/SIGINT handlers so hard kills still reclaim download children.

    Default SIGTERM exits without running ``finally``, which is the root cause of
    orphaned ``download_tts_model.py`` processes after ``run-dev-all`` restarts.
    """

    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    stopping = threading.Event()

    def _handle_stop(_signum: int, _frame: object | None) -> None:
        if stopping.is_set():
            return
        stopping.set()
        try:
            on_stop()
        except Exception:
            # Never raise from a signal handler; process exit still proceeds.
            pass

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    def restore() -> None:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)

    return restore


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
    speaker_reference_store = SpeakerReferenceStore(config.data_dir, artifact_store)
    request_state_store = RequestStateStore(config.data_dir)
    memory_service = MemoryService(config.data_dir, store, config_store)
    orchestrator = InterviewOrchestrator(store, config_store, memory_service)
    script_generation = ScriptGenerationService(store, config_store, memory_service)
    audio_rendering = AudioRenderingService(store, config_store, artifact_store)

    store.bootstrap()
    config_store.bootstrap()
    artifact_store.bootstrap()
    speaker_reference_store.bootstrap()
    request_state_store.bootstrap()
    memory_service.bootstrap()
    request_state_store.fail_orphaned_active_states(
        prefix="download_model:",
        message="Download interrupted by a runtime restart. Retry to resume.",
        build_request_state=build_request_state,
    )
    request_state_store.fail_orphaned_active_states(
        prefix="render_audio:",
        message="Render interrupted by a runtime restart. Try generating again.",
        build_request_state=build_request_state,
    )
    for session in store.list_sessions():
        if session.state == SessionState.AUDIO_RENDERING:
            store.release_stuck_audio_render(
                session.session_id,
                message="Render interrupted by a runtime restart. Try generating again.",
            )

    context = RuntimeContext(
        cwd=cwd,
        config=config,
        store=store,
        config_store=config_store,
        artifact_store=artifact_store,
        speaker_reference_store=speaker_reference_store,
        request_state_store=request_state_store,
        orchestrator=orchestrator,
        script_generation=script_generation,
        audio_rendering=audio_rendering,
        memory_service=memory_service,
        runtime_token=runtime_token or "",
        bootstrap_nonce=bootstrap_nonce,
        bootstrap_created_at=time.time(),
        runtime_started_at=time.time(),
        runtime_build_token=uuid.uuid4().hex,
        allowed_origins=_normalize_allowed_origins(allowed_origins),
    )

    server = RuntimeHttpServer((host, port), context)
    stop_lock = threading.Lock()
    stop_started = False

    def request_stop() -> None:
        nonlocal stop_started
        with stop_lock:
            if stop_started:
                return
            stop_started = True
        # Reclaim download process groups before the runtime PID disappears.
        context.shutdown_download_processes()
        threading.Thread(target=server.shutdown, daemon=True, name="runtime-stop").start()

    restore_signals = install_runtime_stop_handlers(on_stop=request_stop)
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
        request_stop()
    finally:
        restore_signals()
        context.shutdown_download_processes()
        memory_service.shutdown()
        server.server_close()
    return 0
