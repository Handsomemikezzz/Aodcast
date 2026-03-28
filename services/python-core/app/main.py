from __future__ import annotations

import argparse
from pathlib import Path

from app.config import AppConfig
from app.domain.session import SessionRecord
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
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.from_cwd(args.cwd)
    store = ProjectStore(config.data_dir)
    store.bootstrap()

    print(f"Aodcast Python core ready at: {config.data_dir}")

    if args.create_demo_session:
        session = SessionRecord(topic=args.topic, creation_intent=args.intent)
        path = store.save_session(session)
        print(f"Created demo session {session.session_id} at {path}")
    else:
        print(f"Known sessions: {len(store.list_sessions())}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
