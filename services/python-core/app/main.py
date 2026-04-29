from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from app.config import AppConfig
from app.cli.parser import build_parser
from app.api.bridge_envelope import build_request_state, progress_from_request_state
from app.api.serializers import (
    serialize_audio_result,
    serialize_generation_result,
    serialize_project,
    serialize_script_revisions,
    serialize_turn_result,
    serialize_voice_take_result,
)
from app.api.http_runtime import serve_http
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import TranscriptRecord
from app.domain.voice_studio import STANDARD_PREVIEW_TEXT, STYLE_PRESETS, VOICE_PRESETS
from app.orchestration.audio_rendering import AudioRenderingService, VoiceRenderSettings
from app.orchestration.interview_service import InterviewOrchestrator, InterviewTurnResult
from app.orchestration.script_generation import ScriptGenerationService
from app.models_catalog import (
    build_models_status,
    delete_voice_model,
    download_voice_model,
    migrate_model_storage,
    model_storage_status,
    reset_model_storage,
)
from app.providers.llm.factory import validate_llm_provider
from app.providers.tts_api.factory import validate_tts_provider
from app.runtime.long_task_state import LongTaskStateManager
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability
from app.providers.tts_local_mlx.presets import DEFAULT_QWEN3_TTS_MODEL
from app.runtime.request_state_store import RequestStateStore
from app.runtime.task_cancellation import TaskCancellationRequested
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore

DOWNLOAD_PROGRESS_MARKER = "AODCAST_PROGRESS"

TASK_TERMINAL_PHASES = {"succeeded", "failed", "cancelled"}


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



def create_project(topic: str, intent: str, *, demo: bool = False) -> SessionProject:
    session = SessionRecord(topic=topic, creation_intent=intent)
    transcript = TranscriptRecord(session_id=session.session_id)
    script = None
    if demo:
        script = ScriptRecord(
            session_id=session.session_id,
            draft="Draft script pending real generation.",
            final="",
        )
    artifact = ArtifactRecord(
        session_id=session.session_id,
        transcript_path=f"sessions/{session.session_id}/transcript.json",
        audio_path="",
        provider="",
    )
    return SessionProject(
        session=session,
        transcript=transcript,
        script=script,
        artifact=artifact,
    )


def ensure_session_is_active(project: SessionProject) -> None:
    if project.session.is_deleted():
        raise ValueError("Session is deleted. Restore it before continuing.")


def ensure_script_is_active(project: SessionProject) -> None:
    if project.script is None:
        raise ValueError("Cannot continue without a script record.")
    if project.script.is_deleted():
        raise ValueError("Script is deleted. Restore it before continuing.")



def load_final_script_text(args: argparse.Namespace) -> str:
    if args.script_final_file:
        return Path(args.script_final_file).read_text(encoding="utf-8")
    return args.script_final_text


def infer_operation(args: argparse.Namespace) -> str:
    if args.serve_http:
        return "http_runtime"
    if args.list_projects:
        return "list_projects"
    if args.create_session or args.create_demo_session:
        return "create_session"
    if args.show_session:
        return "show_session"
    if args.rename_session:
        return "rename_session"
    if args.delete_session:
        return "delete_session"
    if args.restore_session:
        return "restore_session"
    if args.save_script:
        return "save_script"
    if args.delete_script:
        return "delete_script"
    if args.restore_script:
        return "restore_script"
    if args.list_script_revisions:
        return "list_script_revisions"
    if args.rollback_script_revision:
        return "rollback_script_revision"
    if args.start_interview:
        return "start_interview"
    if args.reply_session:
        return "submit_reply"
    if args.finish_session:
        return "request_finish"
    if args.generate_script:
        return "generate_script"
    if args.render_audio:
        return "render_audio"
    if args.list_voice_presets:
        return "list_voice_presets"
    if args.render_voice_preview:
        return "render_voice_preview"
    if args.render_voice_take:
        return "render_voice_take"
    if args.set_final_voice_take:
        return "set_final_voice_take"
    if args.show_tts_config:
        return "show_tts_config"
    if args.configure_tts_provider:
        return "configure_tts_provider"
    if args.show_llm_config:
        return "show_llm_config"
    if args.configure_llm_provider:
        return "configure_llm_provider"
    if args.show_local_tts_capability:
        return "show_local_tts_capability"
    if args.list_models_status:
        return "list_models_status"
    if args.show_model_storage:
        return "show_model_storage"
    if args.migrate_model_storage.strip():
        return "migrate_model_storage"
    if args.reset_model_storage:
        return "reset_model_storage"
    if args.download_model.strip():
        return "download_model"
    if args.delete_model.strip():
        return "delete_model"
    if args.show_task_state.strip():
        return "show_task_state"
    if args.cancel_task.strip():
        return "cancel_task"
    # Referenced by HTTP-only routes; kept for bridge contract parity with desktop httpBridge.
    if False:  # pragma: no cover
        return "show_latest_script"
    if False:  # pragma: no cover
        return "show_script"
    if False:  # pragma: no cover
        return "list_scripts"
    if False:  # pragma: no cover
        return "delete_generated_audio"
    if False:  # pragma: no cover
        return "delete_artifact_audio"
    if False:  # pragma: no cover
        return "delete_voice_take"
    return "bridge_ping"



