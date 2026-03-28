from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord
from app.domain.transcript import Speaker, TranscriptRecord
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
        transcript = TranscriptRecord(session_id=session.session_id)
        transcript.append(Speaker.AGENT, "What makes this topic worth turning into a podcast?")
        transcript.append(Speaker.USER, "I want to validate the local-first project scaffolding.")

        script = ScriptRecord(
            session_id=session.session_id,
            draft="Draft script pending real generation.",
            final="Draft script pending real generation.",
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
    elif args.show_session:
        project = store.load_project(args.show_session)
        print(
            json.dumps(
                {
                    "session": project.session.to_dict(),
                    "transcript": project.transcript.to_dict() if project.transcript else None,
                    "script": project.script.to_dict() if project.script else None,
                    "artifact": project.artifact.to_dict() if project.artifact else None,
                },
                indent=2,
            )
        )
    else:
        print(f"Known sessions: {len(store.list_projects())}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
