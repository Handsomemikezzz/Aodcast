from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.tts_config import TTSProviderConfig
from app.orchestration.audio_rendering import AudioRenderingService
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


class AudioRenderingTests(unittest.TestCase):
    def build_environment(self) -> tuple[ProjectStore, ConfigStore, ArtifactStore, AudioRenderingService]:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = AppConfig.from_cwd(Path(self.temp_dir.name))
        store = ProjectStore(config.data_dir)
        config_store = ConfigStore(config.config_dir)
        artifact_store = ArtifactStore(config.data_dir)
        store.bootstrap()
        config_store.bootstrap()
        artifact_store.bootstrap()
        return store, config_store, artifact_store, AudioRenderingService(
            store,
            config_store,
            artifact_store,
        )

    def tearDown(self) -> None:
        temp_dir = getattr(self, "temp_dir", None)
        if temp_dir is not None:
            temp_dir.cleanup()

    def seed_script_project(self, store: ProjectStore) -> str:
        session = SessionRecord(topic="Audio flow", creation_intent="Validate remote TTS")
        session.transition(SessionState.SCRIPT_EDITED)
        script = ScriptRecord(
            session_id=session.session_id,
            draft="Draft body",
            final="Final edited script for audio rendering.",
        )
        artifact = ArtifactRecord(session_id=session.session_id)
        store.save_project(SessionProject(session=session, script=script, artifact=artifact))
        return session.session_id

    def test_render_audio_with_mock_provider_writes_artifacts(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session_id = self.seed_script_project(store)

        result = service.render_audio(session_id)
        loaded = store.load_project(session_id)

        self.assertEqual(result.provider, "mock_remote")
        self.assertEqual(loaded.session.state, SessionState.COMPLETED)
        assert loaded.artifact is not None
        self.assertTrue(Path(loaded.artifact.audio_path).exists())
        self.assertTrue(Path(loaded.artifact.transcript_path).exists())
        self.assertEqual(loaded.session.tts_provider, "mock_remote")

    def test_render_audio_failure_marks_session_failed(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(
            TTSProviderConfig(
                provider="openai_compatible",
                model="tts-test",
                base_url="https://example.invalid/v1",
                api_key_env="MISSING_TTS_KEY",
            )
        )
        os.environ.pop("MISSING_TTS_KEY", None)
        session_id = self.seed_script_project(store)

        with self.assertRaises(ValueError):
            service.render_audio(session_id)

        loaded = store.load_project(session_id)
        self.assertEqual(loaded.session.state, SessionState.FAILED)
        self.assertIn("MISSING_TTS_KEY", loaded.session.last_error)

    def test_render_audio_requires_script_state(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session = SessionRecord(topic="Guard", creation_intent="Reject invalid state")
        script = ScriptRecord(session_id=session.session_id, draft="Draft", final="Final")
        artifact = ArtifactRecord(session_id=session.session_id)
        store.save_project(SessionProject(session=session, script=script, artifact=artifact))

        with self.assertRaises(ValueError):
            service.render_audio(session.session_id)


if __name__ == "__main__":
    unittest.main()
