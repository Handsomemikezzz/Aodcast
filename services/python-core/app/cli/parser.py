from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aodcast-python-core",
        description="Bootstrap utility for the Aodcast Python orchestration core.",
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Project root")
    parser.add_argument("--serve-http", action="store_true", help="Run the stdlib localhost HTTP runtime.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for --serve-http.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port for --serve-http.")
    parser.add_argument("--runtime-token", default="", help="Runtime auth token for protected HTTP endpoints.")
    parser.add_argument(
        "--allowed-origins",
        default="",
        help="Comma-separated explicit origin allowlist for the HTTP runtime.",
    )
    parser.add_argument(
        "--bootstrap-nonce",
        default="",
        help="Single-use bootstrap nonce for same-machine browser token exchange.",
    )
    parser.add_argument("--topic", default="A new podcast topic", help="Topic seed")
    parser.add_argument(
        "--intent",
        default="Validate bootstrap wiring",
        help="Short creation intent",
    )
    parser.add_argument("--list-projects", action="store_true", help="List all known projects.")
    parser.add_argument(
        "--list-projects-include-deleted",
        "--include-deleted",
        dest="list_projects_include_deleted",
        action="store_true",
        help="Include soft-deleted sessions in --list-projects output.",
    )
    parser.add_argument(
        "--list-projects-query",
        "--search",
        dest="list_projects_query",
        default="",
        help="Optional search query for --list-projects (topic + creation_intent).",
    )
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
        "--rename-session",
        default="",
        help="Rename a session topic by session id.",
    )
    parser.add_argument(
        "--session-topic",
        default="",
        help="Session topic value for --rename-session.",
    )
    parser.add_argument(
        "--delete-session",
        default="",
        help="Soft-delete a session by id.",
    )
    parser.add_argument(
        "--restore-session",
        default="",
        help="Restore a soft-deleted session by id (within retention window).",
    )
    parser.add_argument(
        "--save-script",
        default="",
        help="Persist a user-edited final script for a session id.",
    )
    parser.add_argument(
        "--delete-script",
        default="",
        help="Soft-delete the script content for a session id.",
    )
    parser.add_argument(
        "--restore-script",
        default="",
        help="Restore a soft-deleted script for a session id (within retention window).",
    )
    parser.add_argument(
        "--list-script-revisions",
        default="",
        help="List script revisions for a session id.",
    )
    parser.add_argument(
        "--rollback-script-revision",
        default="",
        help="Rollback script content to a revision id for a session id.",
    )
    parser.add_argument(
        "--revision-id",
        default="",
        help="Target revision id for --rollback-script-revision.",
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
        "--no-stream",
        action="store_true",
        help="Disable streaming and wait for the full response before output.",
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
        default=None,
        help="LLM model value for configuration updates.",
    )
    parser.add_argument(
        "--llm-base-url",
        default=None,
        help="Base URL for an OpenAI-compatible provider.",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        help="Raw API key for an OpenAI-compatible LLM provider.",
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
    parser.add_argument("--list-voice-presets", action="store_true", help="List Voice Studio voice/style presets.")
    parser.add_argument("--render-voice-preview", action="store_true", help="Render the Voice Studio standard preview sentence.")
    parser.add_argument("--render-voice-take", default="", help="Render a Voice Studio candidate take for a session id.")
    parser.add_argument("--set-final-voice-take", default="", help="Set a Voice Studio take as final for a session id.")
    parser.add_argument("--take-id", default="", help="Take id for --set-final-voice-take.")
    parser.add_argument(
        "--configure-tts-provider",
        default="",
        help="Persist the active TTS provider name.",
    )
    parser.add_argument(
        "--tts-model",
        default=None,
        help="TTS model value for configuration updates.",
    )
    parser.add_argument(
        "--tts-base-url",
        default=None,
        help="Base URL for an OpenAI-compatible TTS provider.",
    )
    parser.add_argument(
        "--tts-api-key",
        default=None,
        help="Raw API key for an OpenAI-compatible TTS provider.",
    )
    parser.add_argument(
        "--tts-voice",
        default=None,
        help="Voice identifier for TTS configuration updates.",
    )
    parser.add_argument(
        "--tts-audio-format",
        default=None,
        help="Audio format for TTS output, for example wav or mp3.",
    )
    parser.add_argument(
        "--tts-local-runtime",
        default=None,
        help="Local runtime identifier, currently mlx on macOS.",
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
        "--list-models-status",
        action="store_true",
        help="List local voice models (Voicebox-aligned ids) with install status.",
    )
    parser.add_argument(
        "--download-model",
        default="",
        help="Download a catalog voice model (e.g. qwen-tts-0.6B). Uses scripts/model-download/.",
    )
    parser.add_argument(
        "--delete-model",
        default="",
        help="Delete a voice model directory under AODCAST_HF_MODEL_BASE or HF_HUB_CACHE.",
    )
    parser.add_argument(
        "--show-task-state",
        default="",
        help="Show the latest saved request state for a long-running task id.",
    )
    parser.add_argument(
        "--cancel-task",
        default="",
        help="Request cancellation for a long-running task id.",
    )
    parser.add_argument(
        "--tts-local-model-path",
        default=None,
        help="Local model path for MLX TTS configuration updates.",
    )
    parser.add_argument(
        "--clear-tts-local-model-path",
        action="store_true",
        help="Clear the configured local model path for MLX TTS.",
    )
    return parser


