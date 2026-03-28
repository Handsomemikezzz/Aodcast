from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import TranscriptRecord
from app.orchestration.audio_rendering import AudioRenderResult, AudioRenderingService
from app.orchestration.interview_service import InterviewOrchestrator, InterviewTurnResult
from app.orchestration.script_generation import (
    ScriptGenerationResult,
    ScriptGenerationService,
    build_generation_context,
)
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability
from app.providers.tts_local_mlx.presets import DEFAULT_QWEN3_TTS_MODEL
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aodcast-python-core",
        description="Bootstrap utility for the Aodcast Python orchestration core.",
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Project root")
    parser.add_argument("--bridge-json", action="store_true", help="Emit a JSON envelope for desktop bridge calls.")
    parser.add_argument("--topic", default="A new podcast topic", help="Topic seed")
    parser.add_argument(
        "--intent",
        default="Validate bootstrap wiring",
        help="Short creation intent",
    )
    parser.add_argument("--list-projects", action="store_true", help="List all known projects.")
    parser.add_argument("--create-session", action="store_true", help="Create a new session project.")
    parser.add_argument(
        "--create-demo-session",
        action="store_true",
        help="Create a demo session record in local storage.",
    )
    parser.add_argument(
        "--show-session",
        default="",
        help="Print a recovered session project as JSON.",
    )
    parser.add_argument(
        "--save-script",
        default="",
        help="Persist a user-edited final script for a session id.",
    )
    parser.add_argument(
        "--script-final-text",
        default="",
        help="Final script text for --save-script.",
    )
    parser.add_argument(
        "--script-final-file",
        default="",
        help="Optional file path containing the final script text for --save-script.",
    )
    parser.add_argument(
        "--start-interview",
        default="",
        help="Start the interview flow for a session id.",
    )
    parser.add_argument(
        "--reply-session",
        default="",
        help="Submit a user answer to the interview flow for a session id.",
    )
    parser.add_argument(
        "--message",
        default="",
        help="User response content for --reply-session.",
    )
    parser.add_argument(
        "--finish-session",
        default="",
        help="Move a session directly to ready_to_generate.",
    )
    parser.add_argument(
        "--user-requested-finish",
        action="store_true",
        help="Mark the reply as an explicit user stop request.",
    )
    parser.add_argument(
        "--generate-script",
        default="",
        help="Generate a draft script for a session id.",
    )
    parser.add_argument(
        "--configure-llm-provider",
        default="",
        help="Persist the active LLM provider name.",
    )
    parser.add_argument(
        "--llm-model",
        default="",
        help="LLM model value for configuration updates.",
    )
    parser.add_argument(
        "--llm-base-url",
        default="",
        help="Base URL for an OpenAI-compatible provider.",
    )
    parser.add_argument(
        "--llm-api-key-env",
        default="",
        help="Environment variable name that stores the LLM API key.",
    )
    parser.add_argument(
        "--show-llm-config",
        action="store_true",
        help="Print the persisted LLM configuration.",
    )
    parser.add_argument(
        "--llm-provider-override",
        default="",
        help="Temporarily override the configured LLM provider for script generation.",
    )
    parser.add_argument(
        "--render-audio",
        default="",
        help="Render final audio for a session id.",
    )
    parser.add_argument(
        "--configure-tts-provider",
        default="",
        help="Persist the active TTS provider name.",
    )
    parser.add_argument(
        "--tts-model",
        default="",
        help="TTS model value for configuration updates.",
    )
    parser.add_argument(
        "--tts-base-url",
        default="",
        help="Base URL for an OpenAI-compatible TTS provider.",
    )
    parser.add_argument(
        "--tts-api-key-env",
        default="",
        help="Environment variable name that stores the TTS API key.",
    )
    parser.add_argument(
        "--tts-voice",
        default="",
        help="Voice identifier for TTS configuration updates.",
    )
    parser.add_argument(
        "--tts-audio-format",
        default="",
        help="Audio format for TTS output, for example wav or mp3.",
    )
    parser.add_argument(
        "--show-tts-config",
        action="store_true",
        help="Print the persisted TTS configuration.",
    )
    parser.add_argument(
        "--tts-provider-override",
        default="",
        help="Temporarily override the configured TTS provider for audio rendering.",
    )
    parser.add_argument(
        "--show-local-tts-capability",
        action="store_true",
        help="Print the current local MLX TTS capability report.",
    )
    parser.add_argument(
        "--tts-local-model-path",
        default="",
        help="Local model path for MLX TTS configuration updates.",
    )
    parser.add_argument(
        "--clear-tts-local-model-path",
        action="store_true",
        help="Clear the configured local model path for MLX TTS.",
    )
    return parser


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
    return {
        "project": serialize_project(project),
        "provider": result.provider,
        "model": result.model,
        "generation_context": build_generation_context(project),
    }


def serialize_audio_result(result: AudioRenderResult) -> dict[str, object]:
    return {
        "project": serialize_project(result.project),
        "provider": result.provider,
        "model": result.model,
        "audio_path": result.audio_path,
        "transcript_path": result.transcript_path,
    }


