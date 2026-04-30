from __future__ import annotations

import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_local_mlx.chunker import ScriptChunk, split_script_into_chunks
from app.providers.tts_local_mlx.runtime import resolve_local_model_target
from app.providers.tts_local_mlx.worker_client import (
    MLXWorkerCancelled,
    MLXWorkerError,
    WorkerClient,
    WorkerEvent,
)
from app.runtime.task_cancellation import TaskCancellationRequested


@dataclass(frozen=True, slots=True)
class LocalMLXRunResult:
    audio_bytes: bytes
    file_extension: str
    model_name: str
    output_path: str
    chunks_total: int = 0


@dataclass(frozen=True, slots=True)
class ChunkProgressEvent:
    """Public event surfaced to the orchestration layer.

    - ``index`` is 0-based
    - ``total`` is the number of chunks to render
    - ``phase`` is either ``"chunk_started"`` or ``"chunk_done"``
    - ``elapsed_ms``/``duration_seconds`` are best-effort timings
    """

    phase: str
    index: int
    total: int
    elapsed_ms: int = 0
    duration_seconds: float = 0.0


_DEFAULT_CLIENT_LOCK = threading.Lock()
_DEFAULT_CLIENT: WorkerClient | None = None


def get_default_worker_client() -> WorkerClient:
    global _DEFAULT_CLIENT
    with _DEFAULT_CLIENT_LOCK:
        if _DEFAULT_CLIENT is None:
            _DEFAULT_CLIENT = WorkerClient()
        return _DEFAULT_CLIENT


def set_default_worker_client(client: WorkerClient | None) -> None:
    global _DEFAULT_CLIENT
    with _DEFAULT_CLIENT_LOCK:
        _DEFAULT_CLIENT = client


class MLXAudioQwenRunner:
    def __init__(
        self,
        config: TTSProviderConfig,
        *,
        worker_client: WorkerClient | None = None,
        chunker: Callable[[str], list[ScriptChunk]] | None = None,
    ) -> None:
        self.config = config
        self._worker_client = worker_client
        self._chunker = chunker or split_script_into_chunks

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        audio_format: str,
        speed: float = 1.0,
        style_prompt: str = "",
        language: str = "zh",
        reference_audio_path: str = "",
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[ChunkProgressEvent], None] | None = None,
    ) -> LocalMLXRunResult:
        model_target, _ = resolve_local_model_target(self.config)
        file_extension = (self.config.audio_format or audio_format).lstrip(".").lower() or "wav"

        chunks = self._chunker(text)
        if not chunks:
            raise RuntimeError("Local MLX synthesis received empty script content.")

        client = self._worker_client or get_default_worker_client()

        def relay(event: WorkerEvent) -> None:
            if on_progress is None:
                return
            if event.type == "chunk_started":
                on_progress(
                    ChunkProgressEvent(
                        phase="chunk_started",
                        index=event.get_int("index"),
                        total=event.get_int("total"),
                    )
                )
            elif event.type == "chunk_done":
                duration = event.payload.get("duration_seconds")
                on_progress(
                    ChunkProgressEvent(
                        phase="chunk_done",
                        index=event.get_int("index"),
                        total=event.get_int("total"),
                        elapsed_ms=event.get_int("elapsed_ms"),
                        duration_seconds=float(duration) if isinstance(duration, (int, float)) else 0.0,
                    )
                )

        with tempfile.TemporaryDirectory(prefix="aodcast-mlx-tts-") as temp_dir:
            output_dir = Path(temp_dir)
            try:
                outcome = client.synthesize(
                    model=model_target,
                    chunks=[chunk.text for chunk in chunks],
                    voice=voice or self.config.voice,
                    audio_format=file_extension,
                    speed=speed,
                    style_prompt=style_prompt,
                    language=language,
                    output_dir=output_dir,
                    ref_audio=reference_audio_path or self.config.local_ref_audio_path or None,
                    should_cancel=should_cancel,
                    on_event=relay,
                )
            except MLXWorkerCancelled as exc:
                raise TaskCancellationRequested(str(exc)) from exc
            except MLXWorkerError as exc:
                raise RuntimeError(f"mlx-audio generation failed. {exc}") from exc

            audio_path = self._resolve_output_file(outcome, output_dir, file_extension)
            audio_bytes = audio_path.read_bytes()

        return LocalMLXRunResult(
            audio_bytes=audio_bytes,
            file_extension=file_extension,
            model_name=self.config.model,
            output_path=str(audio_path),
            chunks_total=len(chunks),
        )

    def _resolve_output_file(
        self,
        outcome: dict[str, object],
        output_dir: Path,
        file_extension: str,
    ) -> Path:
        raw = outcome.get("audio_path") if isinstance(outcome, dict) else None
        if isinstance(raw, str) and raw:
            candidate = Path(raw)
            if candidate.exists():
                return candidate
        direct = output_dir / f"final.{file_extension}"
        if direct.exists():
            return direct
        matches = sorted(output_dir.glob(f"final.*"))
        if matches:
            return matches[0]
        raise RuntimeError(
            f"MLX worker did not produce an output .{file_extension} file in {output_dir}."
        )
