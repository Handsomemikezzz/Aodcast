from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.provider_config import LLMProviderConfig
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.tts_config import TTSProviderConfig
from app.orchestration.audio_rendering import AudioRenderingService, VoiceRenderSettings
from app.runtime.task_cancellation import TaskCancellationRequested
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore
from tests.tts_test_fakes import SineWaveTTSProvider


class AudioRenderingTests(unittest.TestCase):
    def build_environment(self):
        temp = tempfile.TemporaryDirectory()
        config = AppConfig.from_cwd(Path(temp.name))
        store = ProjectStore(config.data_dir)
        configs = ConfigStore(config.config_dir)
        artifacts = ArtifactStore(config.data_dir)
        store.bootstrap()
        configs.bootstrap()
        artifacts.bootstrap()
        configs.save_llm_config(LLMProviderConfig(provider="mock"))
        configs.save_tts_config(
            TTSProviderConfig(provider="local_mlx", model="mlx-community/VoxCPM2-8bit", audio_format="wav")
        )
        fake = SineWaveTTSProvider()
        for target in (
            "app.orchestration.podcast_rendering.build_tts_provider",
            "app.orchestration.audio_rendering.build_tts_provider",
        ):
            patcher = patch(target, return_value=fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        return temp, store, configs, artifacts, AudioRenderingService(store, configs, artifacts)

    def seed_project(self, store: ProjectStore):
        session = SessionRecord(topic="Audio flow", creation_intent="Validate final rendering")
        session.transition(SessionState.SCRIPT_EDITED)
        script = ScriptRecord(
            session_id=session.session_id,
            draft="Draft body",
            final="这是第一句完整口播内容。这里是第二句，用来验证最终播客渲染。",
        )
        store.save_project(SessionProject(session=session, script=script, artifact=ArtifactRecord(session_id=session.session_id)))
        return session.session_id, script.script_id

    def test_final_render_writes_manifest_and_final_wav_take(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)

        result = service.render_audio(session_id, script_id=script_id)
        loaded = store.load_project_for_script(session_id, script_id)

        self.assertEqual(result.provider, "test_sine")
        self.assertTrue(Path(result.audio_path).is_file())
        self.assertEqual(loaded.session.state, SessionState.COMPLETED)
        self.assertIsNotNone(loaded.speech_plan)
        self.assertIsNotNone(loaded.render_manifest)
        assert loaded.artifact is not None
        self.assertEqual(loaded.artifact.final_take_id, loaded.artifact.takes[-1].render_id)

    def test_render_cancellation_restores_previous_state_and_publishes_no_manifest(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)

        with self.assertRaises(TaskCancellationRequested):
            service.render_audio_with_cancellation(
                session_id,
                script_id=script_id,
                should_cancel=lambda: True,
            )
        loaded = store.load_project_for_script(session_id, script_id)
        self.assertEqual(loaded.session.state, SessionState.SCRIPT_EDITED)
        self.assertIsNone(loaded.render_manifest)

    def test_voice_preview_is_temporary_and_does_not_change_final_settings(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)
        before = store.load_project_for_script(session_id, script_id)

        preview = service.render_voice_preview(
            VoiceRenderSettings(preview_text="这是一句临时试听文本。", style_id="story")
        )
        after = store.load_project_for_script(session_id, script_id)

        self.assertTrue(Path(preview.audio_path).is_file())
        assert before.artifact and after.artifact
        self.assertEqual(before.artifact.voice_settings, after.artifact.voice_settings)
        self.assertEqual(after.artifact.audio_path, "")

    def test_local_final_render_requires_speaker_reference_when_requested(self) -> None:
        temp, store, configs, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        configs.save_tts_config(TTSProviderConfig(provider="local_mlx", model="mlx-community/VoxCPM2-8bit"))
        session_id, script_id = self.seed_project(store)

        with self.assertRaisesRegex(ValueError, "speaker reference"):
            service.render_audio(
                session_id,
                script_id=script_id,
                require_speaker_reference=True,
            )


if __name__ == "__main__":
    unittest.main()
