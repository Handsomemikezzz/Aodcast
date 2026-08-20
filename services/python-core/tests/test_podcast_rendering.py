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
from app.providers.audio_utils import synthesize_sine_wave_bytes
from app.providers.tts_api.base import TTSGenerationResponse
from app.orchestration.audio_rendering import AudioRenderingService, VoiceRenderSettings
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


class PodcastRenderingTests(unittest.TestCase):
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
        configs.save_tts_config(TTSProviderConfig(provider="mock_remote", model="mock-voice", audio_format="wav"))
        return temp, store, configs, artifacts, AudioRenderingService(store, configs, artifacts)

    def seed_project(self, store: ProjectStore) -> tuple[str, str]:
        session = SessionRecord(topic="分段渲染", creation_intent="验证上下文修复")
        session.transition(SessionState.SCRIPT_EDITED)
        script = ScriptRecord(
            session_id=session.session_id,
            final=(
                "第一段内容已经足够完整，可以独立表达一个清楚的判断。"
                "第二段内容同样足够完整，继续解释这个判断为什么重要。"
                "第三段继续说明问题，并且加入一个可以被听众记住的细节。"
                "第四段给出一个足够具体的例子，让抽象内容变得容易理解。"
                "第五段负责克制地收尾，并为听众保留一点继续思考的空间。"
            ),
        )
        store.save_project(SessionProject(session=session, script=script, artifact=ArtifactRecord(session_id=session.session_id)))
        return session.session_id, script.script_id

    def test_full_render_persists_plan_manifest_and_take_lineage(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)

        result = service.render_audio(session_id, script_id=script_id, settings=VoiceRenderSettings())
        loaded = store.load_project_for_script(session_id, script_id)

        self.assertTrue(Path(result.audio_path).is_file())
        self.assertIsNotNone(loaded.speech_plan)
        self.assertIsNotNone(loaded.render_manifest)
        assert loaded.artifact and loaded.speech_plan and loaded.render_manifest
        self.assertEqual(loaded.artifact.takes[-1].speech_plan_id, loaded.speech_plan.plan_id)
        self.assertEqual(loaded.artifact.takes[-1].render_id, loaded.render_manifest.render_id)
        self.assertEqual(len(loaded.render_manifest.segments), len(loaded.speech_plan.segments))
        self.assertTrue(
            store.speech_plan_version_file(
                session_id,
                script_id,
                loaded.speech_plan.plan_id,
            ).is_file()
        )
        self.assertTrue(
            store.render_manifest_version_file(
                session_id,
                script_id,
                loaded.render_manifest.render_id,
            ).is_file()
        )

    def test_regeneration_replaces_b_c_d_and_reuses_outer_segments(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)
        service.render_audio(session_id, script_id=script_id)
        before = store.load_project_for_script(session_id, script_id)
        assert before.speech_plan and before.render_manifest
        target = before.speech_plan.segments[2]
        old_assets = {item.segment_id: item.segment_artifact_id for item in before.render_manifest.segments}

        result = service.regenerate_audio_window_with_cancellation(
            session_id,
            script_id=script_id,
            target_segment_id=target.segment_id,
            expected_plan_id=before.speech_plan.plan_id,
            expected_render_id=before.render_manifest.render_id,
        )
        after = store.load_project_for_script(session_id, script_id)
        assert after.render_manifest
        new_assets = {item.segment_id: item.segment_artifact_id for item in after.render_manifest.segments}

        self.assertEqual(result.affected_segment_ids, tuple(item.segment_id for item in before.speech_plan.segments[1:4]))
        self.assertEqual(old_assets[before.speech_plan.segments[0].segment_id], new_assets[before.speech_plan.segments[0].segment_id])
        self.assertEqual(old_assets[before.speech_plan.segments[4].segment_id], new_assets[before.speech_plan.segments[4].segment_id])
        for item in before.speech_plan.segments[1:4]:
            self.assertNotEqual(old_assets[item.segment_id], new_assets[item.segment_id])
        self.assertEqual(after.render_manifest.parent_render_id, before.render_manifest.render_id)
        self.assertTrue(
            store.render_manifest_version_file(
                session_id,
                script_id,
                before.render_manifest.render_id,
            ).is_file()
        )
        self.assertTrue(all(Path(item.audio_path).is_file() for item in before.render_manifest.segments))

    def test_script_edit_keeps_old_audio_visible_but_blocks_local_regeneration(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)
        service.render_audio(session_id, script_id=script_id)
        edited = store.load_project_for_script(session_id, script_id)
        assert edited.script and edited.speech_plan and edited.render_manifest
        edited.script.save_final(edited.script.final + "这是脚本修改后新增的一句。")
        store.save_project(edited)

        stale = store.load_project_for_script(session_id, script_id)
        assert stale.speech_plan and stale.render_manifest
        self.assertFalse(stale.speech_plan.is_current_for(stale.script.final))
        self.assertTrue(Path(stale.render_manifest.output.audio_path).is_file())
        with self.assertRaisesRegex(ValueError, "script changed"):
            service.regenerate_audio_window_with_cancellation(
                session_id,
                script_id=script_id,
                target_segment_id=stale.speech_plan.segments[0].segment_id,
                expected_plan_id=stale.speech_plan.plan_id,
                expected_render_id=stale.render_manifest.render_id,
            )

    def test_script_edit_during_render_cannot_be_overwritten_by_stale_publication(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)
        original_render = service.podcast_pipeline.render_full

        def render_then_edit(*args, **kwargs):
            result = original_render(*args, **kwargs)
            edited = store.load_project_for_script(session_id, script_id)
            assert edited.script is not None
            edited.script.save_final(edited.script.final + "渲染期间保存的新内容。")
            edited.session.transition(SessionState.SCRIPT_EDITED)
            store.save_project(edited)
            return result

        service.podcast_pipeline.render_full = render_then_edit  # type: ignore[method-assign]
        with self.assertRaisesRegex(RuntimeError, "script changed"):
            service.render_audio(session_id, script_id=script_id)

        loaded = store.load_project_for_script(session_id, script_id)
        assert loaded.script is not None
        self.assertTrue(loaded.script.final.endswith("渲染期间保存的新内容。"))
        self.assertIsNone(loaded.render_manifest)
        self.assertFalse(any((Path(temp.name) / ".local-data" / "exports").rglob("podcast.wav")))

    def test_cancel_after_synthesis_but_before_publish_discards_new_render(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)
        original_render = service.podcast_pipeline.render_full
        cancelled = False

        def render_then_cancel(*args, **kwargs):
            nonlocal cancelled
            result = original_render(*args, **kwargs)
            cancelled = True
            return result

        service.podcast_pipeline.render_full = render_then_cancel  # type: ignore[method-assign]
        with self.assertRaisesRegex(Exception, "cancelled before publication"):
            service.render_audio_with_cancellation(
                session_id,
                script_id=script_id,
                should_cancel=lambda: cancelled,
            )

        loaded = store.load_project_for_script(session_id, script_id)
        self.assertIsNone(loaded.render_manifest)
        self.assertFalse(any((Path(temp.name) / ".local-data" / "exports").rglob("podcast.wav")))

    def test_regeneration_rejects_tampered_reused_segment_audio(self) -> None:
        temp, store, _, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)
        service.render_audio(session_id, script_id=script_id)
        before = store.load_project_for_script(session_id, script_id)
        assert before.speech_plan and before.render_manifest
        parent_render_id = before.render_manifest.render_id
        Path(before.render_manifest.segments[0].audio_path).write_bytes(
            synthesize_sine_wave_bytes(1, frequency=880.0)
        )

        with self.assertRaisesRegex(ValueError, "audio hash changed"):
            service.regenerate_audio_window_with_cancellation(
                session_id,
                script_id=script_id,
                target_segment_id=before.speech_plan.segments[2].segment_id,
                expected_plan_id=before.speech_plan.plan_id,
                expected_render_id=parent_render_id,
            )

        after = store.load_project_for_script(session_id, script_id)
        assert after.render_manifest
        self.assertEqual(after.render_manifest.render_id, parent_render_id)

    def test_local_segments_chain_previous_audio_as_real_generation_context(self) -> None:
        temp, store, configs, _, service = self.build_environment()
        self.addCleanup(temp.cleanup)
        session_id, script_id = self.seed_project(store)
        configs.save_tts_config(
            TTSProviderConfig(
                provider="local_mlx",
                model="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
                audio_format="wav",
            )
        )
        requests = []

        class CapturingProvider:
            def synthesize(self, request):
                requests.append(request)
                return TTSGenerationResponse(
                    audio_bytes=synthesize_sine_wave_bytes(1),
                    file_extension="wav",
                    provider_name="local_mlx",
                    model_name="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
                    adapter_version="speech-plan-v1",
                    sample_rate_hz=22_050,
                    channels=1,
                )

        with patch(
            "app.orchestration.podcast_rendering.build_tts_provider",
            return_value=CapturingProvider(),
        ):
            service.render_audio(session_id, script_id=script_id)

        self.assertGreater(len(requests), 1)
        self.assertEqual(requests[0].reference_audio_path, "")
        for previous, current in zip(requests, requests[1:]):
            self.assertTrue(Path(current.reference_audio_path).is_file())
            self.assertEqual(current.reference_text, previous.script_text)
            self.assertEqual(current.clone_mode, "ultimate")


if __name__ == "__main__":
    unittest.main()