def create_project(topic: str, intent: str, *, demo: bool = False) -> SessionProject:
    session = SessionRecord(topic=topic, creation_intent=intent)
    transcript = TranscriptRecord(session_id=session.session_id)
    script = ScriptRecord(
        session_id=session.session_id,
        draft="Draft script pending real generation." if demo else "",
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


def load_final_script_text(args: argparse.Namespace) -> str:
    if args.script_final_file:
        return Path(args.script_final_file).read_text(encoding="utf-8")
    return args.script_final_text


def output_payload(args: argparse.Namespace, payload: dict[str, object]) -> int:
    if args.bridge_json:
        print(json.dumps({"ok": True, "data": payload}, indent=2))
    else:
        print(json.dumps(payload, indent=2))
    return 0


def output_error(
    args: argparse.Namespace,
    *,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> int:
    if args.bridge_json:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": code,
                        "message": message,
                        "details": details or {},
                    },
                },
                indent=2,
            )
        )
    else:
        print(message, file=sys.stderr)
    return 1


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.from_cwd(args.cwd)
    store = ProjectStore(config.data_dir)
    config_store = ConfigStore(config.config_dir)
    artifact_store = ArtifactStore(config.data_dir)
    orchestrator = InterviewOrchestrator(store)
    script_generation = ScriptGenerationService(store, config_store)
    audio_rendering = AudioRenderingService(store, config_store, artifact_store)
    store.bootstrap()
    config_store.bootstrap()
    artifact_store.bootstrap()

    if not args.bridge_json:
        print(f"Aodcast Python core ready at: {config.data_dir}")

    try:
        if args.list_projects:
            projects = sorted(
                store.list_projects(),
                key=lambda project: project.session.updated_at,
                reverse=True,
            )
            return output_payload(args, {"projects": [serialize_project(project) for project in projects]})

        if args.create_session or args.create_demo_session:
            project = create_project(args.topic, args.intent, demo=args.create_demo_session)
            store.save_project(project)
            if args.create_demo_session and not args.bridge_json:
                print(f"Created demo session {project.session.session_id} at {store.session_dir(project.session.session_id)}")
                return 0
            return output_payload(args, {"project": serialize_project(project)})

        if args.save_script:
            final_text = load_final_script_text(args)
            if not final_text.strip():
                raise ValueError("--script-final-text or --script-final-file is required when using --save-script")
            project = store.load_project(args.save_script)
            if project.script is None:
                raise ValueError("Cannot save an edited script without a script record.")
            project.script.update_final(final_text)
            project.session.transition(SessionState.SCRIPT_EDITED)
            store.save_project(project)
            return output_payload(args, {"project": serialize_project(project)})

        if args.configure_llm_provider:
            llm_config = config_store.load_llm_config()
            llm_config.provider = args.configure_llm_provider
            if args.llm_model:
                llm_config.model = args.llm_model
            if args.llm_base_url:
                llm_config.base_url = args.llm_base_url
            if args.llm_api_key_env:
                llm_config.api_key_env = args.llm_api_key_env
            path = config_store.save_llm_config(llm_config)
            return output_payload(args, {"path": str(path), "llm_config": llm_config.to_dict()})

        if args.configure_tts_provider:
            tts_config = config_store.load_tts_config()
            tts_config.provider = args.configure_tts_provider
            if (
                args.configure_tts_provider == "local_mlx"
                and tts_config.model in {"", "mock-voice"}
                and not args.tts_model
            ):
                tts_config.model = DEFAULT_QWEN3_TTS_MODEL
            if args.tts_model:
                tts_config.model = args.tts_model
            if args.tts_base_url:
                tts_config.base_url = args.tts_base_url
            if args.tts_api_key_env:
                tts_config.api_key_env = args.tts_api_key_env
            if args.tts_voice:
                tts_config.voice = args.tts_voice
            if args.tts_audio_format:
                tts_config.audio_format = args.tts_audio_format
            if args.clear_tts_local_model_path:
                tts_config.local_model_path = ""
            if args.tts_local_model_path:
                tts_config.local_model_path = args.tts_local_model_path
            path = config_store.save_tts_config(tts_config)
            return output_payload(args, {"path": str(path), "tts_config": tts_config.to_dict()})

        if args.show_llm_config:
            return output_payload(args, {"llm_config": config_store.load_llm_config().to_dict()})

        if args.show_tts_config:
            return output_payload(args, {"tts_config": config_store.load_tts_config().to_dict()})

        if args.show_local_tts_capability:
            capability = detect_local_mlx_capability(config_store.load_tts_config()).to_dict()
            return output_payload(args, {"tts_capability": capability})

        if args.start_interview:
            result = orchestrator.start_interview(args.start_interview)
            return output_payload(args, serialize_turn_result(result))

        if args.reply_session:
            if not args.message.strip():
                raise ValueError("--message is required when using --reply-session")
            result = orchestrator.submit_user_response(
                args.reply_session,
                args.message,
                user_requested_finish=args.user_requested_finish,
            )
            return output_payload(args, serialize_turn_result(result))

        if args.finish_session:
            result = orchestrator.request_finish(args.finish_session)
            return output_payload(args, serialize_turn_result(result))

        if args.generate_script:
            result = script_generation.generate_draft(
                args.generate_script,
                override_provider=args.llm_provider_override,
            )
            return output_payload(args, serialize_generation_result(result))

        if args.render_audio:
            result = audio_rendering.render_audio(
                args.render_audio,
                override_provider=args.tts_provider_override,
            )
            return output_payload(args, serialize_audio_result(result))

        if args.show_session:
            project = store.load_project(args.show_session)
            return output_payload(args, {"project": serialize_project(project)})

        if args.bridge_json:
            return output_payload(args, {"projects": []})

        print(f"Known sessions: {len(store.list_projects())}")
        return 0
    except Exception as exc:
        return output_error(
            args,
            code="python_core_error",
            message=str(exc),
            details={"exception_type": exc.__class__.__name__},
        )


if __name__ == "__main__":
    raise SystemExit(run())
