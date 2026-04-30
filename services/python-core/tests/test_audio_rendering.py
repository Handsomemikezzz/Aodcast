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
from app.orchestration.audio_rendering import AudioRenderingService, VoiceRenderSettings
from app.providers.tts_api.base import TTSGenerationResponse
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

    def test_render_audio_initializes_missing_artifact_record(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session = SessionRecord(topic="Recovered artifact", creation_intent="Render older data")
        session.transition(SessionState.SCRIPT_GENERATED)
        script = ScriptRecord(
            session_id=session.session_id,
            draft="Draft body",
            final="Final script body for recovered artifact rendering.",
        )
        store.save_project(SessionProject(session=session, script=script, artifact=None))

        result = service.render_audio(session.session_id, script_id=script.script_id)
        loaded = store.load_project(session.session_id)

        self.assertEqual(result.provider, "mock_remote")
        assert loaded.artifact is not None
        self.assertTrue(Path(loaded.artifact.audio_path).exists())
        self.assertTrue(Path(loaded.artifact.transcript_path).exists())

    def test_render_voice_preview_writes_preview_without_changing_final_artifact(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session_id = self.seed_script_project(store)

        result = service.render_voice_preview(
            VoiceRenderSettings(
                voice_id="warm_narrator",
                voice_name="Warm Narrator",
                style_id="natural",
                style_name="Natural",
                speed=1.2,
            )
        )
        loaded = store.load_project(session_id)

        self.assertEqual(result.provider, "mock_remote")
        self.assertTrue(Path(result.audio_path).exists())
        assert loaded.artifact is not None
        self.assertEqual(loaded.artifact.audio_path, "")
        self.assertEqual(loaded.artifact.takes, [])

    def test_render_voice_preview_uses_custom_preview_text(self) -> None:
        _, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        captured: dict[str, str] = {}

        class CapturingProvider:
            def synthesize(self, request):
                captured["script_text"] = request.script_text
                return TTSGenerationResponse(
                    audio_bytes=b"preview-audio",
                    file_extension="wav",
                    provider_name="capture",
                    model_name="capture-model",
                )

        with patch("app.orchestration.audio_rendering.build_tts_provider", return_value=CapturingProvider()):
            result = service.render_voice_preview(
                VoiceRenderSettings(
                    voice_id="warm_narrator",
                    style_id="natural",
                    preview_text="这是我自己输入的一句试音文本。",
                )
            )

        self.assertEqual(captured["script_text"], "这是我自己输入的一句试音文本。")
        self.assertEqual(result.settings.preview_text, "这是我自己输入的一句试音文本。")
        self.assertTrue(Path(result.audio_path).exists())


    def test_render_voice_preview_applies_provider_override(self) -> None:
        _, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model"))
        captured: dict[str, object] = {}

        class CapturingProvider:
            def synthesize(self, request):  # type: ignore[no-untyped-def]
                return TTSGenerationResponse(
                    audio_bytes=b"preview-audio",
                    file_extension=request.audio_format,
                    provider_name="capture",
                    model_name="capture-model",
                )

        def build_provider(config):  # type: ignore[no-untyped-def]
            captured["provider"] = config.provider
            captured["voice"] = config.voice
            return CapturingProvider()

        with patch("app.orchestration.audio_rendering.build_tts_provider", side_effect=build_provider):
            service.render_voice_preview_with_cancellation(
                VoiceRenderSettings(voice_id="news_anchor", style_id="news"),
                override_provider="mock_remote",
            )

        self.assertEqual(captured["provider"], "mock_remote")
        self.assertEqual(captured["voice"], "onyx")

    def test_render_voice_take_keeps_final_take_and_latest_candidate_only(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session_id = self.seed_script_project(store)
        settings = VoiceRenderSettings(
            voice_id="warm_narrator",
            voice_name="Warm Narrator",
            style_id="natural",
            style_name="Natural",
            speed=1.0,
        )

        first = service.render_voice_take(session_id, settings=settings)
        second = service.render_voice_take(session_id, settings=settings)
        third = service.render_voice_take(
            session_id,
            settings=VoiceRenderSettings(
                voice_id="news_anchor",
                voice_name="News Anchor",
                style_id="news",
                style_name="News",
                speed=0.8,
            ),
        )
        loaded = store.load_project(session_id)

        assert loaded.artifact is not None
        self.assertEqual(loaded.artifact.final_take_id, third.take.take_id)
        self.assertEqual(loaded.artifact.audio_path, third.take.audio_path)
        self.assertEqual(loaded.artifact.voice_settings["voice_id"], "news_anchor")
        self.assertEqual({take.take_id for take in loaded.artifact.takes}, {second.take.take_id, third.take.take_id})
        self.assertNotIn(first.take.take_id, {take.take_id for take in loaded.artifact.takes})
        candidate = next(take for take in loaded.artifact.takes if take.take_id == third.take.take_id)
        self.assertEqual(candidate.voice_id, "news_anchor")
        self.assertEqual(candidate.style_id, "news")
        self.assertEqual(candidate.speed, 0.8)



    def test_voice_settings_are_isolated_per_script_snapshot(self) -> None:
        store, _, _, service = self.build_environment()
        session = SessionRecord(topic="Two scripts", creation_intent="Isolate voices")
        session.transition(SessionState.SCRIPT_EDITED)
        first = ScriptRecord(session_id=session.session_id, script_id="script-a", draft="A draft", final="A final")
        second = ScriptRecord(session_id=session.session_id, script_id="script-b", draft="B draft", final="B final")
        store.save_project(SessionProject(session=session, script=second, artifact=ArtifactRecord(session_id=session.session_id)))
        store.save_script(first)

        service.save_voice_settings(
            session.session_id,
            VoiceRenderSettings(voice_id="news_anchor", style_id="news", speed=0.8),
            script_id=first.script_id,
        )

        first_project = store.load_project_for_script(session.session_id, first.script_id)
        second_project = store.load_project_for_script(session.session_id, second.script_id)
        assert first_project.artifact is not None
        assert second_project.artifact is not None
        self.assertEqual(first_project.artifact.voice_settings["voice_id"], "news_anchor")
        self.assertEqual(second_project.artifact.voice_settings, {})

    def test_lock_voice_preview_persists_reference_for_requested_script(self) -> None:
        store, _, artifact_store, service = self.build_environment()
        session = SessionRecord(topic="Two scripts", creation_intent="Lock preview")
        session.transition(SessionState.SCRIPT_EDITED)
        first = ScriptRecord(session_id=session.session_id, script_id="script-a", draft="A draft", final="A final")
        second = ScriptRecord(session_id=session.session_id, script_id="script-b", draft="B draft", final="B final")
        store.save_project(SessionProject(session=session, script=second, artifact=ArtifactRecord(session_id=session.session_id)))
        store.save_script(first)
        preview_path = artifact_store.write_preview_audio(b"preview-audio", "wav")

        project = service.lock_voice_preview(
            session.session_id,
            script_id=first.script_id,
            preview_audio_path=str(preview_path),
            settings=VoiceRenderSettings(
                voice_id="news_anchor",
                style_id="news",
                speed=0.8,
                language="zh",
                audio_format="wav",
                preview_text="锁定这一句试音。",
            ),
            provider="local_mlx",
            model="mlx-voice",
        )

        assert project.artifact is not None
        self.assertEqual(project.artifact.voice_reference["audio_path"], str(preview_path))
        self.assertEqual(project.artifact.voice_reference["preview_text"], "锁定这一句试音。")
        self.assertEqual(project.artifact.voice_reference["provider"], "local_mlx")
        self.assertEqual(project.artifact.voice_reference["model"], "mlx-voice")
        self.assertEqual(project.artifact.voice_reference["voice_id"], "news_anchor")
        self.assertEqual(project.artifact.voice_settings["voice_id"], "news_anchor")

        second_project = store.load_project_for_script(session.session_id, second.script_id)
        assert second_project.artifact is not None
        self.assertEqual(second_project.artifact.voice_reference, {})

    def test_local_mlx_render_uses_locked_preview_as_reference_audio(self) -> None:
        store, config_store, artifact_store, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model"))
        session_id = self.seed_script_project(store)
        preview_path = artifact_store.write_preview_audio(b"preview-audio", "wav")
        service.lock_voice_preview(
            session_id,
            script_id="",
            preview_audio_path=str(preview_path),
            settings=VoiceRenderSettings(voice_id="deep_story", style_id="story", preview_text="参考试音。"),
            provider="local_mlx",
            model="mlx-voice",
        )
        captured: dict[str, object] = {}

        class CapturingProvider:
            def synthesize(self, request):  # type: ignore[no-untyped-def]
                captured["request"] = request
                return TTSGenerationResponse(
                    audio_bytes=b"local-audio",
                    file_extension=request.audio_format,
                    provider_name="local_mlx",
                    model_name="mlx-voice",
                )

        with patch("app.orchestration.audio_rendering.build_tts_provider", return_value=CapturingProvider()):
            service.render_audio(session_id)

        request = captured["request"]
        self.assertEqual(request.reference_audio_path, str(preview_path))
        self.assertEqual(request.reference_text, "参考试音。")
        self.assertTrue(request.voice_lock_id)

    def test_local_mlx_voice_take_uses_locked_preview_as_reference_audio(self) -> None:
        store, config_store, artifact_store, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model"))
        session_id = self.seed_script_project(store)
        preview_path = artifact_store.write_preview_audio(b"preview-audio", "wav")
        service.lock_voice_preview(
            session_id,
            script_id="",
            preview_audio_path=str(preview_path),
            settings=VoiceRenderSettings(voice_id="warm_narrator", style_id="natural", preview_text="参考 take。"),
            provider="local_mlx",
            model="mlx-voice",
        )
        captured: dict[str, object] = {}

        class CapturingProvider:
            def synthesize(self, request):  # type: ignore[no-untyped-def]
                captured["request"] = request
                return TTSGenerationResponse(
                    audio_bytes=b"local-take-audio",
                    file_extension=request.audio_format,
                    provider_name="local_mlx",
                    model_name="mlx-voice",
                )

        with patch("app.orchestration.audio_rendering.build_tts_provider", return_value=CapturingProvider()):
            service.render_voice_take(session_id, settings=VoiceRenderSettings(voice_id="warm_narrator", style_id="natural"))

        request = captured["request"]
        self.assertEqual(request.reference_audio_path, str(preview_path))
        self.assertEqual(request.reference_text, "参考 take。")

    def test_voice_take_audio_is_isolated_per_script_snapshot(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session = SessionRecord(topic="Two scripts", creation_intent="Isolate takes")
        session.transition(SessionState.SCRIPT_EDITED)
        first = ScriptRecord(session_id=session.session_id, script_id="script-a", draft="A draft", final="A final")
        second = ScriptRecord(session_id=session.session_id, script_id="script-b", draft="B draft", final="B final")
        store.save_project(SessionProject(session=session, script=second, artifact=ArtifactRecord(session_id=session.session_id)))
        store.save_script(first)

        take = service.render_voice_take(
            session.session_id,
            script_id=first.script_id,
            settings=VoiceRenderSettings(voice_id="deep_story", style_id="story"),
        )

        first_project = store.load_project_for_script(session.session_id, first.script_id)
        second_project = store.load_project_for_script(session.session_id, second.script_id)
        assert first_project.artifact is not None
        assert second_project.artifact is not None
        self.assertEqual(first_project.artifact.audio_path, take.audio_path)
        self.assertEqual(first_project.artifact.final_take_id, take.take.take_id)
        self.assertEqual(second_project.artifact.audio_path, "")
        self.assertEqual(second_project.artifact.final_take_id, "")
        self.assertEqual(second_project.artifact.takes, [])

    def test_delete_generated_audio_targets_requested_script_snapshot(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session = SessionRecord(topic="Two scripts", creation_intent="Delete one script audio")
        session.transition(SessionState.SCRIPT_EDITED)
        first = ScriptRecord(session_id=session.session_id, script_id="script-a", draft="A draft", final="A final")
        second = ScriptRecord(session_id=session.session_id, script_id="script-b", draft="B draft", final="B final")
        store.save_project(SessionProject(session=session, script=second, artifact=ArtifactRecord(session_id=session.session_id)))
        store.save_script(first)
        first_take = service.render_voice_take(
            session.session_id,
            script_id=first.script_id,
            settings=VoiceRenderSettings(voice_id="deep_story", style_id="story"),
        )
        second_take = service.render_voice_take(
            session.session_id,
            script_id=second.script_id,
            settings=VoiceRenderSettings(voice_id="news_anchor", style_id="news"),
        )

        service.delete_generated_audio(session.session_id, script_id=first.script_id)

        first_project = store.load_project_for_script(session.session_id, first.script_id)
        second_project = store.load_project_for_script(session.session_id, second.script_id)
        assert first_project.artifact is not None
        assert second_project.artifact is not None
        self.assertFalse(Path(first_take.audio_path).exists())
        self.assertEqual(first_project.artifact.audio_path, "")
        self.assertEqual(first_project.artifact.final_take_id, "")
        self.assertTrue(Path(second_take.audio_path).exists())
        self.assertEqual(second_project.artifact.audio_path, second_take.audio_path)
        self.assertEqual(second_project.artifact.final_take_id, second_take.take.take_id)

    def test_render_audio_uses_artifact_voice_studio_settings_as_default(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote", voice="onyx", audio_format="wav"))
        session_id = self.seed_script_project(store)
        loaded = store.load_project(session_id)
        assert loaded.artifact is not None
        loaded.artifact.voice_settings = {
            "voice_id": "casual_chat",
            "voice_name": "轻松聊天",
            "style_id": "casual",
            "style_name": "轻松聊天",
            "speed": 0.9,
            "language": "zh",
            "audio_format": "mp3",
        }
        store.save_project(loaded)
        captured: dict[str, object] = {}

        class CapturingProvider:
            def synthesize(self, request):  # type: ignore[no-untyped-def]
                captured["request"] = request
                return TTSGenerationResponse(
                    audio_bytes=b"voice-studio-audio",
                    file_extension=request.audio_format,
                    provider_name="capture",
                    model_name="capture-model",
                )

        def build_provider(config):  # type: ignore[no-untyped-def]
            captured["config_voice"] = config.voice
            captured["config_audio_format"] = config.audio_format
            return CapturingProvider()

        with patch("app.orchestration.audio_rendering.build_tts_provider", side_effect=build_provider):
            result = service.render_audio(session_id)

        request = captured["request"]
        self.assertEqual(captured["config_voice"], "nova")
        self.assertEqual(captured["config_audio_format"], "mp3")
        self.assertEqual(request.voice, "nova")
        self.assertEqual(request.style_id, "casual")
        self.assertEqual(request.speed, 0.9)
        self.assertEqual(request.language, "zh")
        self.assertEqual(result.provider, "capture")
        reloaded = store.load_project(session_id)
        assert reloaded.artifact is not None
        self.assertEqual(reloaded.artifact.voice_settings["voice_id"], "casual_chat")

    def test_render_audio_uses_explicit_voice_studio_settings_over_saved_default(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote", voice="onyx", audio_format="wav"))
        session_id = self.seed_script_project(store)
        loaded = store.load_project(session_id)
        assert loaded.artifact is not None
        loaded.artifact.voice_settings = {"voice_id": "casual_chat", "style_id": "casual", "speed": 0.9}
        store.save_project(loaded)
        captured: dict[str, object] = {}

        class CapturingProvider:
            def synthesize(self, request):  # type: ignore[no-untyped-def]
                captured["request"] = request
                return TTSGenerationResponse(
                    audio_bytes=b"explicit-voice-audio",
                    file_extension=request.audio_format,
                    provider_name="capture",
                    model_name="capture-model",
                )

        with patch("app.orchestration.audio_rendering.build_tts_provider", return_value=CapturingProvider()):
            service.render_audio(
                session_id,
                settings=VoiceRenderSettings(
                    voice_id="deep_story",
                    voice_name="低沉故事感",
                    style_id="story",
                    style_name="故事感",
                    speed=0.8,
                    language="zh",
                    audio_format="wav",
                ),
            )

        request = captured["request"]
        self.assertEqual(request.voice, "echo")
        self.assertEqual(request.style_id, "story")
        self.assertEqual(request.speed, 0.8)
        reloaded = store.load_project(session_id)
        assert reloaded.artifact is not None
        self.assertEqual(reloaded.artifact.voice_settings["voice_id"], "deep_story")



    def test_local_mlx_render_maps_voice_studio_preset_to_qwen_voice(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model"))
        session_id = self.seed_script_project(store)
        captured: dict[str, object] = {}

        class CapturingProvider:
            def synthesize(self, request):  # type: ignore[no-untyped-def]
                captured["request"] = request
                return TTSGenerationResponse(
                    audio_bytes=b"local-audio",
                    file_extension=request.audio_format,
                    provider_name="local_mlx",
                    model_name="mlx-voice",
                )

        def build_provider(config):  # type: ignore[no-untyped-def]
            captured["config_voice"] = config.voice
            return CapturingProvider()

        with patch("app.orchestration.audio_rendering.build_tts_provider", side_effect=build_provider):
            service.render_audio(
                session_id,
                settings=VoiceRenderSettings(
                    voice_id="deep_story",
                    style_id="story",
                    speed=0.8,
                    language="zh",
                    audio_format="wav",
                ),
            )

        request = captured["request"]
        self.assertEqual(captured["config_voice"], "Uncle_Fu")
        self.assertEqual(request.voice, "Uncle_Fu")
        self.assertEqual(request.style_id, "story")
        self.assertEqual(request.speed, 0.8)
        self.assertEqual(request.language, "zh")

    def test_delete_generated_audio_removes_files_and_clears_artifact_audio(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session_id = self.seed_script_project(store)
        result = service.render_audio(session_id)
        audio_path = Path(result.audio_path)
        transcript_path = Path(result.transcript_path)
        self.assertTrue(audio_path.exists())
        self.assertTrue(transcript_path.exists())

        project = service.delete_generated_audio(session_id)

        self.assertFalse(audio_path.exists())
        self.assertFalse(transcript_path.exists())
        assert project.artifact is not None
        self.assertEqual(project.artifact.audio_path, "")
        self.assertEqual(project.artifact.transcript_path, "")
        self.assertEqual(project.artifact.provider, "")
        self.assertEqual(project.artifact.final_take_id, "")

    def test_delete_voice_take_removes_take_files_and_clears_final_audio(self) -> None:
        store, config_store, _, service = self.build_environment()
        config_store.save_tts_config(TTSProviderConfig(provider="mock_remote"))
        session_id = self.seed_script_project(store)
        take_result = service.render_voice_take(
            session_id,
            settings=VoiceRenderSettings(voice_id="casual_chat", style_id="casual"),
        )
        audio_path = Path(take_result.take.audio_path)
        transcript_path = Path(take_result.take.transcript_path)
        self.assertTrue(audio_path.exists())
        self.assertTrue(transcript_path.exists())

        project = service.delete_voice_take(session_id, take_result.take.take_id)

        self.assertFalse(audio_path.exists())
        self.assertFalse(transcript_path.exists())
        assert project.artifact is not None
        self.assertEqual(project.artifact.takes, [])
        self.assertEqual(project.artifact.final_take_id, "")
        self.assertEqual(project.artifact.audio_path, "")

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
