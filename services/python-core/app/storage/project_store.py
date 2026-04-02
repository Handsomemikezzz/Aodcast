from __future__ import annotations

import json
from pathlib import Path

from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord
from app.domain.transcript import TranscriptRecord


class ProjectStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.sessions_dir = self.data_dir / "sessions"

    def bootstrap(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def session_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.json"

    def transcript_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "transcript.json"

    def script_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "script.json"

    def artifact_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "artifact.json"

    def _write_json(self, path: Path, payload: dict[str, object]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return path

    def _read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def save_session(self, session: SessionRecord) -> Path:
        return self._write_json(self.session_file(session.session_id), session.to_dict())

    def load_session(self, session_id: str) -> SessionRecord:
        return SessionRecord.from_dict(self._read_json(self.session_file(session_id)))

    def save_transcript(self, transcript: TranscriptRecord) -> Path:
        return self._write_json(
            self.transcript_file(transcript.session_id),
            transcript.to_dict(),
        )

    def load_transcript(self, session_id: str) -> TranscriptRecord:
        return TranscriptRecord.from_dict(self._read_json(self.transcript_file(session_id)))

    def save_script(self, script: ScriptRecord) -> Path:
        return self._write_json(self.script_file(script.session_id), script.to_dict())

    def load_script(self, session_id: str) -> ScriptRecord:
        return ScriptRecord.from_dict(self._read_json(self.script_file(session_id)))

    def save_artifact(self, artifact: ArtifactRecord) -> Path:
        return self._write_json(
            self.artifact_file(artifact.session_id),
            artifact.to_dict(),
        )

    def load_artifact(self, session_id: str) -> ArtifactRecord:
        return ArtifactRecord.from_dict(self._read_json(self.artifact_file(session_id)))

    def save_project(self, project: SessionProject) -> None:
        self.save_session(project.session)
        if project.transcript is not None:
            self.save_transcript(project.transcript)
        if project.script is not None:
            self.save_script(project.script)
        if project.artifact is not None:
            self.save_artifact(project.artifact)

    def load_project(self, session_id: str) -> SessionProject:
        session = self.load_session(session_id)
        transcript = None
        script = None
        artifact = None

        transcript_path = self.transcript_file(session_id)
        script_path = self.script_file(session_id)
        artifact_path = self.artifact_file(session_id)

        if transcript_path.exists():
            transcript = self.load_transcript(session_id)
        if script_path.exists():
            script = self.load_script(session_id)
        if artifact_path.exists():
            artifact = self.load_artifact(session_id)

        return SessionProject(
            session=session,
            transcript=transcript,
            script=script,
            artifact=artifact,
        )

    def list_sessions(
        self,
        *,
        include_deleted: bool = False,
        search_query: str = "",
    ) -> list[SessionRecord]:
        if not self.sessions_dir.exists():
            return []
        query_value = search_query.strip().lower()
        sessions: list[SessionRecord] = []
        for session_file in sorted(self.sessions_dir.glob("*/session.json")):
            session = SessionRecord.from_dict(self._read_json(session_file))
            if not include_deleted and session.is_deleted():
                continue
            if query_value and query_value not in f"{session.topic} {session.creation_intent}".lower():
                continue
            sessions.append(session)
        return sessions

    def list_projects(
        self,
        *,
        include_deleted: bool = False,
        search_query: str = "",
    ) -> list[SessionProject]:
        return [
            self.load_project(session.session_id)
            for session in self.list_sessions(
                include_deleted=include_deleted,
                search_query=search_query,
            )
        ]
