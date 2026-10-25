from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Operator CLI: runtime startup, provider configuration, and diagnostics.

    Product operations go through the HTTP runtime (--serve-http), not this CLI.
    """
    parser = argparse.ArgumentParser(
        prog="aodcast-python-core",
        description="Operator utility for the Aodcast Python orchestration core.",
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

    parser.add_argument(
        "--create-demo-session",
        action="store_true",
        help="Create a demo session record in local storage.",
    )
    parser.add_argument("--topic", default="A new podcast topic", help="Topic for --create-demo-session.")
    parser.add_argument(
        "--intent",
        default="Validate bootstrap wiring",
        help="Creation intent for --create-demo-session.",
    )

    parser.add_argument(
        "--configure-llm-provider",
        default="",
        help="Persist the active LLM provider name (mock, openai_compatible, or codex_subscription).",
    )
    parser.add_argument("--llm-model", default=None, help="LLM model value for configuration updates.")
    parser.add_argument(
        "--llm-reasoning-effort",
        default=None,
        help="Codex reasoning effort (auto or a model-supported effort value).",
    )
    parser.add_argument("--llm-base-url", default=None, help="Base URL for an OpenAI-compatible provider.")
    parser.add_argument("--llm-api-key", default=None, help="Raw API key for an OpenAI-compatible LLM provider.")
    parser.add_argument("--show-llm-config", action="store_true", help="Print the persisted LLM configuration.")
    parser.add_argument(
        "--check-llm-config",
        action="store_true",
        help="Check whether the persisted LLM configuration can run interview and script generation.",
    )

    parser.add_argument("--configure-tts-provider", default="", help="Persist the active TTS provider name.")
    parser.add_argument("--tts-model", default=None, help="TTS model value for configuration updates.")
    parser.add_argument("--tts-base-url", default=None, help="Base URL for an OpenAI-compatible TTS provider.")
    parser.add_argument("--tts-api-key", default=None, help="Raw API key for an OpenAI-compatible TTS provider.")
    parser.add_argument("--tts-voice", default=None, help="Voice identifier for TTS configuration updates.")
    parser.add_argument("--tts-audio-format", default=None, help="Audio format for TTS output, for example wav or mp3.")
    parser.add_argument("--show-tts-config", action="store_true", help="Print the persisted TTS configuration.")

    parser.add_argument(
        "--show-local-tts-capability",
        action="store_true",
        help="Print the current local HTTP speech service capability report.",
    )
    parser.add_argument(
        "--list-models-status",
        action="store_true",
        help="List speech service models and readiness status.",
    )
    return parser
