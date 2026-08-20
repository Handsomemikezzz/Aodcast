from __future__ import annotations

from dataclasses import dataclass
import io
import math
import wave

import miniaudio  # type: ignore
import numpy as np  # type: ignore

from app.domain.render_manifest import AssemblySpec


@dataclass(frozen=True, slots=True)
class AssembledAudio:
    audio_bytes: bytes
    duration_ms: int


class PodcastAudioAssembler:
    """Normalize provider WAVs into one deterministic podcast master."""

    def __init__(self, spec: AssemblySpec | None = None) -> None:
        self.spec = spec or AssemblySpec(target_rms_dbfs=-19.0)
        if self.spec.audio_format != "wav" or self.spec.sample_width_bits != 16:
            raise ValueError("Podcast assembly currently produces 16-bit WAV only.")

    def normalize_segment(self, audio_bytes: bytes) -> AssembledAudio:
        samples = self._decode(audio_bytes)
        samples = self._edge_fade(samples)
        return self._encode(samples)

    def assemble(
        self,
        segments: list[tuple[bytes, int]],
    ) -> AssembledAudio:
        """Assemble segment assets previously produced by ``normalize_segment``."""

        if not segments:
            raise ValueError("Cannot assemble a podcast without audio segments.")
        # Segment assets are normalized (including their one edge fade) before
        # they are persisted. Assembly must not fade them a second time.
        decoded = [self._decode(audio_bytes) for audio_bytes, _ in segments]
        decoded = self._match_segment_loudness(decoded)
        audible_program = np.concatenate(decoded, axis=0)
        parts: list[np.ndarray] = []
        for samples, (_, pause_after_ms) in zip(decoded, segments, strict=True):
            parts.append(samples)
            if pause_after_ms > 0:
                silence_frames = round(self.spec.sample_rate_hz * min(pause_after_ms, 10_000) / 1000)
                parts.append(np.zeros((silence_frames, self.spec.channels), dtype=np.float32))
        master = np.concatenate(parts, axis=0)
        master = self._normalize_master(master, level_samples=audible_program)
        return self._encode(master)

    def combine_units(self, units: list[tuple[bytes, int]]) -> AssembledAudio:
        """Join raw pieces of one segment; the caller normalizes the result once."""

        return self.assemble(units)

    def _decode(self, audio_bytes: bytes) -> np.ndarray:
        decoded = miniaudio.decode(
            audio_bytes,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=self.spec.channels,
            sample_rate=self.spec.sample_rate_hz,
        )
        samples = np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            raise ValueError("TTS provider returned empty audio.")
        return samples.reshape(-1, self.spec.channels)

    def _edge_fade(self, samples: np.ndarray) -> np.ndarray:
        fade_frames = min(
            samples.shape[0] // 3,
            round(self.spec.sample_rate_hz * self.spec.edge_fade_ms / 1000),
        )
        if fade_frames <= 0:
            return samples
        output = samples.copy()
        fade_in = np.linspace(0.0, 1.0, fade_frames, dtype=np.float32).reshape(-1, 1)
        fade_out = np.linspace(1.0, 0.0, fade_frames, dtype=np.float32).reshape(-1, 1)
        output[:fade_frames] *= fade_in
        output[-fade_frames:] *= fade_out
        return output

    def _match_segment_loudness(self, segments: list[np.ndarray]) -> list[np.ndarray]:
        rms_values = [self._rms(segment) for segment in segments]
        audible = sorted(value for value in rms_values if value > 1e-6)
        if not audible:
            return segments
        target = audible[len(audible) // 2]
        output: list[np.ndarray] = []
        max_gain = 10 ** (3.0 / 20.0)
        min_gain = 1.0 / max_gain
        for samples, rms in zip(segments, rms_values, strict=True):
            gain = 1.0 if rms <= 1e-6 else min(max_gain, max(min_gain, target / rms))
            output.append(np.clip(samples * gain, -1.0, 1.0))
        return output

    def _normalize_master(
        self,
        samples: np.ndarray,
        *,
        level_samples: np.ndarray,
    ) -> np.ndarray:
        # Planned silence is editorial timing, not program level. Measure gain
        # from audible segments only, then apply that gain to the full timeline.
        rms = self._rms(level_samples)
        target_rms = 10 ** (self.spec.target_rms_dbfs / 20.0)
        gain = 1.0 if rms <= 1e-6 else target_rms / rms
        peak = float(np.max(np.abs(level_samples)))
        peak_ceiling = 10 ** (self.spec.peak_ceiling_dbfs / 20.0)
        if peak > 1e-6:
            gain = min(gain, peak_ceiling / peak)
        return np.clip(samples * gain, -1.0, 1.0)

    def _encode(self, samples: np.ndarray) -> AssembledAudio:
        pcm = np.round(np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(self.spec.channels)
            output.setsampwidth(self.spec.sample_width_bits // 8)
            output.setframerate(self.spec.sample_rate_hz)
            output.writeframes(pcm.tobytes())
        duration_ms = max(1, round(samples.shape[0] * 1000 / self.spec.sample_rate_hz))
        return AssembledAudio(audio_bytes=buffer.getvalue(), duration_ms=duration_ms)

    @staticmethod
    def _rms(samples: np.ndarray) -> float:
        if samples.size == 0:
            return 0.0
        return math.sqrt(float(np.mean(np.square(samples, dtype=np.float64))))
