from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import AppConfig
from app.domain.session import SessionRecord, SessionState
from app.storage.project_store import ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def test_project_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AppConfig.from_cwd(Path(tmp_dir))
            store = ProjectStore(config.data_dir)
            store.bootstrap()

            session = SessionRecord(
                topic="Async work",
                creation_intent="Test persistence",
            )
            session.transition(SessionState.INTERVIEW_IN_PROGRESS)
            store.save_session(session)

            loaded = store.load_session(session.session_id)

            self.assertEqual(loaded.session_id, session.session_id)
            self.assertEqual(loaded.topic, "Async work")
            self.assertEqual(loaded.state, SessionState.INTERVIEW_IN_PROGRESS)

    def test_project_store_lists_saved_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AppConfig.from_cwd(Path(tmp_dir))
            store = ProjectStore(config.data_dir)
            store.bootstrap()

            first = SessionRecord(topic="First", creation_intent="One")
            second = SessionRecord(topic="Second", creation_intent="Two")

            store.save_session(first)
            store.save_session(second)

            sessions = store.list_sessions()

            self.assertEqual(len(sessions), 2)
            self.assertEqual(
                {session.topic for session in sessions},
                {"First", "Second"},
            )


if __name__ == "__main__":
    unittest.main()
