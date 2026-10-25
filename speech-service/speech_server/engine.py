import asyncio
import gc
import hashlib
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

from .audio import WavSplicer, trim_silence
from .config import CLONE_MODELS, KOKORO, Settings
from .text import split_text

log = logging.getLogger(__name__)

# Qwen3-TTS codec rate; references are decoded straight to it.
CLONE_SAMPLE_RATE = 24000
# Which positional argument is an uploaded file the worker must delete.
UPLOAD_ARG = {"asr": 0, "clone": 2}


def discard_upload(operation: str, args: tuple):
    if operation in UPLOAD_ARG:
        Path(args[UPLOAD_ARG[operation]]).unlink(missing_ok=True)


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

    def load(self, model_id: str):
        if model_id not in self.models:
            if self.settings.single_resident:
                self.unload()
            self.memory_guard()
            log.info("Loading %s", model_id)
            if model_id == self.settings.asr_model:
                from mlx_audio.stt import load

                model = load(model_id)
            else:
                from mlx_audio.tts.utils import load_model

                model = load_model(model_id)
            self.mx.eval(model.parameters())
            self.models[model_id] = model
        self.memory_guard()
        return self.models[model_id]

    def tts(self, text: str, voice: str, seed: int) -> tuple[np.ndarray, int]:
        model = self.load(self.settings.tts_model)
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
        return self._collect(outputs, token_limited=self.settings.tts_model != KOKORO)

    def clone(
        self,
        text: str,
        model_id: str,
        reference: np.ndarray,
        reference_text: str,
        language: str,
        seed: int,
    ) -> tuple[np.ndarray, int]:
        model = self.load(model_id)
        if int(model.sample_rate) != CLONE_SAMPLE_RATE:
            raise ServiceError(502, "Clone model sample rate does not match the decoded reference")
        tokenizer = getattr(model, "speech_tokenizer", None)
        if tokenizer is None or not tokenizer.has_encoder:
            # Without the codec encoder mlx-audio silently degrades to a speaker embedding.
            raise ServiceError(502, "This model cannot encode reference audio; cloning unavailable")
        self.mx.random.seed(seed)
        outputs = model.generate(
            text=text,
            ref_audio=self.mx.array(reference),
            ref_text=reference_text,
            lang_code=language,
            max_tokens=self.settings.tts_max_tokens,
            temperature=0.7,
            verbose=False,
        )
        return self._collect(outputs, token_limited=True)

    def _collect(self, outputs, *, token_limited: bool) -> tuple[np.ndarray, int]:
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
                if token_limited and result.token_count >= self.settings.tts_max_tokens:
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
        model = self.load(self.settings.asr_model)
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
        # Decoded clone reference keyed by upload hash; every segment re-sends the same
        # reference, so decode it once. Worker-thread only; holds just the latest reference.
        self.reference_cache: dict[str, np.ndarray] = {}
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
        loaded = set(state["loaded"])
        return {
            "status": "ok",
            "busy": self.busy,
            "waiting": self.waiting,
            "models": {
                "tts": {"id": self.settings.tts_model, "loaded": self.settings.tts_model in loaded},
                "asr": {"id": self.settings.asr_model, "loaded": self.settings.asr_model in loaded},
                "clone": [{"id": model, "loaded": model in loaded} for model in CLONE_MODELS],
            },
            "clone_reference": {
                "min_seconds": self.settings.clone_min_seconds,
                "max_seconds": self.settings.clone_max_seconds,
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
            elif operation == "clone":
                return self._clone(*args, stop=stop)
            elif operation == "asr":
                return self._transcribe(*args, stop=stop)
        finally:
            discard_upload(operation, args)
            if self.backend:
                self.backend.cleanup()
                self._snapshot()

    async def run(self, operation: str, *args):
        if self.closed:
            discard_upload(operation, args)
            raise ServiceError(503, "Service is shutting down")
        self.waiting += 1
        try:
            try:
                await asyncio.wait_for(self.gpu_semaphore.acquire(), self.settings.queue_timeout)
            except TimeoutError as exc:
                raise ServiceError(503, "GPU queue timed out; retry later") from exc
        except BaseException:
            discard_upload(operation, args)
            raise
        finally:
            self.waiting -= 1
        if self.closed:
            self.gpu_semaphore.release()
            discard_upload(operation, args)
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
            discard_upload(operation, args)
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
            if stop.is_set() and error is None and operation in ("tts", "clone"):
                Path(done.result()[0]).unlink(missing_ok=True)

        future.add_done_callback(finished)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            stop.set()
            if future.done() and not future.cancelled() and future.exception() is None:
                if operation in ("tts", "clone"):
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
        return self._splice(text, lambda chunk: self.backend.tts(chunk, voice, seed), stop)

    def _clone(
        self,
        text: str,
        model_id: str,
        source: Path,
        reference_text: str,
        language: str,
        seed: int,
        *,
        stop,
    ):
        self._check_stop(stop)
        reference = self._reference(source)
        return self._splice(
            text,
            lambda chunk: self.backend.clone(
                chunk, model_id, reference, reference_text, language, seed
            ),
            stop,
        )

    def _reference(self, source: Path) -> np.ndarray:
        """Decode to 24 kHz mono, trim edge silence, and enforce the cloning window."""
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest in self.reference_cache:
            return self.reference_cache[digest]
        with tempfile.TemporaryDirectory(prefix="local-clone-") as folder:
            decoded = self._decode(source, CLONE_SAMPLE_RATE, Path(folder))
            reference, _ = sf.read(decoded, dtype="float32")
        try:
            reference = trim_silence(reference, CLONE_SAMPLE_RATE)
        except RuntimeError as exc:
            raise ServiceError(422, "Reference audio is silent or invalid") from exc
        seconds = len(reference) / CLONE_SAMPLE_RATE
        low, high = self.settings.clone_min_seconds, self.settings.clone_max_seconds
        if not low <= seconds <= high:
            raise ServiceError(
                422,
                f"Reference speech is {seconds:.1f}s; voice cloning needs {low:g}-{high:g}s "
                "of clean speech with its exact transcript",
            )
        self.reference_cache = {digest: reference}
        return reference

    def _splice(self, text: str, render, stop):
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
                audio, sr = render(chunk.text)
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

    def _decode(self, source: Path, sample_rate: int, folder: Path) -> Path:
        """Decode the first audio stream to mono PCM16 WAV at sample_rate."""
        decoded = folder / "decoded.wav"
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
            str(sample_rate),
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
            raise ServiceError(422, "Cannot decode audio; upload a valid wav/mp3/m4a file") from exc
        return decoded

    def _transcribe(self, source: Path, language: str | None, *, stop):
        # Route transfers ownership of source to the worker; cancellation cannot
        # delete an input file while FFmpeg / native inference is still using it.
        try:
            self._check_stop(stop)
            with tempfile.TemporaryDirectory(prefix="local-asr-") as folder:
                decoded = self._decode(source, 16000, Path(folder))
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
