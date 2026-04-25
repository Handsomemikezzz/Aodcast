from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.tts_config import TTSProviderConfig
from app.orchestration.audio_rendering import AudioRenderingService
from app.runtime.task_cancellation import TaskCancellationRequested
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
                api_key="",
            )
        )
        session_id = self.seed_script_project(store)

        with self.assertRaises(ValueError):
            service.render_audio(session_id)

        loaded = store.load_project(session_id)
        self.assertEqual(loaded.session.state, SessionState.FAILED)
        self.assertIn("requires an api_key", loaded.session.last_error)

    def test_render_audio_rejects_concurrent_audio_rendering_state(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session = SessionRecord(topic="Guard", creation_intent="Reject invalid state")
        session.transition(SessionState.AUDIO_RENDERING)
        script = ScriptRecord(session_id=session.session_id, draft="Draft", final="Final")
        artifact = ArtifactRecord(session_id=session.session_id)
        store.save_project(SessionProject(session=session, script=script, artifact=artifact))

        with self.assertRaises(ValueError):
            service.render_audio(session.session_id)

    def test_render_audio_uses_draft_when_final_is_empty(self) -> None:
        store, config_store, artifact_store, service = self.build_environment()
        config_store.save_tts_config(
            TTSProviderConfig(
                provider="local_mlx",
                model="mlx-voice",
                local_model_path="/tmp/model",
            )
        )
        session = SessionRecord(topic="Draft fallback", creation_intent="Render without final edit")
        session.transition(SessionState.SCRIPT_GENERATED)
        script = ScriptRecord(
            session_id=session.session_id,
            draft="Draft script body should be rendered.",
            final="",
        )
        artifact = ArtifactRecord(session_id=session.session_id)
        store.save_project(SessionProject(session=session, script=script, artifact=artifact))

        with patch(
            "app.providers.tts_local_mlx.provider.detect_local_mlx_capability",
            return_value=type(
                "Capability",
                (),
                {"available": True, "reasons": [], "fallback_provider": "mock_remote"},
            )(),
        ), patch(
            "app.providers.tts_local_mlx.provider.MLXAudioQwenRunner.synthesize",
            return_value=type(
                "RunResult",
                (),
                {
                    "audio_bytes": b"runner-wav",
                    "file_extension": "wav",
                    "model_name": "mlx-voice",
                    "output_path": "/tmp/render.wav",
                },
            )(),
        ):
            result = service.render_audio(session.session_id)

        transcript_text = Path(result.transcript_path).read_text(encoding="utf-8")
        self.assertEqual(transcript_text, script.draft + "\n")
        self.assertTrue(Path(result.audio_path).exists())
        self.assertTrue(Path(artifact_store.exports_dir / session.session_id).exists())

    def test_render_audio_targets_requested_script_snapshot(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))

        session = SessionRecord(topic="Snapshot target", creation_intent="Render a specific script")
        session.transition(SessionState.SCRIPT_EDITED)
        first_script = ScriptRecord(
            session_id=session.session_id,
            script_id="script-first",
            draft="First draft",
            final="First final transcript.",
            created_at="2026-04-24T00:00:00Z",
            updated_at="2026-04-24T00:00:00Z",
        )
        second_script = ScriptRecord(
            session_id=session.session_id,
            script_id="script-second",
            draft="Second draft",
            final="Second final transcript.",
            created_at="2026-04-24T01:00:00Z",
            updated_at="2026-04-24T01:00:00Z",
        )
        artifact = ArtifactRecord(session_id=session.session_id)
        store.save_project(SessionProject(session=session, script=second_script, artifact=artifact))
        store.save_script(first_script)

        result = service.render_audio_with_cancellation(session.session_id, script_id=first_script.script_id)

        transcript_text = Path(result.transcript_path).read_text(encoding="utf-8")
        self.assertEqual(transcript_text, first_script.final + "\n")
        loaded_latest = store.load_project(session.session_id)
        assert loaded_latest.script is not None
        self.assertEqual(loaded_latest.script.script_id, second_script.script_id)

    def test_render_audio_cancellation_restores_previous_state(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session_id = self.seed_script_project(store)
        checks = {"count": 0}

        def should_cancel() -> bool:
            checks["count"] += 1
            return checks["count"] >= 2

        class CancelAwareProvider:
            def synthesize(self, request):  # type: ignore[no-untyped-def]
                if request.should_cancel is not None and request.should_cancel():
                    raise TaskCancellationRequested("cancelled in provider")
                raise AssertionError("Provider should have been cancelled before writing output.")

        with patch(
            "app.orchestration.audio_rendering.build_tts_provider",
            return_value=CancelAwareProvider(),
        ):
            with self.assertRaises(TaskCancellationRequested):
                service.render_audio_with_cancellation(
                    session_id,
                    should_cancel=should_cancel,
                )

        loaded = store.load_project(session_id)
        self.assertEqual(loaded.session.state, SessionState.SCRIPT_EDITED)

    def test_render_audio_preserves_interview_state_for_historical_snapshot(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))

        session = SessionRecord(topic="Historical snapshot", creation_intent="Render without leaving interview")
        session.transition(SessionState.INTERVIEW_IN_PROGRESS)
        script = ScriptRecord(
            session_id=session.session_id,
            draft="Draft script body",
            final="Historical snapshot final text.",
        )
        artifact = ArtifactRecord(session_id=session.session_id)
        store.save_project(SessionProject(session=session, script=script, artifact=artifact))

        result = service.render_audio(session.session_id)
        loaded = store.load_project(session.session_id)

        self.assertEqual(result.provider, "mock_remote")
        self.assertEqual(loaded.session.state, SessionState.INTERVIEW_IN_PROGRESS)
        self.assertEqual(loaded.session.tts_provider, "mock_remote")
        self.assertEqual(loaded.session.last_error, "")

    def test_render_audio_failure_does_not_abort_active_interview(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(
            TTSProviderConfig(
                provider="openai_compatible",
                model="tts-test",
                base_url="https://example.invalid/v1",
                api_key="",
            )
        )

        session = SessionRecord(topic="Interview continues", creation_intent="Keep session active on TTS failure")
        session.transition(SessionState.INTERVIEW_IN_PROGRESS)
        script = ScriptRecord(session_id=session.session_id, draft="Draft", final="Final")
        artifact = ArtifactRecord(session_id=session.session_id)
        store.save_project(SessionProject(session=session, script=script, artifact=artifact))

        with self.assertRaises(ValueError):
            service.render_audio(session.session_id)

        loaded = store.load_project(session.session_id)
        self.assertEqual(loaded.session.state, SessionState.INTERVIEW_IN_PROGRESS)
        self.assertIn("requires an api_key", loaded.session.last_error)


if __name__ == "__main__":
    unittest.main()
