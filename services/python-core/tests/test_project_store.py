from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import Speaker, TranscriptRecord
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

    def test_project_store_recovers_full_project_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AppConfig.from_cwd(Path(tmp_dir))
            store = ProjectStore(config.data_dir)
            store.bootstrap()

            session = SessionRecord(topic="Recovery", creation_intent="Validate loading")
            transcript = TranscriptRecord(session_id=session.session_id)
            transcript.append(Speaker.AGENT, "What happened?")
            transcript.append(Speaker.USER, "A full session payload was persisted.")

            script = ScriptRecord(session_id=session.session_id)
            script.update_draft("Draft copy")
            script.update_final("Final copy")

            artifact = ArtifactRecord(
                session_id=session.session_id,
                transcript_path="sessions/recovery/transcript.json",
                audio_path="exports/recovery.mp3",
                provider="demo-provider",
            )

            project = SessionProject(
                session=session,
                transcript=transcript,
                script=script,
                artifact=artifact,
            )

            store.save_project(project)
            loaded = store.load_project(session.session_id)

            self.assertIsNotNone(loaded.transcript)
            self.assertIsNotNone(loaded.script)
            self.assertIsNotNone(loaded.artifact)
            assert loaded.transcript is not None
            assert loaded.script is not None
            assert loaded.artifact is not None
            self.assertEqual(len(loaded.transcript.turns), 2)
            self.assertEqual(loaded.script.final, "Final copy")
            self.assertEqual(loaded.artifact.audio_path, "exports/recovery.mp3")

    def test_project_store_persists_script_revisions_and_deleted_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AppConfig.from_cwd(Path(tmp_dir))
            store = ProjectStore(config.data_dir)
            store.bootstrap()

            session = SessionRecord(topic="Revision store", creation_intent="Persist revisions")
            script = ScriptRecord(session_id=session.session_id)
            script.save_final("First revision")
            script.save_final("Second revision")
            script.soft_delete()

            project = SessionProject(session=session, script=script)
            store.save_project(project)
            loaded = store.load_project(session.session_id)

            assert loaded.script is not None
            self.assertTrue(loaded.script.is_deleted())
            self.assertEqual(len(loaded.script.revisions), 3)
            self.assertEqual(loaded.script.revisions[-1].final, "Second revision")

    def test_list_sessions_excludes_deleted_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AppConfig.from_cwd(Path(tmp_dir))
            store = ProjectStore(config.data_dir)
            store.bootstrap()

            active = SessionRecord(topic="Active", creation_intent="One")
            deleted = SessionRecord(topic="Deleted", creation_intent="Two")
            deleted.soft_delete()

            store.save_session(active)
            store.save_session(deleted)

            sessions = store.list_sessions()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].topic, "Active")

            with_deleted = store.list_sessions(include_deleted=True)
            self.assertEqual(len(with_deleted), 2)

    def test_list_sessions_supports_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AppConfig.from_cwd(Path(tmp_dir))
            store = ProjectStore(config.data_dir)
            store.bootstrap()

            first = SessionRecord(topic="Apple pie", creation_intent="Baking")
            second = SessionRecord(topic="Orange", creation_intent="Citrus notes")

            store.save_session(first)
            store.save_session(second)

            filtered = store.list_sessions(search_query="apple")
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0].session_id, first.session_id)


if __name__ == "__main__":
    unittest.main()
