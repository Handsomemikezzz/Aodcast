"""Persistent MLX TTS worker subprocess.

This module is launched as ``python -m app.providers.tts_local_mlx.mlx_worker``
by :mod:`app.providers.tts_local_mlx.worker_client`. It loads the requested
MLX model **once** and then services JSON-line jobs on stdin, streaming
per-chunk progress events back on stdout. The parent process owns chunking
and final audio assembly; this worker is intentionally thin so unit tests can
swap in a stub worker script without importing MLX.

Protocol (one JSON object per line, newline terminated):

- stdin requests:
    ``{"type": "synthesize", "job_id": str, "chunks": [str, ...], "voice": str,
       "audio_format": str, "ref_audio": str | None, "model": str,
       "output_dir": str}``
    ``{"type": "cancel", "job_id": str}``
    ``{"type": "shutdown"}``

- stdout events:
    ``{"type": "ready", "pid": int, "model": str}``
    ``{"type": "chunk_started", "job_id": str, "index": int, "total": int}``
    ``{"type": "chunk_done", "job_id": str, "index": int, "total": int,
       "wav_path": str, "duration_seconds": float, "elapsed_ms": int}``
    ``{"type": "done", "job_id": str, "audio_path": str,
       "file_extension": str, "chunks_total": int, "sample_rate": int}``
    ``{"type": "cancelled", "job_id": str}``
    ``{"type": "error", "job_id": str | None, "message": str, "stage": str}``

Every event is flushed immediately so the parent can update UI progress in
near real time.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

# Honour the resource cap the parent sets so the child does not monopolise
# the machine. Values are conservative defaults suitable for Apple Silicon
# unified memory; the worker client may override them via the environment.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")


def _emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class WorkerShutdown(Exception):
    """Raised to unwind the worker main loop cleanly."""


class MlxTtsWorker:
    def __init__(self, model_target: str) -> None:
        self.model_target = model_target
        self._model: Any | None = None
        self._sample_rate: int = 24_000
        self._cancel_lock = threading.Lock()
        self._cancel_job: str | None = None

    def load_model(self) -> None:
        from mlx_audio.tts.utils import load_model  # type: ignore

        self._model = load_model(model_path=self.model_target)
        sample_rate = getattr(self._model, "sample_rate", None)
        if isinstance(sample_rate, int) and sample_rate > 0:
            self._sample_rate = sample_rate

    def _should_cancel(self, job_id: str) -> bool:
        with self._cancel_lock:
            return self._cancel_job == job_id

    def request_cancel(self, job_id: str) -> None:
        with self._cancel_lock:
            self._cancel_job = job_id

    def clear_cancel(self) -> None:
        with self._cancel_lock:
            self._cancel_job = None

    def synthesize_job(self, job: dict[str, Any]) -> None:
        import numpy as np  # type: ignore
        from mlx_audio.audio_io import write as audio_write  # type: ignore

        job_id = str(job.get("job_id") or "")
        chunks = job.get("chunks") or []
        if not isinstance(chunks, list) or not chunks:
            _emit({"type": "error", "job_id": job_id, "stage": "validate", "message": "No chunks provided."})
            return
        voice = str(job.get("voice") or "")
        audio_format = str(job.get("audio_format") or "wav").lstrip(".").lower()
        ref_audio = job.get("ref_audio") or None
        output_dir = Path(str(job.get("output_dir") or "."))
        output_dir.mkdir(parents=True, exist_ok=True)

        if self._model is None:
            self.load_model()
        assert self._model is not None

        total = len(chunks)
        segment_paths: list[Path] = []

        for index, raw_text in enumerate(chunks):
            text = str(raw_text or "").strip()
            if not text:
                continue
            if self._should_cancel(job_id):
                _emit({"type": "cancelled", "job_id": job_id})
                self.clear_cancel()
                return

            _emit({"type": "chunk_started", "job_id": job_id, "index": index, "total": total})
            started_at = time.monotonic()
            try:
                wav_path = self._synthesize_chunk(
                    index=index,
                    text=text,
                    voice=voice,
                    audio_format=audio_format,
                    ref_audio=ref_audio,
                    output_dir=output_dir,
                    audio_write=audio_write,
                    np=np,
                )
            except Exception as exc:  # pragma: no cover - guarded in tests via stub worker
                _emit(
                    {
                        "type": "error",
                        "job_id": job_id,
                        "stage": f"synthesize_chunk:{index}",
                        "message": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(limit=6),
                    }
                )
                self.clear_cancel()
                return

            segment_paths.append(wav_path)
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            duration_seconds = self._probe_duration_seconds(wav_path, np=np)
            _emit(
                {
                    "type": "chunk_done",
                    "job_id": job_id,
                    "index": index,
                    "total": total,
                    "wav_path": str(wav_path),
                    "elapsed_ms": elapsed_ms,
                    "duration_seconds": duration_seconds,
                }
            )

        if self._should_cancel(job_id):
            _emit({"type": "cancelled", "job_id": job_id})
            self.clear_cancel()
            return

        final_path = self._join_segments(
            output_dir=output_dir,
            segments=segment_paths,
            audio_format=audio_format,
            np=np,
        )
        _emit(
            {
                "type": "done",
                "job_id": job_id,
                "audio_path": str(final_path),
                "file_extension": audio_format,
                "chunks_total": total,
                "sample_rate": self._sample_rate,
            }
        )
        self.clear_cancel()

    def _synthesize_chunk(
        self,
        *,
        index: int,
        text: str,
        voice: str,
        audio_format: str,
        ref_audio: str | None,
        output_dir: Path,
        audio_write: Any,
        np: Any,
    ) -> Path:
        import mlx.core as mx  # type: ignore

        gen_kwargs: dict[str, Any] = {"text": text}
        if voice:
            gen_kwargs["voice"] = voice
        if ref_audio:
            gen_kwargs["ref_audio"] = ref_audio

        assert self._model is not None
        results = self._model.generate(**gen_kwargs)

        audio_parts: list[Any] = []
        for segment in results:
            audio_parts.append(segment.audio)
        if not audio_parts:
            raise RuntimeError(f"MLX model produced no audio for chunk {index}.")

        joined = mx.concatenate(audio_parts, axis=0) if len(audio_parts) > 1 else audio_parts[0]
        path = output_dir / f"segment_{index:04d}.wav"
        audio_write(str(path), np.asarray(joined), self._sample_rate, format="wav")
        return path

    def _join_segments(
        self,
        *,
        output_dir: Path,
        segments: list[Path],
        audio_format: str,
        np: Any,
    ) -> Path:
        from mlx_audio.audio_io import write as audio_write  # type: ignore

        if not segments:
            raise RuntimeError("No synthesized segments to join.")

        suffix = audio_format if audio_format else "wav"
        final_path = output_dir / f"final.{suffix}"

        if len(segments) == 1 and suffix == "wav":
            segments[0].replace(final_path)
            return final_path

        samples = [self._read_pcm(segment, np=np) for segment in segments]
        combined = np.concatenate(samples, axis=0)
        audio_write(str(final_path), combined, self._sample_rate, format=suffix)
        return final_path

    def _read_pcm(self, path: Path, *, np: Any) -> Any:
        import miniaudio  # type: ignore

        with open(path, "rb") as handle:
            raw = handle.read()
        decoded = miniaudio.decode(raw, output_format=miniaudio.SampleFormat.SIGNED16)
        arr = np.frombuffer(decoded.samples, dtype=np.int16)
        if decoded.nchannels > 1:
            arr = arr.reshape(-1, decoded.nchannels)
        return arr

    def _probe_duration_seconds(self, path: Path, *, np: Any) -> float:
        try:
            samples = self._read_pcm(path, np=np)
            if samples.ndim == 1:
                frames = samples.shape[0]
            else:
                frames = samples.shape[0]
            return float(frames) / float(self._sample_rate or 1)
        except Exception:
            return 0.0


def _main() -> int:
    parser = argparse.ArgumentParser(description="Persistent MLX TTS worker.")
    parser.add_argument("--model", required=True, help="Model path or HF repo id.")
    parser.add_argument(
        "--lazy-load",
        action="store_true",
        help="Postpone model load until the first job (useful for tests).",
    )
    args = parser.parse_args()

    worker = MlxTtsWorker(args.model)
    if not args.lazy_load:
        try:
            worker.load_model()
        except Exception as exc:
            _emit(
                {
                    "type": "error",
                    "stage": "load_model",
                    "message": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=8),
                }
            )
            return 2

    _emit({"type": "ready", "pid": os.getpid(), "model": args.model})

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _emit({"type": "error", "stage": "decode", "message": f"Invalid JSON line: {exc}"})
            continue

        kind = str(message.get("type") or "")
        try:
            if kind == "synthesize":
                worker.synthesize_job(message)
            elif kind == "cancel":
                worker.request_cancel(str(message.get("job_id") or ""))
            elif kind == "shutdown":
                break
            else:
                _emit({"type": "error", "stage": "dispatch", "message": f"Unknown message type: {kind}"})
        except WorkerShutdown:
            break
        except Exception as exc:
            _emit(
                {
                    "type": "error",
                    "stage": f"dispatch:{kind}",
                    "message": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=8),
                }
            )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
