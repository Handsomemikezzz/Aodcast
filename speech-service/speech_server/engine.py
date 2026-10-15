import asyncio
import gc
import logging
import os
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Any

import numpy as np
import psutil
import soundfile as sf

from .audio import WavSplicer
from .config import KOKORO, Settings
from .text import split_text

log = logging.getLogger(__name__)


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class InferenceStopped(Exception):
    pass


class MLXBackend:
    """Construct and access exclusively in the one dedicated executor thread."""

    def __init__(self, settings: Settings):
        import mlx.core as mx

        self.mx = mx
        self.settings = settings
        self.models: dict[str, Any] = {}
        mx.set_memory_limit(int(settings.memory_gb * 1024**3))
        mx.set_cache_limit(int(settings.cache_mb * 1024**2))

    def memory_guard(self):
        if psutil.virtual_memory().available < self.settings.min_available_gb * 1024**3:
            raise ServiceError(
                503, "Available system memory is too low; retry after freeing memory"
            )

    def load(self, kind: str):
        if kind not in self.models:
            if self.settings.single_resident:
                self.unload()
            self.memory_guard()
            model_id = self.settings.tts_model if kind == "tts" else self.settings.asr_model
            log.info("Loading %s: %s", kind, model_id)
            if kind == "tts":
                from mlx_audio.tts.utils import load_model

                model = load_model(model_id)
            else:
                from mlx_audio.stt import load

                model = load(model_id)
            self.mx.eval(model.parameters())
            self.models[kind] = model
        self.memory_guard()
        return self.models[kind]

    def tts(self, text: str, voice: str, seed: int) -> tuple[np.ndarray, int]:
        model = self.load("tts")
        self.mx.random.seed(seed)
        if self.settings.tts_model == KOKORO:
            outputs = model.generate(text=text, voice=voice, lang_code=self.settings.language)
        else:
            speakers = {v.lower() for v in model.get_supported_speakers()}
            if voice.lower() not in speakers:
                raise ServiceError(400, f"Unsupported voice; choose one of {sorted(speakers)}")
            outputs = model.generate_custom_voice(
                text=text,
                speaker=voice,
                language=self.settings.language,
                max_tokens=self.settings.tts_max_tokens,
                temperature=0.7,
                verbose=False,
            )
        pieces = []
        sample_rate = None
        samples = 0
        try:
            for result in outputs:
                self.mx.eval(result.audio)
                sr = int(result.sample_rate)
                if sample_rate is not None and sr != sample_rate:
                    raise ServiceError(502, "Model changed sample rate during generation")
                sample_rate = sr
                if (
                    self.settings.tts_model != KOKORO
                    and result.token_count >= self.settings.tts_max_tokens
                ):
                    raise ServiceError(
                        502, "TTS reached token limit; shorten text slices or raise limit"
                    )
                audio = np.array(result.audio, dtype=np.float32).reshape(-1)
                samples += len(audio)
                if samples > sr * 120:
                    raise ServiceError(502, "TTS exceeded the per-slice audio duration limit")
                pieces.append(audio)
        finally:
            outputs.close()
        if not pieces or sample_rate is None:
            raise ServiceError(502, "TTS produced no audio")
        return np.concatenate(pieces), sample_rate

    def asr(self, audio: np.ndarray, language: str | None) -> str:
        model = self.load("asr")
        # numpy audio is already mono 16 kHz; never give the full recording to MLX.
        result = model.generate(
            audio,
            language=language,
            max_tokens=self.settings.asr_max_tokens,
            batch_size=1,
            verbose=False,
        )
        if getattr(result, "generation_tokens", 0) >= self.settings.asr_max_tokens:
            raise ServiceError(502, "ASR reached token limit; reduce ASR_CHUNK_SECONDS")
        return result.text.strip()

    def cleanup(self):
        gc.collect()
        self.mx.synchronize()
        clear = getattr(self.mx, "clear_cache", None) or self.mx.metal.clear_cache
        clear()

    def unload(self):
        self.models.clear()
        self.cleanup()

    def snapshot(self) -> dict:
        return {
            "loaded": list(self.models),
            "metal_active_bytes": self.mx.get_active_memory(),
            "metal_cache_bytes": self.mx.get_cache_memory(),
            "metal_peak_bytes": self.mx.get_peak_memory(),
        }


