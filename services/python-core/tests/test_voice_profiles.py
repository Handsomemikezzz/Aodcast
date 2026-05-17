from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

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

    def write_silent_wav(self, path: Path, *, seconds: float, sample_rate: int = 24_000) -> None:
        frame_count = int(seconds * sample_rate)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * frame_count)

    def test_bootstrap_creates_builtin_profiles_with_reference_audio(self) -> None:
        _, profile_store = self.build_environment()

        profiles = profile_store.list_profiles()
        built_ins = [profile for profile in profiles if profile.source == "built_in"]

        self.assertEqual(len(built_ins), 2)
        self.assertEqual(
            [profile.voice_profile_id for profile in built_ins],
            ["builtin_warm_knowledge", "builtin_clear_broadcast"],
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

    def test_two_step_profile_creation_uploads_single_sample(self) -> None:
        _, profile_store = self.build_environment()
        source_audio = Path(self.temp_dir.name) / "reference.wav"
        self.write_silent_wav(source_audio, seconds=2)

        profile = profile_store.create_user_profile_metadata(
            name="我的采访音色",
            provider="local_mlx",
            model="mlx-voice",
            language="zh",
            audio_format="wav",
        )
        updated = profile_store.attach_user_profile_sample(
            profile.voice_profile_id,
            source_audio_path=source_audio,
            reference_text="这是一段上传样本的参考文本。",
            audio_format="wav",
        )

        self.assertEqual(updated.voice_profile_id, profile.voice_profile_id)
        self.assertEqual(updated.reference_text, "这是一段上传样本的参考文本。")
        self.assertNotEqual(updated.audio_path, str(source_audio))
        self.assertTrue(Path(updated.audio_path).exists())

    def test_sample_upload_rejects_wav_longer_than_thirty_seconds(self) -> None:
        _, profile_store = self.build_environment()
        source_audio = Path(self.temp_dir.name) / "long-reference.wav"
        self.write_silent_wav(source_audio, seconds=31)
        profile = profile_store.create_user_profile_metadata(name="过长样本")

        with self.assertRaisesRegex(ValueError, "30 seconds"):
            profile_store.attach_user_profile_sample(
                profile.voice_profile_id,
                source_audio_path=source_audio,
                reference_text="这段参考音频太长。",
                audio_format="wav",
            )

    def test_create_user_profile_rejects_oversized_reference_audio(self) -> None:
        artifact_store, profile_store = self.build_environment()
        preview_path = artifact_store.write_preview_audio(b"oversized-audio", "wav")

        with patch("app.storage.voice_profile_store.MAX_REFERENCE_AUDIO_BYTES", 4):
            with self.assertRaisesRegex(ValueError, "too large"):
                profile_store.create_user_profile(
                    name="过大的参考音频",
                    reference_audio_path=str(preview_path),
                    reference_text="这段文本不会被保存。",
                    provider="local_mlx",
                    model="mlx-voice",
                )

    def test_update_user_profile_can_rename_and_change_reference_text(self) -> None:
        artifact_store, profile_store = self.build_environment()
        preview_path = artifact_store.write_preview_audio(b"preview-audio", "wav")
        profile = profile_store.create_user_profile(
            name="原始名称",
            preview_audio_path=str(preview_path),
            reference_text="原始参考文本。",
            provider="local_mlx",
            model="mlx-voice",
        )

        renamed = profile_store.update_profile(profile.voice_profile_id, name="更新后的名称")
        updated = profile_store.update_profile(profile.voice_profile_id, reference_text="更新后的参考文本。")

        self.assertEqual(renamed.name, "更新后的名称")
        self.assertEqual(updated.name, "更新后的名称")
        self.assertEqual(updated.preview_text, "更新后的参考文本。")
        self.assertEqual(profile_store.get_profile(profile.voice_profile_id).preview_text, "更新后的参考文本。")

    def test_delete_user_profile_removes_copied_audio_but_rejects_builtin_delete(self) -> None:
        artifact_store, profile_store = self.build_environment()
        preview_path = artifact_store.write_preview_audio(b"preview-audio", "wav")
        profile = profile_store.create_user_profile(
            name="可删除音色",
            preview_audio_path=str(preview_path),
            settings=VoiceRenderSettings(
                voice_id="warm_narrator",
                style_id="natural",
                preview_text="删除前保存这条试音。",
            ),
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
