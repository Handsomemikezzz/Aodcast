from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.provider_config import LLMProviderConfig
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.interview_service import InterviewOrchestrator, InterviewTurnResult
from app.orchestration.script_generation import (
    ScriptGenerationResult,
    ScriptGenerationService,
    build_generation_context,
)
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aodcast-python-core",
        description="Bootstrap utility for the Aodcast Python orchestration core.",
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Project root")
    parser.add_argument("--topic", default="A new podcast topic", help="Topic seed")
    parser.add_argument(
        "--intent",
        default="Validate bootstrap wiring",
        help="Short creation intent",
    )
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


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.from_cwd(args.cwd)
    store = ProjectStore(config.data_dir)
    config_store = ConfigStore(config.config_dir)
    orchestrator = InterviewOrchestrator(store)
    script_generation = ScriptGenerationService(store, config_store)
    store.bootstrap()
    config_store.bootstrap()

    print(f"Aodcast Python core ready at: {config.data_dir}")

    if args.create_demo_session:
        session = SessionRecord(topic=args.topic, creation_intent=args.intent)
        transcript = TranscriptRecord(session_id=session.session_id)
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
        project = SessionProject(
            session=session,
            transcript=transcript,
            script=script,
            artifact=artifact,
        )
        store.save_project(project)
        print(f"Created demo session {session.session_id} at {store.session_dir(session.session_id)}")
    elif args.configure_llm_provider:
        llm_config = config_store.load_llm_config()
        llm_config.provider = args.configure_llm_provider
        if args.llm_model:
            llm_config.model = args.llm_model
        if args.llm_base_url:
            llm_config.base_url = args.llm_base_url
        if args.llm_api_key_env:
            llm_config.api_key_env = args.llm_api_key_env
        path = config_store.save_llm_config(llm_config)
        print(json.dumps({"path": str(path), "llm_config": llm_config.to_dict()}, indent=2))
    elif args.show_llm_config:
        print(json.dumps(config_store.load_llm_config().to_dict(), indent=2))
    elif args.start_interview:
        result = orchestrator.start_interview(args.start_interview)
        print(json.dumps(serialize_turn_result(result), indent=2))
    elif args.reply_session:
        if not args.message.strip():
            parser.error("--message is required when using --reply-session")
        result = orchestrator.submit_user_response(
            args.reply_session,
            args.message,
            user_requested_finish=args.user_requested_finish,
        )
        print(json.dumps(serialize_turn_result(result), indent=2))
    elif args.finish_session:
        result = orchestrator.request_finish(args.finish_session)
        print(json.dumps(serialize_turn_result(result), indent=2))
    elif args.generate_script:
        result = script_generation.generate_draft(
            args.generate_script,
            override_provider=args.llm_provider_override,
        )
        print(json.dumps(serialize_generation_result(result), indent=2))
    elif args.show_session:
        project = store.load_project(args.show_session)
        print(json.dumps(serialize_project(project), indent=2))
    else:
        print(f"Known sessions: {len(store.list_projects())}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
