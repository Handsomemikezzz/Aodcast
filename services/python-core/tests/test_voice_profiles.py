from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import AppConfig
from app.orchestration.audio_rendering import VoiceRenderSettings
from app.storage.artifact_store import ArtifactStore
from app.storage.voice_profile_store import VoiceProfileStore


class VoiceProfileStoreTests(unittest.TestCase):
    def build_environment(self) -> tuple[ArtifactStore, VoiceProfileStore]:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = AppConfig.from_cwd(Path(self.temp_dir.name))
        artifact_store = ArtifactStore(config.data_dir)
        profile_store = VoiceProfileStore(config.data_dir, artifact_store)
        artifact_store.bootstrap()
        profile_store.bootstrap()
        return artifact_store, profile_store

    def tearDown(self) -> None:
        temp_dir = getattr(self, "temp_dir", None)
        if temp_dir is not None:
            temp_dir.cleanup()

    def test_bootstrap_creates_three_builtin_profiles_with_reference_audio(self) -> None:
        _, profile_store = self.build_environment()

        profiles = profile_store.list_profiles()
        built_ins = [profile for profile in profiles if profile.source == "built_in"]

        self.assertEqual(len(built_ins), 3)
        self.assertEqual(
            [profile.voice_profile_id for profile in built_ins],
            ["builtin_warm_knowledge", "builtin_clear_broadcast", "builtin_deep_story"],
        )
        self.assertTrue(all(Path(profile.audio_path).exists() for profile in built_ins))
        self.assertTrue(all(profile.preview_text for profile in built_ins))
        self.assertTrue(
            all("services/python-core/app/assets/voice-profiles" in profile.audio_path for profile in built_ins)
        )
        self.assertEqual(
            {profile.preview_text for profile in built_ins},
            {"Hello, welcome to use Aodcast. What shall we talk about today?"},
        )

    def test_create_user_profile_copies_preview_audio_and_persists_settings(self) -> None:
        artifact_store, profile_store = self.build_environment()
        preview_path = artifact_store.write_preview_audio(b"preview-audio", "wav")

        profile = profile_store.create_user_profile(
            name="我的知识主播",
            preview_audio_path=str(preview_path),
            settings=VoiceRenderSettings(
                voice_id="news_anchor",
                style_id="news",
                speed=0.8,
                language="zh",
                audio_format="wav",
                preview_text="保存这条试音。",
            ),
            provider="local_mlx",
            model="mlx-voice",
        )

        self.assertEqual(profile.source, "user_saved")
        self.assertEqual(profile.name, "我的知识主播")
        self.assertEqual(profile.voice_id, "news_anchor")
        self.assertEqual(profile.preview_text, "保存这条试音。")
        self.assertNotEqual(profile.audio_path, str(preview_path))
        self.assertTrue(Path(profile.audio_path).exists())

        reloaded = profile_store.get_profile(profile.voice_profile_id)
        self.assertEqual(reloaded.to_dict(), profile.to_dict())

    def test_delete_user_profile_removes_copied_audio_but_rejects_builtin_delete(self) -> None:
        artifact_store, profile_store = self.build_environment()
        preview_path = artifact_store.write_preview_audio(b"preview-audio", "wav")
        profile = profile_store.create_user_profile(
            name="可删除音色",
            preview_audio_path=str(preview_path),
            settings=VoiceRenderSettings(voice_id="warm_narrator", style_id="natural"),
            provider="local_mlx",
            model="mlx-voice",
        )
        profile_audio = Path(profile.audio_path)

        deleted = profile_store.delete_profile(profile.voice_profile_id)

        self.assertTrue(deleted)
        self.assertFalse(profile_audio.exists())
        with self.assertRaises(ValueError):
            profile_store.delete_profile("builtin_warm_knowledge")


if __name__ == "__main__":
    unittest.main()
