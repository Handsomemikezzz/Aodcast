"""Client for the persistent MLX TTS worker.

The client owns a long-lived worker subprocess, keeps the MLX model hot
across renders, and streams chunk-level progress events back to the
orchestration layer. The subprocess itself is implemented in
:mod:`app.providers.tts_local_mlx.mlx_worker`.

Key responsibilities:

- lazily start the worker on first render, keep it alive afterwards
- pipe one synthesize job at a time over newline-delimited JSON
- drain stdout on a background thread and push events into a queue
- surface structured events to callers via an ``on_event`` callback
- cooperate with cancellation, falling back to hard kill after a timeout
- recover from worker crashes by restarting on the next synthesize call
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "WorkerEvent",
    "WorkerClient",
    "MLXWorkerError",
    "MLXWorkerCancelled",
    "build_worker_command",
    "worker_environment",
]

_READY_TIMEOUT_SECONDS = 300.0
_SHUTDOWN_TIMEOUT_SECONDS = 5.0
_CANCEL_GRACE_SECONDS = 3.0


class MLXWorkerError(RuntimeError):
    """Raised when the worker emits a terminal error for a job."""


class MLXWorkerCancelled(RuntimeError):
    """Raised when a job terminated because cancellation was requested."""


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    type: str
    payload: dict[str, object]

    def get_str(self, key: str, default: str = "") -> str:
        value = self.payload.get(key)
        return value if isinstance(value, str) else default

    def get_int(self, key: str, default: int = 0) -> int:
        value = self.payload.get(key)
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            return int(value)
        return default


@dataclass(slots=True)
class _JobContext:
    job_id: str
    total_chunks: int
    on_event: Callable[[WorkerEvent], None] | None = None
    done_event: threading.Event = field(default_factory=threading.Event)
    outcome: dict[str, object] | None = None
    error: BaseException | None = None


def build_worker_command(python_executable: str | None = None) -> list[str]:
    exe = python_executable or sys.executable
    return [exe, "-u", "-m", "app.providers.tts_local_mlx.mlx_worker"]


def worker_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("MKL_NUM_THREADS", "2")
    env.setdefault("VECLIB_MAXIMUM_THREADS", "2")
    env.setdefault("NUMEXPR_NUM_THREADS", "2")
    if extra:
        env.update(extra)
    return env


class WorkerClient:
    """Manage a persistent MLX worker and funnel one job at a time to it."""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        command_factory: Callable[[], list[str]] | None = None,
        popen_factory: Callable[..., subprocess.Popen[str]] | None = None,
        niceness: int = 10,
    ) -> None:
        self._python_executable = python_executable or sys.executable
        self._command_factory = command_factory or (
            lambda: build_worker_command(self._python_executable)
        )
        self._popen_factory = popen_factory or subprocess.Popen
        self._niceness = niceness
        self._current_model: str | None = None
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._event_queue: queue.Queue[WorkerEvent | None] = queue.Queue()
        self._submit_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._current_job: _JobContext | None = None
        self._ready_event = threading.Event()
        self._shutdown = False

    # Public API ---------------------------------------------------------

    def is_running(self) -> bool:
        with self._state_lock:
            return self._process is not None and self._process.poll() is None

    def synthesize(
        self,
        *,
        model: str,
        chunks: Iterable[str],
        voice: str,
        audio_format: str,
        output_dir: Path,
        ref_audio: str | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_event: Callable[[WorkerEvent], None] | None = None,
    ) -> dict[str, object]:
        chunk_list = [str(item) for item in chunks if str(item).strip()]
        if not chunk_list:
            raise ValueError("synthesize requires at least one non-empty chunk.")
        total = len(chunk_list)

        with self._submit_lock:
            self._ensure_worker(model)
            job_id = uuid.uuid4().hex
            ctx = _JobContext(job_id=job_id, total_chunks=total, on_event=on_event)
            with self._state_lock:
                self._current_job = ctx

            request = {
                "type": "synthesize",
                "job_id": job_id,
                "chunks": chunk_list,
                "voice": voice,
                "audio_format": audio_format,
                "ref_audio": ref_audio,
                "model": model,
                "output_dir": str(output_dir),
            }
            self._send(request)

            try:
                self._wait_for_job(ctx, should_cancel=should_cancel)
            finally:
                with self._state_lock:
                    if self._current_job is ctx:
                        self._current_job = None

            if ctx.error is not None:
                raise ctx.error
            if ctx.outcome is None:
                raise MLXWorkerError("Worker finished without producing a result payload.")
            return ctx.outcome

    def shutdown(self) -> None:
        with self._submit_lock:
            with self._state_lock:
                self._shutdown = True
                process = self._process
                reader_thread = self._reader_thread
            if process is None:
                return
            try:
                self._send({"type": "shutdown"})
            except Exception:
                pass
            self._terminate_process(process, grace_seconds=_SHUTDOWN_TIMEOUT_SECONDS)
            if reader_thread is not None:
                reader_thread.join(timeout=2.0)
            with self._state_lock:
                self._process = None
                self._reader_thread = None
                self._ready_event.clear()
                self._current_model = None
                self._shutdown = False

    # Worker lifecycle ---------------------------------------------------

    def _ensure_worker(self, model: str) -> None:
        with self._state_lock:
            needs_restart = (
                self._process is None
                or self._process.poll() is not None
                or self._current_model != model
            )
        if not needs_restart:
            return
        self._restart_worker(model)

    def _restart_worker(self, model: str) -> None:
        self._stop_worker_locked()
        command = self._command_factory()
        env = worker_environment({"AODCAST_MLX_WORKER_MODEL": model})
        preexec = _build_preexec(self._niceness)
        kwargs: dict[str, object] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
            "env": env,
        }
        if preexec is not None:
            kwargs["preexec_fn"] = preexec
        process = self._popen_factory(command + ["--model", model], **kwargs)
        reader_thread = threading.Thread(
            target=self._reader_loop,
            name="mlx-worker-reader",
            args=(process,),
            daemon=True,
        )
        with self._state_lock:
            self._process = process
            self._reader_thread = reader_thread
            self._current_model = model
            self._ready_event = threading.Event()
        reader_thread.start()
        if not self._ready_event.wait(timeout=_READY_TIMEOUT_SECONDS):
            self._terminate_process(process, grace_seconds=_SHUTDOWN_TIMEOUT_SECONDS)
            with self._state_lock:
                self._process = None
                self._reader_thread = None
                self._current_model = None
            raise MLXWorkerError(
                "MLX worker did not become ready before the model-load timeout."
            )

    def _stop_worker_locked(self) -> None:
        with self._state_lock:
            process = self._process
            reader_thread = self._reader_thread
            self._process = None
            self._reader_thread = None
            self._ready_event.clear()
            self._current_model = None
        if process is not None:
            self._terminate_process(process, grace_seconds=_SHUTDOWN_TIMEOUT_SECONDS)
        if reader_thread is not None:
            reader_thread.join(timeout=2.0)

    def _terminate_process(
        self, process: subprocess.Popen[str], *, grace_seconds: float
    ) -> None:
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except Exception:
                    pass
                try:
                    process.wait(timeout=grace_seconds)
                except Exception:
                    pass
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except Exception:
                pass

    # Job dispatch -------------------------------------------------------

    def _wait_for_job(
        self,
        ctx: _JobContext,
        *,
        should_cancel: Callable[[], bool] | None,
    ) -> None:
        cancel_sent = False
        cancel_deadline: float | None = None
        while True:
            if should_cancel is not None and not cancel_sent and should_cancel():
                try:
                    self._send({"type": "cancel", "job_id": ctx.job_id})
                except Exception:
                    pass
                cancel_sent = True
                cancel_deadline = time.monotonic() + _CANCEL_GRACE_SECONDS

            completed = ctx.done_event.wait(timeout=0.2)
            if completed:
                return

            if cancel_sent and cancel_deadline is not None and time.monotonic() > cancel_deadline:
                # Worker ignored the cancel: tear it down so the next job gets
                # a fresh process. We still raise cancellation to the caller.
                self._hard_reset_for_cancellation()
                ctx.error = MLXWorkerCancelled("Local MLX synthesis cancelled.")
                ctx.done_event.set()
                return

    def _hard_reset_for_cancellation(self) -> None:
        with self._state_lock:
            process = self._process
            reader_thread = self._reader_thread
            self._process = None
            self._reader_thread = None
            self._ready_event.clear()
            self._current_model = None
        if process is not None:
            self._terminate_process(process, grace_seconds=1.0)
        if reader_thread is not None:
            reader_thread.join(timeout=1.5)

    def _send(self, payload: dict[str, object]) -> None:
        with self._state_lock:
            process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise MLXWorkerError("MLX worker is not running.")
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        try:
            process.stdin.write(line)
            process.stdin.flush()
        except Exception as exc:
            raise MLXWorkerError(f"Failed to send payload to MLX worker: {exc}") from exc

    # Reader loop --------------------------------------------------------

    def _reader_loop(self, process: subprocess.Popen[str]) -> None:
        stdout = process.stdout
        if stdout is None:
            return
        try:
            for raw in stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    # Non-JSON output (warnings, tqdm etc.) is ignored for
                    # routing but still surfaced as an event so tests can
                    # inspect stray noise if needed.
                    self._dispatch_event(WorkerEvent(type="log", payload={"line": line}))
                    continue
                kind = str(message.get("type") or "")
                event = WorkerEvent(type=kind, payload=dict(message))
                self._dispatch_event(event)
        except Exception:
            pass
        finally:
            self._finalize_job_on_exit(process)

    def _dispatch_event(self, event: WorkerEvent) -> None:
        if event.type == "ready":
            self._ready_event.set()
            return

        job_id = event.get_str("job_id")
        with self._state_lock:
            ctx = self._current_job if self._current_job and self._current_job.job_id == job_id else None

        if ctx and ctx.on_event is not None and event.type in {
            "chunk_started",
            "chunk_done",
            "cancelled",
        }:
            try:
                ctx.on_event(event)
            except Exception:
                pass

        if event.type == "done" and ctx is not None:
            ctx.outcome = dict(event.payload)
            ctx.done_event.set()
        elif event.type == "cancelled" and ctx is not None:
            ctx.error = MLXWorkerCancelled("Local MLX synthesis cancelled.")
            ctx.done_event.set()
        elif event.type == "error" and ctx is not None:
            message = event.get_str("message") or "Unknown MLX worker error."
            ctx.error = MLXWorkerError(message)
            ctx.done_event.set()

    def _finalize_job_on_exit(self, process: subprocess.Popen[str]) -> None:
        try:
            returncode = process.wait(timeout=0.5)
        except Exception:
            returncode = None
        stderr_tail = ""
        if process.stderr is not None:
            try:
                stderr_tail = process.stderr.read() or ""
            except Exception:
                stderr_tail = ""

        with self._state_lock:
            ctx = self._current_job
            if self._process is process:
                self._process = None
                self._reader_thread = None
                self._ready_event.clear()
                self._current_model = None

        if ctx is None or ctx.done_event.is_set():
            return
        message = stderr_tail.strip().splitlines()[-1] if stderr_tail.strip() else (
            f"MLX worker exited unexpectedly (code {returncode})."
        )
        ctx.error = MLXWorkerError(message)
        ctx.done_event.set()


def _build_preexec(niceness: int) -> Callable[[], None] | None:
    if sys.platform == "win32":
        return None

    def _apply() -> None:
        try:
            os.nice(niceness)
        except Exception:
            pass

    return _apply
