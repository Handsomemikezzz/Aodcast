"""Persistent MLX TTS worker subprocess.

This module is launched as ``python -m app.providers.tts_local_mlx.mlx_worker``
by :mod:`app.providers.tts_local_mlx.worker_client`. It loads the requested
MLX model **once** and then services JSON-line jobs on stdin, streaming
per-chunk progress events back on stdout. The parent process owns text
segmentation; the worker owns model-specific generation and lossless WAV
assembly so sample rate and channel metadata stay next to the waveform.

Protocol (one JSON object per line, newline terminated):

- stdin requests:
    ``{"type": "synthesize", "job_id": str,
       "segments": [{"text": str, "pause_after_ms": int}, ...],
       "options": object, "leading_silence_ms": int,
       "model": str, "output_dir": str}``
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
import queue
import sys
import threading
import time
import traceback
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.providers.tts_local_mlx.adapters import adapter_for_model
from app.providers.tts_local_mlx.adapters.base import AdapterRequest, PreparedSegment
from app.providers.tts_local_mlx.model_spec import (
    ModelSpec,
    model_spec_from_loaded_model,
    resolve_model_spec,
    validate_loaded_model_spec,
)

# Honour the resource cap the parent sets so the child does not monopolise
# the machine. Values are conservative defaults suitable for Apple Silicon
# unified memory; the worker client may override them via the environment.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")


_EMIT_LOCK = threading.Lock()


def _emit(event: dict[str, Any]) -> None:
    # Control messages are read on a background thread while synthesis stays on
    # the main worker thread. Keep protocol lines atomic if both threads need to
    # report an event at the same time.
    with _EMIT_LOCK:
        sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
        sys.stdout.flush()


class WorkerJobCancelled(Exception):
    """Raised when a running job observes cooperative cancellation."""


@dataclass(frozen=True, slots=True)
class RenderedSegment:
    path: Path
    pause_after_ms: int
    sample_rate_hz: int
    channels: int


class MlxTtsWorker:
    def __init__(self, model_target: str) -> None:
        self.model_target = model_target
        self._model: Any | None = None
        self._model_spec: ModelSpec | None = None
        self._adapter: Any | None = None
        self._sample_rate: int = 24_000
        self._channels: int = 1
        self._cancel_lock = threading.Lock()
        self._cancel_jobs: set[str] = set()

    def load_model(self) -> None:
        from mlx_audio.tts.utils import load_model  # type: ignore

        expected_spec = resolve_model_spec(self.model_target)
        self._model = load_model(model_path=self.model_target)
        actual_spec = model_spec_from_loaded_model(self._model)
        validate_loaded_model_spec(expected_spec, actual_spec)
        self._model_spec = actual_spec
        self._adapter = adapter_for_model(actual_spec)
        sample_rate = getattr(self._model, "sample_rate", actual_spec.sample_rate_hz)
        if isinstance(sample_rate, int) and sample_rate > 0:
            self._sample_rate = sample_rate
        else:
            self._sample_rate = actual_spec.sample_rate_hz
        self._channels = actual_spec.channels

    def _should_cancel(self, job_id: str) -> bool:
        with self._cancel_lock:
            return job_id in self._cancel_jobs

    def request_cancel(self, job_id: str) -> None:
        if not job_id:
            return
        with self._cancel_lock:
            self._cancel_jobs.add(job_id)

    def clear_cancel(self, job_id: str) -> None:
        with self._cancel_lock:
            self._cancel_jobs.discard(job_id)

    def serve(self, input_stream: Iterable[str]) -> None:
        """Serve requests while a reader thread consumes control messages.

        Model generation remains serialized on the calling thread. The reader
        handles ``cancel`` immediately, allowing the active generation loop to
        observe it at the next model-result or text-chunk boundary without
        tearing down the loaded model.
        """

        pending: queue.Queue[dict[str, Any] | None] = queue.Queue()

        def read_requests() -> None:
            try:
                for raw in input_stream:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError as exc:
                        _emit(
                            {
                                "type": "error",
                                "stage": "decode",
                                "message": f"Invalid JSON line: {exc}",
                            }
                        )
                        continue
                    if not isinstance(message, dict):
                        _emit(
                            {
                                "type": "error",
                                "stage": "decode",
                                "message": "Worker requests must be JSON objects.",
                            }
                        )
                        continue
                    if str(message.get("type") or "") == "cancel":
                        self.request_cancel(str(message.get("job_id") or ""))
                        continue
                    pending.put(message)
            finally:
                pending.put(None)

        reader = threading.Thread(
            target=read_requests,
            name="mlx-worker-control-reader",
            daemon=True,
        )
        reader.start()

        while True:
            message = pending.get()
            if message is None:
                break
            kind = str(message.get("type") or "")
            try:
                if kind == "synthesize":
                    self.synthesize_job(message)
                elif kind == "shutdown":
                    break
                else:
                    _emit(
                        {
                            "type": "error",
                            "stage": "dispatch",
                            "message": f"Unknown message type: {kind}",
                        }
                    )
            except Exception as exc:
                _emit(
                    {
                        "type": "error",
                        "job_id": str(message.get("job_id") or ""),
                        "stage": f"dispatch:{kind}",
                        "message": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(limit=8),
                    }
                )

    def synthesize_job(self, job: dict[str, Any]) -> None:
        import numpy as np  # type: ignore
        from mlx_audio.audio_io import write as audio_write  # type: ignore

        job_id = str(job.get("job_id") or "")
        raw_segments = job.get("segments") or []
        if not isinstance(raw_segments, list) or not raw_segments:
            _emit({"type": "error", "job_id": job_id, "stage": "validate", "message": "No segments provided."})
            return
        try:
            segments = [PreparedSegment.from_payload(item) for item in raw_segments]
        except Exception as exc:
            _emit({"type": "error", "job_id": job_id, "stage": "validate", "message": str(exc)})
            return
        raw_options = job.get("options") or {}
        if not isinstance(raw_options, dict):
            _emit({"type": "error", "job_id": job_id, "stage": "validate", "message": "options must be an object."})
            return
        options = AdapterRequest.from_payload(raw_options)
        leading_silence_ms = max(0, int(job.get("leading_silence_ms") or 0))
        output_dir = Path(str(job.get("output_dir") or "."))
        output_dir.mkdir(parents=True, exist_ok=True)

        if self._model is None:
            self.load_model()
        assert self._model is not None
        assert self._adapter is not None
        self._adapter.validate_request(options, ())

        total = len(segments)
        rendered_segments: list[RenderedSegment] = []

        for index, segment in enumerate(segments):
            text = segment.text.strip()
            if not text:
                continue
            if self._should_cancel(job_id):
                _emit({"type": "cancelled", "job_id": job_id})
                self.clear_cancel(job_id)
                return

            _emit({"type": "chunk_started", "job_id": job_id, "index": index, "total": total})
            started_at = time.monotonic()
            try:
                rendered = self._synthesize_segment(
                    job_id=job_id,
                    index=index,
                    text=text,
                    options=options,
                    pause_after_ms=segment.pause_after_ms,
                    output_dir=output_dir,
                    audio_write=audio_write,
                    np=np,
                )
            except WorkerJobCancelled:
                _emit({"type": "cancelled", "job_id": job_id})
                self.clear_cancel(job_id)
                return
            except Exception as exc:  # pragma: no cover - guarded in tests via stub worker
                _emit(
                    {
                        "type": "error",
                        "job_id": job_id,
                        "stage": f"synthesize_segment:{index}",
                        "message": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(limit=6),
                    }
                )
                self.clear_cancel(job_id)
                return

            if self._should_cancel(job_id):
                rendered.path.unlink(missing_ok=True)
                _emit({"type": "cancelled", "job_id": job_id})
                self.clear_cancel(job_id)
                return

            rendered_segments.append(rendered)
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            duration_seconds = self._probe_duration_seconds(
                rendered.path,
                np=np,
                sample_rate=rendered.sample_rate_hz,
                channels=rendered.channels,
            )
            _emit(
                {
                    "type": "chunk_done",
                    "job_id": job_id,
                    "index": index,
                    "total": total,
                    "wav_path": str(rendered.path),
                    "elapsed_ms": elapsed_ms,
                    "duration_seconds": duration_seconds,
                    "sample_rate": rendered.sample_rate_hz,
                    "channels": rendered.channels,
                }
            )

        if self._should_cancel(job_id):
            _emit({"type": "cancelled", "job_id": job_id})
            self.clear_cancel(job_id)
            return

        final_path = self._join_segments(
            output_dir=output_dir,
            segments=rendered_segments,
            leading_silence_ms=leading_silence_ms,
            np=np,
        )
        if self._should_cancel(job_id):
            final_path.unlink(missing_ok=True)
            _emit({"type": "cancelled", "job_id": job_id})
            self.clear_cancel(job_id)
            return
        _emit(
            {
                "type": "done",
                "job_id": job_id,
                "audio_path": str(final_path),
                "file_extension": "wav",
                "chunks_total": total,
                "sample_rate": self._sample_rate,
                "channels": self._channels,
            }
        )
        self.clear_cancel(job_id)

    def _synthesize_segment(
        self,
        *,
        job_id: str,
        index: int,
        text: str,
        options: AdapterRequest,
        pause_after_ms: int,
        output_dir: Path,
        audio_write: Any,
        np: Any,
    ) -> RenderedSegment:
        import mlx.core as mx  # type: ignore

        assert self._model is not None
        assert self._adapter is not None
        results = self._adapter.generate(self._model, text, options)

        audio_parts: list[Any] = []
        sample_rate: int | None = None
        channels: int | None = None
        for segment in results:
            if self._should_cancel(job_id):
                raise WorkerJobCancelled
            audio = segment.audio
            if int(audio.shape[0]) <= 0:
                continue
            result_sample_rate = int(
                getattr(segment, "sample_rate", 0) or self._sample_rate
            )
            result_channels = 1 if audio.ndim == 1 else int(audio.shape[1])
            if audio.ndim not in {1, 2} or result_channels <= 0:
                raise RuntimeError(
                    f"MLX model returned unsupported audio shape {audio.shape}."
                )
            if sample_rate is not None and result_sample_rate != sample_rate:
                raise RuntimeError("MLX model changed sample rate within one segment.")
            if channels is not None and result_channels != channels:
                raise RuntimeError("MLX model changed channel count within one segment.")
            sample_rate = result_sample_rate
            channels = result_channels
            audio_parts.append(audio)
        if not audio_parts:
            raise RuntimeError(f"MLX model produced no audio for segment {index}.")

        joined = mx.concatenate(audio_parts, axis=0) if len(audio_parts) > 1 else audio_parts[0]
        path = output_dir / f"segment_{index:04d}.wav"
        assert sample_rate is not None and channels is not None
        audio_write(str(path), np.asarray(joined), sample_rate, format="wav")
        return RenderedSegment(
            path=path,
            pause_after_ms=max(0, int(pause_after_ms)),
            sample_rate_hz=sample_rate,
            channels=channels,
        )

    def _join_segments(
        self,
        *,
        output_dir: Path,
        segments: list[RenderedSegment],
        leading_silence_ms: int,
        np: Any,
    ) -> Path:
        from mlx_audio.audio_io import write as audio_write  # type: ignore

        if not segments:
            raise RuntimeError("No synthesized segments to join.")

        final_path = output_dir / "final.wav"
        sample_rate = segments[0].sample_rate_hz
        channels = segments[0].channels
        for segment in segments[1:]:
            if segment.sample_rate_hz != sample_rate or segment.channels != channels:
                raise RuntimeError(
                    "Synthesized segments must share a sample rate and channel count."
                )

        if (
            len(segments) == 1
            and leading_silence_ms == 0
            and segments[0].pause_after_ms == 0
        ):
            segments[0].path.replace(final_path)
            self._sample_rate = sample_rate
            self._channels = channels
            return final_path

        samples: list[Any] = []
        if leading_silence_ms:
            samples.append(
                self._silence(
                    leading_silence_ms,
                    sample_rate=sample_rate,
                    channels=channels,
                    np=np,
                )
            )
        for segment in segments:
            samples.append(
                self._read_pcm(
                    segment.path,
                    np=np,
                    sample_rate=sample_rate,
                    channels=channels,
                )
            )
            if segment.pause_after_ms:
                samples.append(
                    self._silence(
                        segment.pause_after_ms,
                        sample_rate=sample_rate,
                        channels=channels,
                        np=np,
                    )
                )
        combined = np.concatenate(samples, axis=0)
        audio_write(str(final_path), combined, sample_rate, format="wav")
        self._sample_rate = sample_rate
        self._channels = channels
        return final_path

    def _read_pcm(
        self,
        path: Path,
        *,
        np: Any,
        sample_rate: int | None = None,
        channels: int | None = None,
    ) -> Any:
        import miniaudio  # type: ignore

        target_sample_rate = sample_rate or self._sample_rate
        target_channels = channels or self._channels
        with open(path, "rb") as handle:
            raw = handle.read()
        decoded = miniaudio.decode(
            raw,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=target_channels,
            sample_rate=target_sample_rate,
        )
        arr = np.frombuffer(decoded.samples, dtype=np.int16)
        if decoded.nchannels > 1:
            arr = arr.reshape(-1, decoded.nchannels)
        return arr

    def _silence(
        self,
        duration_ms: int,
        *,
        sample_rate: int,
        channels: int,
        np: Any,
    ) -> Any:
        frames = max(0, int(round(sample_rate * duration_ms / 1000.0)))
        shape = (frames,) if channels == 1 else (frames, channels)
        return np.zeros(shape, dtype=np.int16)

    def _probe_duration_seconds(
        self,
        path: Path,
        *,
        np: Any,
        sample_rate: int | None = None,
        channels: int | None = None,
    ) -> float:
        try:
            target_sample_rate = sample_rate or self._sample_rate
            samples = self._read_pcm(
                path,
                np=np,
                sample_rate=target_sample_rate,
                channels=channels,
            )
            if samples.ndim == 1:
                frames = samples.shape[0]
            else:
                frames = samples.shape[0]
            return float(frames) / float(target_sample_rate or 1)
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

    worker.serve(sys.stdin)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
