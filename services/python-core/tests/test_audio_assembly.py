from __future__ import annotations

import io
import unittest
import wave
from unittest.mock import patch

from app.domain.render_manifest import AssemblySpec
from app.orchestration.audio_assembly import PodcastAudioAssembler
from app.providers.audio_utils import synthesize_sine_wave_bytes


class AudioAssemblyTests(unittest.TestCase):
    @staticmethod
    def _pcm_frames(audio_bytes: bytes) -> bytes:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            return wav_file.readframes(wav_file.getnframes())

    def test_assembler_inserts_planned_pause_and_normalizes_output(self) -> None:
        assembler = PodcastAudioAssembler(AssemblySpec(sample_rate_hz=48_000, channels=1, target_rms_dbfs=-19.0))
        result = assembler.assemble(
            [
                (synthesize_sine_wave_bytes(1), 400),
                (synthesize_sine_wave_bytes(1, frequency=330), 0),
            ]
        )

        with wave.open(io.BytesIO(result.audio_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 48_000)
            self.assertEqual(wav_file.getnchannels(), 1)
            duration = wav_file.getnframes() / wav_file.getframerate()
        self.assertAlmostEqual(duration, 2.4, delta=0.03)
        self.assertEqual(result.duration_ms, round(duration * 1000))

    def test_segment_edge_fade_is_applied_once_before_assembly(self) -> None:
        assembler = PodcastAudioAssembler(AssemblySpec(edge_fade_ms=12))

        with patch.object(assembler, "_edge_fade", wraps=assembler._edge_fade) as edge_fade:
            normalized = assembler.normalize_segment(synthesize_sine_wave_bytes(1))
            assembler.assemble([(normalized.audio_bytes, 0)])

        self.assertEqual(edge_fade.call_count, 1)

    def test_planned_silence_does_not_change_audible_program_gain(self) -> None:
        assembler = PodcastAudioAssembler(
            AssemblySpec(target_rms_dbfs=-19.0, peak_ceiling_dbfs=-1.0)
        )
        normalized = assembler.normalize_segment(synthesize_sine_wave_bytes(1))

        without_pause = assembler.assemble([(normalized.audio_bytes, 0)])
        with_pause = assembler.assemble([(normalized.audio_bytes, 2_000)])

        audible_frames = self._pcm_frames(without_pause.audio_bytes)
        paused_frames = self._pcm_frames(with_pause.audio_bytes)
        self.assertEqual(paused_frames[: len(audible_frames)], audible_frames)
        self.assertGreater(len(paused_frames), len(audible_frames))

    def test_assembly_spec_round_trips_truthful_level_and_fade_fields(self) -> None:
        spec = AssemblySpec(
            target_rms_dbfs=-19.0,
            peak_ceiling_dbfs=-1.5,
            edge_fade_ms=10,
        )

        payload = spec.to_dict()

        self.assertEqual(AssemblySpec.from_dict(payload), spec)
        self.assertNotIn("target_lufs", payload)
        self.assertNotIn("true_peak_dbfs", payload)
        self.assertNotIn("crossfade_ms", payload)


if __name__ == "__main__":
    unittest.main()