class SpeechEngine:
    def __init__(self, settings: Settings, backend_factory=MLXBackend):
        self.settings = settings
        self.backend_factory = backend_factory
        self.backend = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx-inference")
        # This single global semaphore is the shared ASR/TTS GPU mutual-exclusion lock.
        # It spans a whole request, including all its serial slices and cleanup.
        self.gpu_semaphore = asyncio.Semaphore(1)
        self.gpu_lock = asyncio.Lock()
        self.last_activity = time.monotonic()
        self.busy = False
        self.waiting = 0
        self.closed = False
        self.worker_future = None
        self.stop_event = None
        self.idle_task = None
        self.state_lock = threading.Lock()
        self.state = {
            "loaded": [],
            "metal_active_bytes": 0,
            "metal_cache_bytes": 0,
            "metal_peak_bytes": 0,
        }

    def touch(self):
        self.last_activity = time.monotonic()

    def _snapshot(self):
        if self.backend:
            with self.state_lock:
                self.state = self.backend.snapshot()

    def health(self) -> dict:
        with self.state_lock:
            state = dict(self.state)
        return {
            "status": "ok",
            "busy": self.busy,
            "waiting": self.waiting,
            "models": {
                "tts": {"id": self.settings.tts_model, "loaded": "tts" in state["loaded"]},
                "asr": {"id": self.settings.asr_model, "loaded": "asr" in state["loaded"]},
            },
            "memory": {
                "rss_bytes": psutil.Process().memory_info().rss,
                "system_available_bytes": psutil.virtual_memory().available,
                **{k: v for k, v in state.items() if k != "loaded"},
                "metal_metrics_note": "Snapshot at the last worker boundary; RSS is live",
            },
            "idle_unload_seconds": self.settings.idle_seconds,
            "single_model_resident": self.settings.single_resident,
        }

    def _work(self, operation: str, args: tuple, stop: threading.Event):
        try:
            if self.backend is None:
                if operation in ("unload", "idle_unload"):
                    return None
                self.backend = self.backend_factory(self.settings)
            if operation in ("unload", "idle_unload"):
                self.backend.unload()
            elif operation == "tts":
                return self._synthesize(*args, stop=stop)
            elif operation == "asr":
                return self._transcribe(*args, stop=stop)
        finally:
            if operation == "asr":
                Path(args[0]).unlink(missing_ok=True)
            if self.backend:
                self.backend.cleanup()
                self._snapshot()

    async def run(self, operation: str, *args):
        if self.closed:
            if operation == "asr":
                Path(args[0]).unlink(missing_ok=True)
            raise ServiceError(503, "Service is shutting down")
        self.waiting += 1
        try:
            try:
                await asyncio.wait_for(self.gpu_semaphore.acquire(), self.settings.queue_timeout)
            except TimeoutError as exc:
                raise ServiceError(503, "GPU queue timed out; retry later") from exc
        except BaseException:
            if operation == "asr":
                Path(args[0]).unlink(missing_ok=True)
            raise
        finally:
            self.waiting -= 1
        if self.closed:
            self.gpu_semaphore.release()
            if operation == "asr":
                Path(args[0]).unlink(missing_ok=True)
            raise ServiceError(503, "Service is shutting down")
        if operation == "idle_unload" and (
            self.waiting or time.monotonic() - self.last_activity < self.settings.idle_seconds
        ):
            # A new request may arrive while wait_for schedules acquire().
            self.gpu_semaphore.release()
            return None
        self.busy = True
        if operation != "idle_unload":
            self.touch()
        stop = threading.Event()
        self.stop_event = stop
        loop = asyncio.get_running_loop()
        try:
            await self.gpu_lock.acquire()
            future = loop.run_in_executor(self.executor, self._work, operation, args, stop)
        except BaseException:
            self.busy = False
            if self.gpu_lock.locked():
                self.gpu_lock.release()
            self.gpu_semaphore.release()
            if operation == "asr":
                Path(args[0]).unlink(missing_ok=True)
            raise
        self.worker_future = future

        def finished(done):
            # Release ONLY when native GPU work has actually finished, even if
            # HTTP cancellation already returned to the caller.
            self.busy = False
            self.worker_future = None
            self.stop_event = None
            self.touch()
            self.gpu_lock.release()
            self.gpu_semaphore.release()
            if done.cancelled():
                return
            error = done.exception()  # Always retrieve abandoned worker exceptions.
            if stop.is_set() and error is None and operation == "tts":
                Path(done.result()[0]).unlink(missing_ok=True)

        future.add_done_callback(finished)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            stop.set()
            if future.done() and not future.cancelled() and future.exception() is None:
                if operation == "tts":
                    Path(future.result()[0]).unlink(missing_ok=True)
            raise

    async def start(self):
        self.idle_task = asyncio.create_task(self._idle_loop())

    async def _idle_loop(self):
        interval = min(30, max(0.1, self.settings.idle_seconds / 3))
        while True:
            await asyncio.sleep(interval)
            # No await between checking busy/waiting and acquiring the semaphore.
            with self.state_lock:
                loaded = bool(self.state["loaded"])
            if (
                loaded
                and not self.busy
                and not self.waiting
                and time.monotonic() - self.last_activity >= self.settings.idle_seconds
            ):
                log.info("Idle timeout reached; unloading model weights")
                await self.run("idle_unload")

    async def close(self):
        self.closed = True
        if self.idle_task:
            self.idle_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.idle_task
        if self.stop_event:
            self.stop_event.set()
        if self.worker_future:
            with suppress(Exception):
                await asyncio.shield(self.worker_future)
        if self.backend:
            await asyncio.get_running_loop().run_in_executor(self.executor, self.backend.unload)
        self.executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _check_stop(stop):
        if stop.is_set():
            raise InferenceStopped("Request cancelled at a safe slice boundary")

    def _synthesize(self, text: str, voice: str, seed: int, *, stop):
        chunks = split_text(text)
        if not chunks:
            raise ServiceError(400, "input must contain non-whitespace text")
        handle, name = tempfile.mkstemp(suffix=".wav", prefix="local-speech-")
        os.close(handle)
        path = Path(name)
        writer = None
        try:
            for index, chunk in enumerate(chunks):
                self._check_stop(stop)
                audio, sr = self.backend.tts(chunk.text, voice, seed)
                self._snapshot()
                if writer is None:
                    writer = WavSplicer(
                        path, sr, self.settings.crossfade_ms, self.settings.pause_ms
                    )
                elif writer.sample_rate != sr:
                    raise ServiceError(502, "Model changed sample rate between slices")
                writer.add(audio, chunk.paragraph_end)
                del audio
                self.backend.cleanup()
                self._snapshot()
                log.info(
                    "TTS slice %d/%d complete (%d chars)", index + 1, len(chunks), len(chunk.text)
                )
            self._check_stop(stop)
            writer.close()
            return str(path), len(chunks)
        except BaseException:
            if writer:
                with suppress(Exception):
                    writer.close()
            path.unlink(missing_ok=True)
            raise

    def _transcribe(self, source: Path, language: str | None, *, stop):
        # Route transfers ownership of source to the worker; cancellation cannot
        # delete an input file while FFmpeg / native inference is still using it.
        try:
            self._check_stop(stop)
            with tempfile.TemporaryDirectory(prefix="local-asr-") as folder:
                decoded = Path(folder) / "decoded.wav"
                command = [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-threads",
                    "1",
                    "-i",
                    str(source),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-t",
                    str(self.settings.max_audio_seconds + 0.1),
                    "-c:a",
                    "pcm_s16le",
                    str(decoded),
                ]
                try:
                    subprocess.run(
                        command,
                        check=True,
                        capture_output=True,
                        timeout=self.settings.ffmpeg_timeout,
                    )
                except FileNotFoundError as exc:
                    raise ServiceError(
                        503, "FFmpeg is required; install it with brew install ffmpeg"
                    ) from exc
                except subprocess.TimeoutExpired as exc:
                    raise ServiceError(422, "Audio decoding timed out") from exc
                except subprocess.CalledProcessError as exc:
                    raise ServiceError(
                        422, "Cannot decode audio; upload a valid wav/mp3/m4a file"
                    ) from exc
                self._check_stop(stop)
                with sf.SoundFile(decoded) as audio:
                    if (
                        audio.frames == 0
                        or audio.frames / audio.samplerate > self.settings.max_audio_seconds
                    ):
                        raise ServiceError(413, "Audio is empty or exceeds MAX_AUDIO_SECONDS")
                    block = int(self.settings.asr_chunk_seconds * audio.samplerate)
                    parts = []
                    while True:
                        self._check_stop(stop)
                        samples = audio.read(block, dtype="float32")
                        if not len(samples):
                            break
                        parts.append(self.backend.asr(samples, language))
                        del samples
                        self.backend.cleanup()
                        self._snapshot()
                    return "\n".join(p for p in parts if p)
        finally:
            source.unlink(missing_ok=True)
