from pathlib import Path

import numpy as np
import soundfile as sf


def trim_silence(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Trim only quiet edges; retain 20 ms padding to protect consonants."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not len(audio) or not np.all(np.isfinite(audio)):
        raise RuntimeError("Model produced empty or non-finite audio")
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-6:
        raise RuntimeError("Model produced silent audio")
    threshold = max(1e-5, peak * 10 ** (-45 / 20))
    # Frame-wise maximum also retains quiet speech close to an active frame.
    frame = max(1, int(sample_rate * 0.01))
    padded = np.pad(audio, (0, (-len(audio)) % frame))
    active = np.flatnonzero(np.max(np.abs(padded.reshape(-1, frame)), axis=1) > threshold)
    pad = int(sample_rate * 0.02)
    first = max(0, int(active[0]) * frame - pad)
    last = min(len(audio), (int(active[-1]) + 1) * frame + pad)
    return np.clip(audio[first:last], -1, 1).copy()


def crossfade(left: np.ndarray, right: np.ndarray, frames: int) -> np.ndarray:
    frames = min(frames, len(left), len(right))
    if frames < 2:
        return np.concatenate((left, right))
    ramp = np.linspace(0, 1, frames, dtype=np.float32)
    middle = left[-frames:] * (1 - ramp) + right[:frames] * ramp
    return np.concatenate((left[:-frames], middle, right[frames:]))


class WavSplicer:
    """Write incrementally; retain only a 10 ms tail, never the entire response."""

    def __init__(self, path: Path, sample_rate: int, crossfade_ms: float, pause_ms: float):
        self.sample_rate = sample_rate
        self.fade = max(2, round(sample_rate * crossfade_ms / 1000))
        self.pause = round(sample_rate * pause_ms / 1000)
        self.file = sf.SoundFile(path, "w", samplerate=sample_rate, channels=1, subtype="PCM_16")
        self.tail = np.empty(0, dtype=np.float32)
        self.previous_paragraph_end = False

    def add(self, audio: np.ndarray, paragraph_end: bool):
        audio = trim_silence(audio, self.sample_rate)
        if len(self.tail):
            if self.previous_paragraph_end and self.pause:
                # Crossfade both speech/silence edges. Extra overlap samples
                # preserve exactly pause frames of silence between the fades.
                silence = np.zeros(self.pause + 2 * self.fade, dtype=np.float32)
                audio = crossfade(crossfade(self.tail, silence, self.fade), audio, self.fade)
            else:
                audio = crossfade(self.tail, audio, self.fade)
        else:
            n = min(self.fade, len(audio))
            audio[:n] *= np.linspace(0, 1, n, dtype=np.float32)
        keep = min(self.fade, len(audio))
        self.file.write(audio[:-keep])
        self.tail = audio[-keep:].copy()
        self.previous_paragraph_end = paragraph_end

    def close(self):
        if not self.file.closed:
            if len(self.tail):
                self.tail *= np.linspace(1, 0, len(self.tail), dtype=np.float32)
                self.file.write(self.tail)
            self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
