from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.api.http_runtime import serve_http
from app.cli.parser import build_parser
from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord
from app.domain.transcript import TranscriptRecord
from app.models_catalog import DEFAULT_LOCAL_TTS_MODEL, build_models_status
from app.providers.llm.factory import validate_llm_provider
from app.providers.llm.preflight import check_llm_config
from app.providers.local_speech.capabilities import detect_local_speech_capability
from app.providers.tts_api.factory import validate_tts_provider
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


def create_demo_project(topic: str, intent: str) -> SessionProject:
    session = SessionRecord(topic=topic, creation_intent=intent)
    return SessionProject(
        session=session,
        transcript=TranscriptRecord(session_id=session.session_id),
        script=ScriptRecord(
            session_id=session.session_id,
            draft="Draft script pending real generation.",
            final="",
        ),
        artifact=ArtifactRecord(
            session_id=session.session_id,
            transcript_path=f"sessions/{session.session_id}/transcript.json",
            audio_path="",
            provider="",
        ),
    )


def configure_llm_provider(args: argparse.Namespace, config_store: ConfigStore) -> dict[str, object]:
    validate_llm_provider(args.configure_llm_provider)
    llm_config = config_store.load_llm_config()
    llm_config.provider = args.configure_llm_provider
    if args.llm_model is not None:
        llm_config.model = args.llm_model
    if args.llm_reasoning_effort is not None:
        llm_config.reasoning_effort = args.llm_reasoning_effort.strip().lower() or "auto"
    if args.llm_base_url is not None:
        llm_config.base_url = args.llm_base_url
    if args.llm_api_key is not None:
        llm_config.api_key = args.llm_api_key
    if args.configure_llm_provider == "codex_subscription":
        llm_config.base_url = ""
        llm_config.api_key = ""
    path = config_store.save_llm_config(llm_config)
    return {"path": str(path), "llm_config": llm_config.to_dict()}


def configure_tts_provider(args: argparse.Namespace, config_store: ConfigStore) -> dict[str, object]:
    validate_tts_provider(args.configure_tts_provider)
    tts_config = config_store.load_tts_config()
    tts_config.provider = args.configure_tts_provider
    if args.tts_model is not None:
        if args.configure_tts_provider == "local_http" and args.tts_model.strip() == "":
            tts_config.model = DEFAULT_LOCAL_TTS_MODEL
        else:
            tts_config.model = args.tts_model
    elif args.configure_tts_provider == "local_http" and tts_config.model in {"", "mock-voice"}:
        tts_config.model = DEFAULT_LOCAL_TTS_MODEL
    if args.tts_base_url is not None:
        tts_config.base_url = args.tts_base_url
    if args.tts_api_key is not None:
        tts_config.api_key = args.tts_api_key
    if args.tts_voice is not None:
        tts_config.voice = args.tts_voice
    if args.tts_audio_format is not None:
        tts_config.audio_format = args.tts_audio_format
    path = config_store.save_tts_config(tts_config)
    return {"path": str(path), "tts_config": tts_config.to_dict()}


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.serve_http:
        return serve_http(
            cwd=Path(args.cwd),
            host=args.host,
            port=args.port,
            runtime_token=args.runtime_token.strip() or None,
            allowed_origins=args.allowed_origins.strip() or None,
            bootstrap_nonce=args.bootstrap_nonce.strip() or None,
        )

    config = AppConfig.from_cwd(args.cwd)
    store = ProjectStore(config.data_dir)
    config_store = ConfigStore(config.config_dir)
    store.bootstrap()
    config_store.bootstrap()

    try:
        if args.create_demo_session:
            project = create_demo_project(args.topic, args.intent)
            store.save_project(project)
            payload: dict[str, object] = {
                "session_id": project.session.session_id,
                "session_dir": str(store.session_dir(project.session.session_id)),
            }
        elif args.configure_llm_provider:
            payload = configure_llm_provider(args, config_store)
        elif args.configure_tts_provider:
            payload = configure_tts_provider(args, config_store)
        elif args.show_llm_config:
            payload = {"llm_config": config_store.load_llm_config().to_dict()}
        elif args.check_llm_config:
            payload = {"llm_preflight": check_llm_config(config_store.load_llm_config()).to_dict()}
        elif args.show_tts_config:
            payload = {"tts_config": config_store.load_tts_config().to_dict()}
        elif args.show_local_tts_capability:
            payload = {"tts_capability": detect_local_speech_capability(config_store.load_tts_config()).to_dict()}
        elif args.list_models_status:
            payload = {"models": build_models_status(config_store, Path(args.cwd))}
        else:
            parser.print_help()
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
