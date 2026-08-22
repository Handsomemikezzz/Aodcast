from __future__ import annotations

import tempfile
import unittest
import shutil
import subprocess
import wave
from pathlib import Path

from app.config import AppConfig
from app.providers.audio_utils import synthesize_sine_wave_bytes
from app.domain.common import sha256_bytes
from app.storage.artifact_store import ArtifactStore
from app.storage.speaker_reference_store import SpeakerReferenceStore


class SpeakerReferenceTests(unittest.TestCase):
    def test_user_reference_is_provider_neutral_and_hashes_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig.from_cwd(Path(tmp))
            artifacts = ArtifactStore(config.data_dir)
            artifacts.bootstrap()
            store = SpeakerReferenceStore(config.data_dir, artifacts)
            store.bootstrap()
            sample = Path(tmp) / "speaker.wav"
            sample.write_bytes(synthesize_sine_wave_bytes(1))

            reference = store.create_user_reference(
                name="我的声音",
                source_audio_path=sample,
                reference_text="这是一段干净的参考录音。",
                language="zh",
            )
            payload = reference.to_dict()

            self.assertEqual(payload["duration_ms"], 1000)
            self.assertEqual(payload["audio_format"], "wav")
            self.assertEqual(Path(reference.audio_path).suffix, ".wav")
            with wave.open(reference.audio_path, "rb") as wav_file:
                self.assertEqual(wav_file.getframerate(), 48_000)
                self.assertEqual(wav_file.getnchannels(), 1)
                self.assertEqual(wav_file.getsampwidth(), 2)
            self.assertEqual(len(str(payload["audio_hash"])), 64)
            self.assertEqual(len(str(payload["reference_hash"])), 64)
            for forbidden in ("provider", "model", "style_id", "speed", "preview_text"):
                self.assertNotIn(forbidden, payload)
            self.assertEqual(store.get_reference(reference.speaker_reference_id), reference)

    def test_updating_audio_creates_an_immutable_blob(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig.from_cwd(Path(tmp))
            artifacts = ArtifactStore(config.data_dir)
            artifacts.bootstrap()
            store = SpeakerReferenceStore(config.data_dir, artifacts)
            store.bootstrap()
            first = Path(tmp) / "first.wav"
            second = Path(tmp) / "second.wav"
            first.write_bytes(synthesize_sine_wave_bytes(1, frequency=220.0))
            second.write_bytes(synthesize_sine_wave_bytes(1, frequency=440.0))
            created = store.create_user_reference(
                name="版本化声音",
                source_audio_path=first,
                reference_text="第一版参考文本。",
            )
            original_path = Path(created.audio_path)
            original_bytes = original_path.read_bytes()

            updated = store.update_reference(
                created.speaker_reference_id,
                source_audio_path=second,
                reference_text="第二版参考文本。",
            )

            self.assertNotEqual(updated.audio_path, created.audio_path)
            self.assertEqual(original_path.read_bytes(), original_bytes)
            self.assertEqual(created.audio_hash, sha256_bytes(original_bytes))
            self.assertEqual(updated.audio_hash, sha256_bytes(Path(updated.audio_path).read_bytes()))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required for MP4 normalization")
    def test_mp4_reference_is_normalized_before_provider_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig.from_cwd(Path(tmp))
            artifacts = ArtifactStore(config.data_dir)
            artifacts.bootstrap()
            store = SpeakerReferenceStore(config.data_dir, artifacts)
            store.bootstrap()
            wav_path = Path(tmp) / "source.wav"
            mp4_path = Path(tmp) / "source.mp4"
            wav_path.write_bytes(synthesize_sine_wave_bytes(1))
            subprocess.run(
                [
                    str(shutil.which("ffmpeg")),
                    "-nostdin",
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(wav_path),
                    "-c:a",
                    "aac",
                    str(mp4_path),
                ],
                check=True,
            )

            reference = store.create_user_reference(
                name="MP4 参考音色",
                source_audio_path=mp4_path,
                reference_text="这段音频最初来自 MP4 容器。",
                audio_format="mp4",
            )

            self.assertEqual(reference.audio_format, "wav")
            self.assertEqual(Path(reference.audio_path).suffix, ".wav")
            with wave.open(reference.audio_path, "rb") as wav_file:
                self.assertEqual(wav_file.getframerate(), 48_000)
                self.assertEqual(wav_file.getnchannels(), 1)
                self.assertEqual(wav_file.getsampwidth(), 2)


if __name__ == "__main__":
    unittest.main()
