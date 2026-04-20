from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.config import AppConfig
from app.domain.project import SessionProject
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import TranscriptRecord
from app.models_catalog import build_models_status, delete_voice_model, download_voice_model
from app.orchestration.audio_rendering import AudioRenderingService, AudioRenderProgress
from app.orchestration.interview_service import InterviewOrchestrator, InterviewTurnResult
from app.orchestration.script_generation import (
    ScriptGenerationResult,
    ScriptGenerationService,
    build_generation_context,
)
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


def build_request_state(
    *,
    operation: str,
    phase: str,
    progress_percent: float,
    message: str,
    run_token: str | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {
        "operation": operation,
        "phase": phase,
        "progress_percent": progress_percent,
        "message": message,
    }
    if run_token:
        state["run_token"] = run_token
    return state


def progress_from_request_state(state: dict[str, object] | None, default: float = 0.0) -> float:
    if not isinstance(state, dict):
        return default
    value = state.get("progress_percent")
    if isinstance(value, (int, float)):
        return float(min(100.0, max(0.0, value)))
    return default


def success_envelope(
    data: dict[str, object],
    *,
    operation: str,
    message: str = "completed",
    phase: str = "succeeded",
    progress_percent: float = 100.0,
    run_token: str | None = None,
) -> dict[str, object]:
    payload = dict(data)
    payload["request_state"] = build_request_state(
        operation=operation,
        phase=phase,
        progress_percent=progress_percent,
        message=message,
        run_token=run_token,
    )
    return {"ok": True, "data": payload}


def error_envelope(
    *,
    operation: str,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    phase: str = "failed",
    progress_percent: float = 0.0,
) -> dict[str, object]:
    request_state = build_request_state(
        operation=operation,
        phase=phase,
        progress_percent=progress_percent,
        message=message,
    )
    payload_details = dict(details or {})
    payload_details["request_state"] = request_state
    return {
        "ok": False,
        "request_state": request_state,
        "error": {
            "code": code,
            "message": message,
            "details": payload_details,
        },
    }


def serialize_project(project: SessionProject) -> dict[str, object]:
    return {
        "session": project.session.to_dict(),
        "transcript": project.transcript.to_dict() if project.transcript else None,
        "script": project.script.to_dict() if project.script else None,
        "artifact": project.artifact.to_dict() if project.artifact else None,
    }


def serialize_turn_result(result: InterviewTurnResult) -> dict[str, object]:
    return {
        "project": serialize_project(result.project),
        "readiness": {
            "topic_context": result.readiness.topic_context,
            "core_viewpoint": result.readiness.core_viewpoint,
            "example_or_detail": result.readiness.example_or_detail,
            "conclusion": result.readiness.conclusion,
            "is_ready": result.readiness.is_ready,
            "missing_dimensions": result.readiness.missing_dimensions(),
        },
        "prompt_input": result.prompt_input.to_dict(),
        "next_question": result.next_question,
        "ai_can_finish": result.ai_can_finish,
    }


def serialize_generation_result(result: ScriptGenerationResult) -> dict[str, object]:
    project = result.project
    payload: dict[str, object] = {
        "project": serialize_project(project),
        "provider": result.provider,
        "model": result.model,
        "generation_context": build_generation_context(project),
    }
    if project.script is not None:
        payload["script_id"] = project.script.script_id
    return payload


def serialize_script_revisions(project: SessionProject) -> list[dict[str, object]]:
    if project.script is None:
        return []
    revisions: list[dict[str, object]] = []
    for revision in project.script.list_revisions():
        revisions.append(
            {
                "revision_id": revision.revision_id,
                "session_id": project.session.session_id,
                "content": revision.final or revision.draft,
                "kind": revision.reason,
                "label": revision.reason.replace("_", " "),
                "created_at": revision.created_at,
            }
        )
    return revisions


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
    allowed_origins: frozenset[str]
    task_lock: threading.Lock = field(default_factory=threading.Lock)
    active_tasks: dict[str, threading.Thread] = field(default_factory=dict)
    bootstrap_nonce_used: bool = False

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

    def start_render_audio(self, session_id: str, *, override_provider: str = "") -> dict[str, object]:
        project = self.store.load_project(session_id)
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

                def raise_render_cancelled(
                    message: str,
                    *,
                    default_progress: float,
                    source_error: Exception | None = None,
                ) -> None:
                    cancel_progress = progress.current_progress(default=default_progress)
                    progress.save_cancelled(progress_percent=cancel_progress, message=message)
                    self.request_state_store.clear_cancel_request(task_id)
                    if source_error is None:
                        raise BridgeTaskCancelledError(
                            message,
                            operation="render_audio",
                            progress_percent=cancel_progress,
                        )
                    raise BridgeTaskCancelledError(
                        message,
                        operation="render_audio",
                        progress_percent=cancel_progress,
                    ) from source_error

                def fail_render(message: str) -> None:
                    progress.save_failed(message=message)
                    self.request_state_store.clear_cancel_request(task_id)

                try:
                    self.audio_rendering.render_audio_with_cancellation(
                        session_id,
                        override_provider=override_provider,
                        should_cancel=progress.should_cancel,
                        on_progress=on_progress,
                    )
                except TaskCancellationRequested as exc:
                    raise_render_cancelled(str(exc), default_progress=10.0)
                except Exception as exc:  # pragma: no cover - exercised by integration tests
                    current_phase = progress.current_phase()
                    if self.request_state_store.is_cancel_requested(task_id) or current_phase == "cancelling":
                        raise_render_cancelled(
                            f"Audio rendering cancelled for session {session_id}.",
                            default_progress=10.0,
                            source_error=exc,
                        )
                    fail_render(str(exc))
                else:
                    progress.save_finalizing(
                        progress_percent=99.0,
                        message=f"Finalizing rendered artifacts for session {session_id}...",
                    )
                    saved_succeeded = progress.save_succeeded(
                        message=f"Audio render finished for session {session_id}.",
                    )
                    if not saved_succeeded:
                        current_phase = progress.current_phase()
                        if current_phase == "cancelling" or self.request_state_store.is_cancel_requested(task_id):
                            raise_render_cancelled(
                                f"Audio rendering cancelled for session {session_id}.",
                                default_progress=99.0,
                            )
                        fail_render(f"Unable to finalize audio render for session {session_id}.")
                    self.request_state_store.clear_cancel_request(task_id)
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

                def raise_download_cancelled(
                    message: str,
                    *,
                    default_progress: float,
                    source_error: Exception | None = None,
                ) -> None:
                    cancel_progress = progress.current_progress(default=default_progress)
                    progress.save_cancelled(progress_percent=cancel_progress, message=message)
                    self.request_state_store.clear_cancel_request(task_id)
                    if source_error is None:
                        raise BridgeTaskCancelledError(
                            message,
                            operation="download_model",
                            progress_percent=cancel_progress,
                        )
                    raise BridgeTaskCancelledError(
                        message,
                        operation="download_model",
                        progress_percent=cancel_progress,
                    ) from source_error

                def fail_download(message: str) -> None:
                    progress.save_failed(message=message)
                    self.request_state_store.clear_cancel_request(task_id)

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
                        on_output_line=on_download_output_line,
                        should_cancel=progress.should_cancel,
                    )
                except TaskCancellationRequested as exc:
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    raise_download_cancelled(str(exc), default_progress=5.0)
                except Exception as exc:  # pragma: no cover - exercised by integration tests
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    if self.request_state_store.is_cancel_requested(task_id) or progress.current_phase() == "cancelling":
                        raise_download_cancelled(
                            f"Model {model_name} download cancelled.",
                            default_progress=5.0,
                            source_error=exc,
                        )
                    fail_download(str(exc))
                else:
                    progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                    progress.save_finalizing(
                        progress_percent=98.0,
                        message=f"Finalizing model {model_name}...",
                    )
                    saved_succeeded = progress.save_succeeded(message=f"Model {model_name} is ready.")
                    if not saved_succeeded and (
                        self.request_state_store.is_cancel_requested(task_id)
                        or progress.current_phase() == "cancelling"
                    ):
                        raise_download_cancelled(
                            f"Model {model_name} download cancelled.",
                            default_progress=98.0,
                        )
                    if not saved_succeeded:
                        fail_download(f"Unable to finalize download state for {model_name}.")
                    self.request_state_store.clear_cancel_request(task_id)
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
            self._send_json(HTTPStatus.OK, {"ok": True, "status": "ready", "service": "aodcast-python-core-http"})
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
                    message=str(exc),
                ),
                origin=origin,
            )
        except Exception as exc:  # pragma: no cover - exercised by integration tests
            self._send_bridge_envelope(
                error_envelope(
                    operation=self._infer_operation(path),
                    code="python_core_error",
                    message=str(exc),
                    details={"exception_type": exc.__class__.__name__},
                ),
                origin=origin,
            )

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
        if self.command == "POST" and path.startswith("/api/v1/models/") and path.endswith(":download"):
            model_name = path.removeprefix("/api/v1/models/").removesuffix(":download")
            self._send_bridge_envelope(self.context.start_download_model(model_name), origin=origin)
            return
        if self.command == "POST" and path.startswith("/api/v1/models/") and path.endswith(":delete"):
            model_name = path.removeprefix("/api/v1/models/").removesuffix(":delete")
            self._send_bridge_envelope(
                success_envelope(delete_voice_model(self.context.cwd, model_name), operation="delete_model"),
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
            self.context.request_state_store.request_cancel(task_id)
            cancelling_state = build_request_state(
                operation=operation,
                phase="cancelling",
                progress_percent=progress_percent,
                message=f"Cancellation requested for {task_id}.",
            )
            self.context.request_state_store.save(task_id, cancelling_state)
            self._send_bridge_envelope(
                success_envelope(
                    {"task_id": task_id, "task_state": cancelling_state},
                    operation="cancel_task",
                    message="cancellation_requested",
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
        if self.command == "PUT" and suffix.startswith("/scripts/") and suffix.endswith("/final"):
            rest = suffix.removeprefix("/scripts/").removesuffix("/final").strip("/")
            final_text = str(body.get("final_text") or "")
            if not final_text.strip():
                raise ValueError("Field 'final_text' is required.")
            project = self.context.store.load_project_for_script(session_id, rest)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            project.script.save_final(final_text)
            project.session.transition(SessionState.SCRIPT_EDITED)
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="save_script"), origin=origin)
            return
        if self.command == "GET" and suffix.startswith("/scripts/") and "/revisions" in suffix:
            # /scripts/{id}/revisions
            rest = suffix.removeprefix("/scripts/").strip("/")
            if not rest.endswith("/revisions"):
                raise ValueError(f"Unknown route: {path}")
            script_id = rest[: -len("/revisions")].strip("/")
            project = self.context.store.load_project_for_script(session_id, script_id)
            ensure_session_is_active(project)
            if project.script is None:
                raise ValueError("Cannot list revisions because no script record exists.")
            self._send_bridge_envelope(
                success_envelope(
                    {"session_id": session_id, "script_id": script_id, "revisions": serialize_script_revisions(project)},
                    operation="list_script_revisions",
                ),
                origin=origin,
            )
            return
        if self.command == "POST" and suffix.startswith("/scripts/") and "/revisions/" in suffix and suffix.endswith(":rollback"):
            rest = suffix.removeprefix("/scripts/").strip("/")
            # {script_id}/revisions/{rev}:rollback
            mid, _, revpart = rest.partition("/revisions/")
            revision_id = revpart.removesuffix(":rollback")
            project = self.context.store.load_project_for_script(session_id, mid)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            project.script.rollback_to_revision(revision_id)
            project.session.transition(SessionState.SCRIPT_EDITED)
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="rollback_script_revision"), origin=origin)
            return
        if self.command == "POST" and suffix.startswith("/scripts/") and suffix.endswith(":delete"):
            script_id = suffix.removeprefix("/scripts/").removesuffix(":delete").strip("/")
            project = self.context.store.load_project_for_script(session_id, script_id)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            if project.script.is_deleted():
                raise ValueError("Script is already deleted.")
            project.script.soft_delete()
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="delete_script"), origin=origin)
            return
        if self.command == "POST" and suffix.startswith("/scripts/") and suffix.endswith(":restore"):
            script_id = suffix.removeprefix("/scripts/").removesuffix(":restore").strip("/")
            project = self.context.store.load_project_for_script(session_id, script_id)
            ensure_session_is_active(project)
            if project.script is None:
                raise ValueError("Cannot restore script because no script record exists.")
            if not project.script.is_deleted():
                raise ValueError("Script is not deleted.")
            project.script.restore()
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="restore_script"), origin=origin)
            return
        if self.command == "POST" and suffix == "/script:generate":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            result = self.context.script_generation.generate_draft(session_id)
            self._send_bridge_envelope(success_envelope(serialize_generation_result(result), operation="generate_script"), origin=origin)
            return
        if self.command == "POST" and suffix == "/audio:render":
            provider = str(body.get("provider_override") or "")
            self._send_bridge_envelope(self.context.start_render_audio(session_id, override_provider=provider), origin=origin)
            return
        if self.command == "PUT" and suffix == "/script/final":
            final_text = str(body.get("final_text") or "")
            if not final_text.strip():
                raise ValueError("Field 'final_text' is required.")
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            project.script.save_final(final_text)
            project.session.transition(SessionState.SCRIPT_EDITED)
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="save_script"), origin=origin)
            return
        if self.command == "POST" and suffix == "/script:delete":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            if project.script is None:
                raise ValueError("Cannot delete script because no script record exists.")
            if project.script.is_deleted():
                raise ValueError("Script is already deleted.")
            project.script.soft_delete()
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="delete_script"), origin=origin)
            return
        if self.command == "POST" and suffix == "/script:restore":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            if project.script is None:
                raise ValueError("Cannot restore script because no script record exists.")
            if not project.script.is_deleted():
                raise ValueError("Script is not deleted.")
            project.script.restore()
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="restore_script"), origin=origin)
            return
        if self.command == "GET" and suffix == "/script/revisions":
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            if project.script is None:
                raise ValueError("Cannot list revisions because no script record exists.")
            self._send_bridge_envelope(
                success_envelope({"session_id": session_id, "revisions": serialize_script_revisions(project)}, operation="list_script_revisions"),
                origin=origin,
            )
            return
        if self.command == "POST" and suffix.startswith("/script/revisions/") and suffix.endswith(":rollback"):
            revision_id = suffix.removeprefix("/script/revisions/").removesuffix(":rollback")
            project = self.context.store.load_project(session_id)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            project.script.rollback_to_revision(revision_id)
            project.session.transition(SessionState.SCRIPT_EDITED)
            self.context.store.save_project(project)
            self._send_bridge_envelope(success_envelope({"project": serialize_project(project)}, operation="rollback_script_revision"), origin=origin)
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
        if path.startswith("/api/v1/tasks/") and path.endswith(":cancel"):
            return "cancel_task"
        if path.startswith("/api/v1/tasks/"):
            return "show_task_state"
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
        resolved_status = status or self._status_for_payload(payload)
        self._send_json(resolved_status, payload, origin=origin)

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