def output_payload(
    args: argparse.Namespace,
    payload: dict[str, object],
    *,
    operation: str | None = None,
    message: str = "completed",
) -> int:
    request_state = build_request_state(
        operation=operation or infer_operation(args),
        phase="succeeded",
        progress_percent=100.0,
        message=message,
    )
    enriched_payload = dict(payload)
    enriched_payload["request_state"] = request_state
    print(json.dumps(enriched_payload))
    return 0


def output_error(
    args: argparse.Namespace,
    *,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    operation: str | None = None,
    phase: str = "failed",
    progress_percent: float = 0.0,
) -> int:
    request_state = build_request_state(
        operation=operation or infer_operation(args),
        phase=phase,
        progress_percent=progress_percent,
        message=message,
    )
    print(message, file=sys.stderr)
    return 1


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.from_cwd(args.cwd)
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

    if args.serve_http:
        return serve_http(
            cwd=Path(args.cwd),
            host=args.host,
            port=args.port,
            runtime_token=args.runtime_token.strip() or None,
            allowed_origins=args.allowed_origins.strip() or None,
            bootstrap_nonce=args.bootstrap_nonce.strip() or None,
        )

    print(f"Aodcast Python core ready at: {config.data_dir}")

    try:
        if args.list_projects:
            projects = sorted(
                store.list_projects(
                    include_deleted=args.list_projects_include_deleted,
                    search_query=args.list_projects_query,
                ),
                key=lambda project: project.session.updated_at,
                reverse=True,
            )
            return output_payload(args, {"projects": [serialize_project(project) for project in projects]})

        if args.create_session or args.create_demo_session:
            project = create_project(args.topic, args.intent, demo=args.create_demo_session)
            store.save_project(project)
            if args.create_demo_session:
                print(f"Created demo session {project.session.session_id} at {store.session_dir(project.session.session_id)}")
                return 0
            return output_payload(args, {"project": serialize_project(project)})

        if args.rename_session:
            new_topic = args.session_topic.strip()
            if not new_topic:
                raise ValueError("--session-topic is required when using --rename-session")
            project = store.load_project(args.rename_session)
            ensure_session_is_active(project)
            project.session.rename_topic(new_topic)
            store.save_project(project)
            return output_payload(args, {"project": serialize_project(project)})

        if args.delete_session:
            project = store.load_project(args.delete_session)
            if project.session.is_deleted():
                raise ValueError("Session is already deleted.")
            project.session.soft_delete()
            store.save_project(project)
            return output_payload(args, {"project": serialize_project(project)})

        if args.restore_session:
            project = store.load_project(args.restore_session)
            if not project.session.is_deleted():
                raise ValueError("Session is not deleted.")
            project.session.restore()
            store.save_project(project)
            return output_payload(args, {"project": serialize_project(project)})

        if args.save_script:
            final_text = load_final_script_text(args)
            if not final_text.strip():
                raise ValueError("--script-final-text or --script-final-file is required when using --save-script")
            project = store.load_project(args.save_script)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            project.script.save_final(final_text)
            project.session.transition(SessionState.SCRIPT_EDITED)
            store.save_project(project)
            return output_payload(args, {"project": serialize_project(project)})

        if args.delete_script:
            project = store.load_project(args.delete_script)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            if project.script is None:
                raise ValueError("Cannot delete script because no script record exists.")
            if project.script.is_deleted():
                raise ValueError("Script is already deleted.")
            project.script.soft_delete()
            store.save_project(project)
            return output_payload(args, {"project": serialize_project(project)})

        if args.restore_script:
            project = store.load_project(args.restore_script)
            ensure_session_is_active(project)
            if project.script is None:
                raise ValueError("Cannot restore script because no script record exists.")
            if not project.script.is_deleted():
                raise ValueError("Script is not deleted.")
            project.script.restore()
            store.save_project(project)
            return output_payload(args, {"project": serialize_project(project)})

        if args.list_script_revisions:
            project = store.load_project(args.list_script_revisions)
            ensure_session_is_active(project)
            if project.script is None:
                raise ValueError("Cannot list revisions because no script record exists.")
            revisions = serialize_script_revisions(project)
            return output_payload(args, {"session_id": args.list_script_revisions, "revisions": revisions})

        if args.rollback_script_revision:
            if not args.revision_id.strip():
                raise ValueError("--revision-id is required when using --rollback-script-revision")
            project = store.load_project(args.rollback_script_revision)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            project.script.rollback_to_revision(args.revision_id.strip())
            project.session.transition(SessionState.SCRIPT_EDITED)
            store.save_project(project)
            return output_payload(args, {"project": serialize_project(project)})

        if args.configure_llm_provider:
            validate_llm_provider(args.configure_llm_provider)
            llm_config = config_store.load_llm_config()
            llm_config.provider = args.configure_llm_provider
            if args.llm_model is not None:
                llm_config.model = args.llm_model
            if args.llm_base_url is not None:
                llm_config.base_url = args.llm_base_url
            if args.llm_api_key is not None:
                llm_config.api_key = args.llm_api_key
            path = config_store.save_llm_config(llm_config)
            return output_payload(args, {"path": str(path), "llm_config": llm_config.to_dict()})

        if args.configure_tts_provider:
            validate_tts_provider(args.configure_tts_provider)
            tts_config = config_store.load_tts_config()
            tts_config.provider = args.configure_tts_provider
            if args.tts_model is not None:
                if args.configure_tts_provider == "local_mlx" and args.tts_model.strip() == "":
                    tts_config.model = DEFAULT_QWEN3_TTS_MODEL
                else:
                    tts_config.model = args.tts_model
            elif args.configure_tts_provider == "local_mlx" and tts_config.model in {"", "mock-voice"}:
                tts_config.model = DEFAULT_QWEN3_TTS_MODEL
            if args.tts_base_url is not None:
                tts_config.base_url = args.tts_base_url
            if args.tts_api_key is not None:
                tts_config.api_key = args.tts_api_key
            if args.tts_voice is not None:
                tts_config.voice = args.tts_voice
            if args.tts_audio_format is not None:
                tts_config.audio_format = args.tts_audio_format
            if args.tts_local_runtime is not None:
                tts_config.local_runtime = args.tts_local_runtime
            if args.clear_tts_local_model_path:
                tts_config.local_model_path = ""
            if args.tts_local_model_path is not None:
                tts_config.local_model_path = args.tts_local_model_path
            path = config_store.save_tts_config(tts_config)
            return output_payload(args, {"path": str(path), "tts_config": tts_config.to_dict()})

        if args.show_llm_config:
            return output_payload(args, {"llm_config": config_store.load_llm_config().to_dict()})

        if args.show_tts_config:
            return output_payload(args, {"tts_config": config_store.load_tts_config().to_dict()})

        if args.list_models_status:
            models = build_models_status(config_store, Path(args.cwd))
            return output_payload(args, {"models": models})

        if args.show_model_storage:
            return output_payload(
                args,
                {"model_storage": model_storage_status(config_store, Path(args.cwd))},
            )

        if args.reset_model_storage:
            return output_payload(
                args,
                {"model_storage": reset_model_storage(config_store, Path(args.cwd))},
            )

        if args.migrate_model_storage.strip():
            destination = args.migrate_model_storage.strip()
            task_id = "migrate_model_storage"
            progress = LongTaskStateManager(
                request_state_store=request_state_store,
                task_id=task_id,
                operation="migrate_model_storage",
                build_request_state=build_request_state,
                should_cancel=lambda: request_state_store.is_cancel_requested(task_id),
            )
            request_state_store.clear_cancel_request(task_id)
            progress.start(progress_percent=5.0, message="Preparing model storage migration...")

            def on_migration_progress(current: int, total: int, filename: str) -> None:
                percent = 5.0 if total <= 0 else 5.0 + min(90.0, (current / total) * 90.0)
                progress.update_running(
                    percent,
                    f"Migrating model storage... {filename}",
                    max_percent=95.0,
                )

            try:
                result = migrate_model_storage(
                    config_store,
                    Path(args.cwd),
                    Path(destination),
                    on_progress=on_migration_progress,
                    should_cancel=progress.should_cancel,
                )
            except TaskCancellationRequested as exc:
                cancel_progress = progress.current_progress(default=5.0)
                progress.save_cancelled(progress_percent=cancel_progress, message=str(exc))
                request_state_store.clear_cancel_request(task_id)
                raise BridgeTaskCancelledError(
                    str(exc),
                    operation="migrate_model_storage",
                    progress_percent=cancel_progress,
                ) from exc
            except Exception as exc:
                progress.save_failed(message=str(exc) or "Model storage migration failed.")
                request_state_store.clear_cancel_request(task_id)
                raise
            progress.save_finalizing(
                progress_percent=98.0,
                message="Finalizing model storage migration...",
            )
            progress.save_succeeded(message=f"Model storage migrated to {Path(destination).expanduser().resolve()}.")
            request_state_store.clear_cancel_request(task_id)
            payload = dict(result)
            payload["task_id"] = task_id
            return output_payload(args, payload)

        if args.download_model.strip():
            model_name = args.download_model.strip()
            task_id = f"download_model:{model_name}"
            progress = LongTaskStateManager(
                request_state_store=request_state_store,
                task_id=task_id,
                operation="download_model",
                build_request_state=build_request_state,
                should_cancel=lambda: request_state_store.is_cancel_requested(task_id),
            )
            request_state_store.clear_cancel_request(task_id)
            progress_pattern = re.compile(rf"{re.escape(DOWNLOAD_PROGRESS_MARKER)}\s+(\d{{1,3}})")

            progress.start(progress_percent=5.0, message=f"Downloading model {model_name}...")
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
                request_state_store.clear_cancel_request(task_id)
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
                request_state_store.clear_cancel_request(task_id)

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
                result = download_voice_model(
                    Path(args.cwd),
                    model_name,
                    config_store=config_store,
                    on_output_line=on_download_output_line,
                    should_cancel=progress.should_cancel,
                )
            except TaskCancellationRequested as exc:
                progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                raise_download_cancelled(str(exc), default_progress=5.0)
            except Exception as exc:
                progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                if request_state_store.is_cancel_requested(task_id) or progress.current_phase() == "cancelling":
                    raise_download_cancelled(
                        f"Model {model_name} download cancelled.",
                        default_progress=5.0,
                        source_error=exc,
                    )
                fail_download(str(exc))
                raise
            progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
            progress.save_finalizing(
                progress_percent=98.0,
                message=f"Finalizing model {model_name}...",
            )
            saved_succeeded = progress.save_succeeded(message=f"Model {model_name} is ready.")
            if not saved_succeeded and (
                request_state_store.is_cancel_requested(task_id) or progress.current_phase() == "cancelling"
            ):
                raise_download_cancelled(
                    f"Model {model_name} download cancelled.",
                    default_progress=98.0,
                )
            if not saved_succeeded:
                fail_download(f"Unable to finalize download state for {model_name}.")
                raise RuntimeError(f"Unable to finalize download state for {model_name}.")
            request_state_store.clear_cancel_request(task_id)
            payload = dict(result)
            payload["task_id"] = task_id
            return output_payload(args, payload)

        if args.delete_model.strip():
            result = delete_voice_model(Path(args.cwd), args.delete_model.strip(), config_store)
            return output_payload(args, result)

        if args.show_task_state.strip():
            task_id = args.show_task_state.strip()
            task_state = request_state_store.load(task_id)
            return output_payload(args, {"task_id": task_id, "task_state": task_state})

        if args.cancel_task.strip():
            task_id = args.cancel_task.strip()
            task_state = request_state_store.load(task_id)
            if task_state is None:
                request_state_store.clear_cancel_request(task_id)
                return output_payload(
                    args,
                    {"task_id": task_id, "task_state": None},
                    operation="cancel_task",
                    message="task_not_found",
                )

            phase = str(task_state.get("phase", "")).strip().lower()
            if phase in TASK_TERMINAL_PHASES:
                request_state_store.clear_cancel_request(task_id)
                return output_payload(
                    args,
                    {"task_id": task_id, "task_state": task_state},
                    operation="cancel_task",
                    message="task_already_terminal",
                )

            operation = str(task_state.get("operation") or "task")
            progress_percent = progress_from_request_state(task_state)
            run_token = str(task_state.get("run_token") or "").strip() or None
            request_state_store.request_cancel(task_id)
            cancelling_state = build_request_state(
                operation=operation,
                phase="cancelling",
                progress_percent=progress_percent,
                message=f"Cancellation requested for {task_id}.",
                run_token=run_token,
            )
            request_state_store.save(task_id, cancelling_state)
            return output_payload(
                args,
                {"task_id": task_id, "task_state": cancelling_state},
                operation="cancel_task",
                message="cancellation_requested",
            )

        if args.show_local_tts_capability:
            capability = detect_local_mlx_capability(config_store.load_tts_config()).to_dict()
            return output_payload(args, {"tts_capability": capability})

        if args.list_voice_presets:
            return output_payload(
                args,
                {
                    "voices": [voice.to_dict() for voice in VOICE_PRESETS],
                    "styles": [style.to_dict() for style in STYLE_PRESETS],
                    "standard_preview_text": STANDARD_PREVIEW_TEXT,
                },
            )

        if args.render_voice_preview:
            result = audio_rendering.render_voice_preview(VoiceRenderSettings())
            return output_payload(
                args,
                {
                    "provider": result.provider,
                    "model": result.model,
                    "audio_path": result.audio_path,
                    "settings": {
                        "voice_id": result.settings.voice_id,
                        "voice_name": result.settings.voice_name,
                        "style_id": result.settings.style_id,
                        "style_name": result.settings.style_name,
                        "speed": result.settings.speed,
                        "language": result.settings.language,
                        "audio_format": result.settings.audio_format,
                        "preview_text": result.settings.preview_text,
                    },
                },
            )

        if args.render_voice_take:
            project = store.load_project(args.render_voice_take)
            ensure_script_is_active(project)
            if project.script is None:
                raise ValueError("Cannot render voice take because no script record exists.")
            result = audio_rendering.render_voice_take(
                args.render_voice_take,
                script_id=project.script.script_id,
                override_provider=args.tts_provider_override,
                settings=VoiceRenderSettings(),
            )
            return output_payload(args, serialize_voice_take_result(result))

        if args.set_final_voice_take:
            if not args.take_id.strip():
                raise ValueError("--take-id is required when using --set-final-voice-take")
            project = audio_rendering.set_final_voice_take(args.set_final_voice_take, args.take_id.strip())
            return output_payload(args, {"project": serialize_project(project)})

        if args.start_interview:
            project = store.load_project(args.start_interview)
            ensure_session_is_active(project)
            result = orchestrator.start_interview(args.start_interview)
            return output_payload(args, serialize_turn_result(result))

        if args.reply_session:
            if not args.message.strip():
                raise ValueError("--message is required when using --reply-session")
            project = store.load_project(args.reply_session)
            ensure_session_is_active(project)

            final_result = None
            for chunk in orchestrator.submit_user_response_stream(
                args.reply_session,
                args.message,
                user_requested_finish=args.user_requested_finish,
            ):
                if isinstance(chunk, InterviewTurnResult):
                    final_result = chunk
                else:
                    chunk_payload = {
                        "ok": True,
                        "type": "chunk",
                        "delta": chunk,
                    }
                    print(json.dumps(chunk_payload))
                    sys.stdout.flush()

            if final_result:
                return output_payload(args, serialize_turn_result(final_result))
            raise RuntimeError("Streaming finished without a final result record.")

        if args.finish_session:
            project = store.load_project(args.finish_session)
            ensure_session_is_active(project)
            result = orchestrator.request_finish(args.finish_session)
            return output_payload(args, serialize_turn_result(result))

        if args.generate_script:
            project = store.load_project(args.generate_script)
            ensure_session_is_active(project)
            result = script_generation.generate_draft(
                args.generate_script,
                override_provider=args.llm_provider_override,
            )
            return output_payload(args, serialize_generation_result(result))

        if args.render_audio:
            session_id = args.render_audio
            project = store.load_project(session_id)
            ensure_session_is_active(project)
            ensure_script_is_active(project)
            task_id = f"render_audio:{session_id}"
            progress = LongTaskStateManager(
                request_state_store=request_state_store,
                task_id=task_id,
                operation="render_audio",
                build_request_state=build_request_state,
                should_cancel=lambda: request_state_store.is_cancel_requested(task_id),
            )
            request_state_store.clear_cancel_request(task_id)

            progress.start(
                progress_percent=5.0,
                message=f"Rendering audio for session {session_id}...",
            )
            heartbeat_stop, heartbeat_thread = progress.start_heartbeat(
                start_percent=10.0,
                max_percent=88.0,
                step_percent=2.0,
                interval_seconds=1.2,
                message=f"Synthesizing audio for session {session_id}...",
            )

            def raise_render_cancelled(
                message: str,
                *,
                default_progress: float,
                source_error: Exception | None = None,
            ) -> None:
                cancel_progress = progress.current_progress(default=default_progress)
                progress.save_cancelled(progress_percent=cancel_progress, message=message)
                request_state_store.clear_cancel_request(task_id)
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
                request_state_store.clear_cancel_request(task_id)

            try:
                result = audio_rendering.render_audio_with_cancellation(
                    session_id,
                    override_provider=args.tts_provider_override,
                    should_cancel=progress.should_cancel,
                )
            except TaskCancellationRequested as exc:
                progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                raise_render_cancelled(str(exc), default_progress=10.0)
            except Exception as exc:
                progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
                current_phase = progress.current_phase()
                if request_state_store.is_cancel_requested(task_id) or current_phase == "cancelling":
                    raise_render_cancelled(
                        f"Audio rendering cancelled for session {session_id}.",
                        default_progress=10.0,
                        source_error=exc,
                    )
                fail_render(str(exc))
                raise
            progress.stop_heartbeat(heartbeat_stop, heartbeat_thread)
            progress.save_finalizing(
                progress_percent=96.0,
                message=f"Finalizing rendered artifacts for session {session_id}...",
            )
            saved_succeeded = progress.save_succeeded(
                message=f"Audio render finished for session {session_id}.",
            )
            if not saved_succeeded:
                current_phase = progress.current_phase()
                if current_phase == "cancelling" or request_state_store.is_cancel_requested(task_id):
                    raise_render_cancelled(
                        f"Audio rendering cancelled for session {session_id}.",
                        default_progress=96.0,
                    )
                fail_render(f"Unable to finalize audio render for session {session_id}.")
                raise RuntimeError(f"Unable to finalize audio render for session {session_id}.")
            request_state_store.clear_cancel_request(task_id)
            payload = serialize_audio_result(result)
            payload["task_id"] = task_id
            return output_payload(args, payload)

        if args.show_session:
            project = store.load_project(args.show_session)
            if project.session.is_deleted() and not args.list_projects_include_deleted:
                raise ValueError("Session is deleted. Pass --include-deleted to inspect it.")
            return output_payload(args, {"project": serialize_project(project)})

        print(f"Known sessions: {len(store.list_projects())}")
        return 0
    except BridgeTaskCancelledError as exc:
        return output_error(
            args,
            code="task_cancelled",
            message=str(exc),
            details={"exception_type": exc.__class__.__name__},
            operation=exc.operation,
            phase="cancelled",
            progress_percent=exc.progress_percent,
        )
    except Exception as exc:
        return output_error(
            args,
            code="python_core_error",
            message=str(exc),
            details={"exception_type": exc.__class__.__name__},
        )


if __name__ == "__main__":
    raise SystemExit(run())
