from __future__ import annotations

import json
from pathlib import Path

from app.domain.session import SessionRecord


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

    def save_session(self, session: SessionRecord) -> Path:
        session_dir = self.session_dir(session.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        session_path = self.session_file(session.session_id)
        session_path.write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return session_path

    def load_session(self, session_id: str) -> SessionRecord:
        payload = json.loads(self.session_file(session_id).read_text(encoding="utf-8"))
        return SessionRecord.from_dict(payload)

    def list_sessions(self) -> list[SessionRecord]:
        if not self.sessions_dir.exists():
            return []
        sessions: list[SessionRecord] = []
        for session_file in sorted(self.sessions_dir.glob("*/session.json")):
            payload = json.loads(session_file.read_text(encoding="utf-8"))
            sessions.append(SessionRecord.from_dict(payload))
        return sessions
