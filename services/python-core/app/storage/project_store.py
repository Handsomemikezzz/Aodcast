from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.domain.artifact import ArtifactRecord
from app.domain.common import utc_now_iso
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord
from app.domain.transcript import TranscriptRecord


def _script_sort_key(script: ScriptRecord) -> str:
    return script.created_at


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

    def legacy_script_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "script.json"

    def scripts_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "scripts"

    def script_blob_file(self, session_id: str, script_id: str) -> Path:
        return self.scripts_dir(session_id) / f"{script_id}.json"

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
        """Persist a script to scripts/{script_id}.json."""
        return self._write_json(self.script_blob_file(script.session_id, script.script_id), script.to_dict())

    def load_script(self, session_id: str) -> ScriptRecord:
        """Deprecated single-file layout; use load_latest_script or load_script_by_id."""
        return ScriptRecord.from_dict(self._read_json(self.legacy_script_file(session_id)))

    def _maybe_migrate_legacy_script(self, session_id: str) -> None:
        legacy = self.legacy_script_file(session_id)
        if not legacy.exists():
            return
        bucket = self.scripts_dir(session_id)
        if bucket.exists() and any(bucket.glob("*.json")):
            return
        payload = self._read_json(legacy)
        payload["session_id"] = session_id
        if not payload.get("script_id"):
            payload["script_id"] = str(uuid4())
        if not payload.get("name"):
            try:
                session = self.load_session(session_id)
                topic = session.topic.strip() or "Untitled"
            except OSError:
                topic = "Untitled"
            ts = str(payload.get("updated_at") or payload.get("created_at") or utc_now_iso())
            payload["name"] = f"{topic}-{ts[:16].replace('T', ' ')}" if len(ts) >= 16 else f"{topic}-migrated"
        if not payload.get("created_at"):
            payload["created_at"] = payload.get("updated_at") or utc_now_iso()
        script = ScriptRecord.from_dict(payload)
        self._write_json(self.script_blob_file(session_id, script.script_id), script.to_dict())
        legacy.unlink()

    def list_scripts(self, session_id: str) -> list[ScriptRecord]:
        self._maybe_migrate_legacy_script(session_id)
        bucket = self.scripts_dir(session_id)
        if not bucket.exists():
            return []
        scripts: list[ScriptRecord] = []
        for path in sorted(bucket.glob("*.json")):
            scripts.append(ScriptRecord.from_dict(self._read_json(path)))
        scripts.sort(key=_script_sort_key, reverse=True)
        return scripts

    def load_script_by_id(self, session_id: str, script_id: str) -> ScriptRecord:
        self._maybe_migrate_legacy_script(session_id)
        path = self.script_blob_file(session_id, script_id)
        if not path.exists():
            raise ValueError(f"Unknown script_id '{script_id}' for session {session_id}.")
        return ScriptRecord.from_dict(self._read_json(path))

    def load_latest_script(self, session_id: str) -> ScriptRecord | None:
        scripts = self.list_scripts(session_id)
        return scripts[0] if scripts else None

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
        artifact = None

        transcript_path = self.transcript_file(session_id)
        artifact_path = self.artifact_file(session_id)

        if transcript_path.exists():
            transcript = self.load_transcript(session_id)
        script = self.load_latest_script(session_id)
        if artifact_path.exists():
            artifact = self.load_artifact(session_id)

        return SessionProject(
            session=session,
            transcript=transcript,
            script=script,
            artifact=artifact,
        )

    def load_project_for_script(self, session_id: str, script_id: str) -> SessionProject:
        session = self.load_session(session_id)
        transcript = None
        artifact = None
        if self.transcript_file(session_id).exists():
            transcript = self.load_transcript(session_id)
        script = self.load_script_by_id(session_id, script_id)
        if self.artifact_file(session_id).exists():
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
