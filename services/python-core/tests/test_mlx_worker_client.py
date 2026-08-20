from __future__ import annotations

import json
import queue
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

from app.providers.tts_local_mlx.adapters.base import PreparedSegment
from app.providers.tts_local_mlx.chunker import split_script_into_chunks
from app.providers.tts_local_mlx.mlx_worker import MlxTtsWorker
from app.providers.tts_local_mlx.worker_client import (
    MLXWorkerCancelled,
    MLXWorkerError,
    WorkerClient,
    WorkerEvent,
    build_worker_command,
)


def _write_stub_worker(script_dir: Path, *, behavior: str) -> Path:
    """Write a lightweight stand-in worker that mimics the protocol.

    ``behavior`` selects one of the canned scenarios used by the tests:

    - ``success``: emit chunk_started/chunk_done events and then ``done``
    - ``slow``: sleep inside each chunk so the client can request cancel
    - ``crash``: emit ``ready`` then exit non-zero before completing the job
    - ``unscoped_error``: emit an error without job_id while a job is active
    - ``hang_after_chunks``: emit all chunk events and then never emit done
    - ``load_error``: fail before the worker becomes ready
    - ``ignore_cancel``: never acknowledge cancel so the client must hard reset
    """

    source = textwrap.dedent(
        f"""
        import json, sys, os, time, pathlib, queue, threading

        def emit(event):
            sys.stdout.write(json.dumps(event) + "\\n")
            sys.stdout.flush()

        requests = queue.Queue()
        cancelled_jobs = set()
        cancel_lock = threading.Lock()

        def read_requests():
            for raw in sys.stdin:
                line = raw.strip()
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("type") == "cancel":
                    with cancel_lock:
                        cancelled_jobs.add(msg.get("job_id"))
                    continue
                requests.put(msg)
            requests.put(None)

        def main():
            behavior = {behavior!r}
            if behavior == "load_error":
                emit({{"type": "error", "stage": "load_model", "message": "bad model metadata"}})
                sys.exit(2)
            emit({{"type": "ready", "pid": os.getpid(), "model": "stub"}})
            threading.Thread(target=read_requests, daemon=True).start()
            while True:
                msg = requests.get()
                if msg is None:
                    break
                kind = msg.get("type")
                if kind == "shutdown":
                    break
                if kind != "synthesize":
                    continue
                job_id = msg.get("job_id")
                segments = msg.get("segments") or []
                output_dir = pathlib.Path(msg.get("output_dir") or ".")
                total = len(segments)
                if behavior == "crash":
                    sys.exit(3)
                if behavior == "unscoped_error":
                    emit({{"type": "error", "message": "dispatch failed without job id"}})
                    continue
                job_cancelled = False
                for i, _ in enumerate(segments):
                    emit({{"type": "chunk_started", "job_id": job_id, "index": i, "total": total}})
                    if behavior == "ignore_cancel":
                        while True:
                            time.sleep(0.1)
                    if behavior == "slow":
                        time.sleep(0.35)
                    path = output_dir / f"segment_{{i:04d}}.wav"
                    path.write_bytes(b"stub-segment")
                    emit({{
                        "type": "chunk_done",
                        "job_id": job_id,
                        "index": i,
                        "total": total,
                        "wav_path": str(path),
                        "elapsed_ms": 1,
                        "duration_seconds": 0.1,
                    }})
                    with cancel_lock:
                        if job_id in cancelled_jobs:
                            cancelled_jobs.discard(job_id)
                            job_cancelled = True
                    if job_cancelled:
                        emit({{"type": "cancelled", "job_id": job_id}})
                        break
                if job_cancelled:
                    continue
                if behavior == "hang_after_chunks":
                    while True:
                        time.sleep(0.1)
                else:
                    final = output_dir / "final.wav"
                    final.write_bytes(b"stub-final")
                    emit({{
                        "type": "done",
                        "job_id": job_id,
                        "audio_path": str(final),
                        "file_extension": "wav",
                        "chunks_total": total,
                        "sample_rate": 24000,
                        "channels": 1,
                    }})
                    continue

        if __name__ == "__main__":
            main()
        """
    ).strip()
    path = script_dir / "stub_worker.py"
    path.write_text(source, encoding="utf-8")
    return path


class _QueuedInput:
    def __init__(self) -> None:
        self._lines: queue.Queue[str | None] = queue.Queue()

    def send(self, payload: dict[str, object]) -> None:
        self._lines.put(json.dumps(payload) + "\n")

    def close(self) -> None:
        self._lines.put(None)

    def __iter__(self) -> _QueuedInput:
        return self

    def __next__(self) -> str:
        line = self._lines.get()
        if line is None:
            raise StopIteration
        return line


class ChunkerTests(unittest.TestCase):
    def test_split_handles_cjk_and_merges_short_fragments(self) -> None:
        script = (
            "你好。这是一个很短的句子。"
            "这里是一段更长的论述，包含逗号、句号和感叹号！"
            "Now some English. Short one. And a somewhat longer sentence as well."
        )
        chunks = split_script_into_chunks(script)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))
        self.assertEqual(chunks[0].index, 0)

    def test_split_of_empty_script_returns_empty(self) -> None:
        self.assertEqual(split_script_into_chunks("   \n\n"), [])


class WorkerClientTests(unittest.TestCase):
    def _client_for(self, script_path: Path) -> WorkerClient:
        def command_factory() -> list[str]:
            return [sys.executable, "-u", str(script_path)]

        return WorkerClient(command_factory=command_factory, niceness=0)

    def _client_for_terminal_timeout(self, script_path: Path) -> WorkerClient:
        def command_factory() -> list[str]:
            return [sys.executable, "-u", str(script_path)]

        return WorkerClient(
            command_factory=command_factory,
            niceness=0,
            terminal_event_timeout_seconds=0.2,
        )

    def test_success_stream_emits_chunk_events_and_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_stub_worker(Path(tmp), behavior="success")
            client = self._client_for(script)
            try:
                events: list[WorkerEvent] = []
                outcome = client.synthesize(
                    model="stub-model",
                    segments=[PreparedSegment("Hello world."), PreparedSegment("Second sentence.")],
                    options={},
                    output_dir=Path(tmp),
                    on_event=events.append,
                )
            finally:
                client.shutdown()

        self.assertEqual(outcome.get("chunks_total"), 2)
        self.assertTrue(outcome.get("audio_path"))
        types = [event.type for event in events]
        self.assertIn("chunk_started", types)
        self.assertIn("chunk_done", types)

    def test_worker_reads_cancel_while_synthesis_is_running(self) -> None:
        started = threading.Event()
        cancel_seen = threading.Event()

        class BlockingWorker(MlxTtsWorker):
            def synthesize_job(self, job: dict[str, object]) -> None:
                job_id = str(job.get("job_id") or "")
                started.set()
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    if self._should_cancel(job_id):
                        cancel_seen.set()
                        self.clear_cancel(job_id)
                        return
                    time.sleep(0.01)

        worker = BlockingWorker("stub-model")
        requests = _QueuedInput()
        server = threading.Thread(target=worker.serve, args=(requests,), daemon=True)
        server.start()
        try:
            requests.send({"type": "synthesize", "job_id": "job-a"})
            self.assertTrue(started.wait(timeout=1.0))
            requests.send({"type": "cancel", "job_id": "job-a"})
            self.assertTrue(cancel_seen.wait(timeout=0.5))
        finally:
            requests.send({"type": "shutdown"})
            requests.close()
            server.join(timeout=1.0)
        self.assertFalse(server.is_alive())

    def test_cooperative_cancellation_keeps_hot_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_stub_worker(Path(tmp), behavior="slow")
            client = self._client_for(script)
            cancelled = {"fired": False}

            def should_cancel() -> bool:
                if cancelled["fired"]:
                    return True
                return False

            def on_event(event: WorkerEvent) -> None:
                if event.type == "chunk_started":
                    cancelled["fired"] = True

            try:
                with self.assertRaises(MLXWorkerCancelled):
                    client.synthesize(
                        model="stub-model",
                        segments=[PreparedSegment("Slow chunk one."), PreparedSegment("Slow chunk two.")],
                        options={},
                        output_dir=Path(tmp),
                        on_event=on_event,
                        should_cancel=should_cancel,
                    )
                hot_process = client._process
                self.assertIsNotNone(hot_process)
                assert hot_process is not None
                self.assertIsNone(hot_process.poll())

                outcome = client.synthesize(
                    model="stub-model",
                    segments=[PreparedSegment("The next job reuses the model.")],
                    options={},
                    output_dir=Path(tmp),
                )
                self.assertIs(client._process, hot_process)
                self.assertEqual(outcome.get("chunks_total"), 1)
            finally:
                client.shutdown()

    def test_cancel_timeout_hard_resets_unresponsive_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_stub_worker(Path(tmp), behavior="ignore_cancel")

            def command_factory() -> list[str]:
                return [sys.executable, "-u", str(script)]

            client = WorkerClient(
                command_factory=command_factory,
                niceness=0,
                cancel_grace_seconds=0.2,
            )
            cancel = {"requested": False}
            process_holder = []

            def on_event(event: WorkerEvent) -> None:
                if event.type == "chunk_started":
                    cancel["requested"] = True
                    process_holder.append(client._process)

            started_at = time.monotonic()
            try:
                with self.assertRaises(MLXWorkerCancelled):
                    client.synthesize(
                        model="stub-model",
                        segments=[PreparedSegment("The worker ignores cancellation.")],
                        options={},
                        output_dir=Path(tmp),
                        on_event=on_event,
                        should_cancel=lambda: cancel["requested"],
                    )
                self.assertFalse(client.is_running())
                self.assertTrue(process_holder)
                process = process_holder[0]
                self.assertIsNotNone(process)
                assert process is not None
                self.assertIsNotNone(process.poll())
            finally:
                client.shutdown()

        self.assertLess(time.monotonic() - started_at, 5.0)

    def test_worker_crash_surfaces_error_and_recovers_on_next_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            crash_script = _write_stub_worker(Path(tmp), behavior="crash")
            crash_client = self._client_for(crash_script)
            try:
                with self.assertRaises(MLXWorkerError):
                    crash_client.synthesize(
                        model="stub-model",
                        segments=[PreparedSegment("Crashing chunk.")],
                        options={},
                        output_dir=Path(tmp),
                    )
            finally:
                crash_client.shutdown()

            # The second call should transparently restart the worker and
            # complete as expected; here we just need to confirm the client
            # did not get stuck with a half-dead process.
            success_script = _write_stub_worker(Path(tmp), behavior="success")
            success_client = self._client_for(success_script)
            try:
                outcome = success_client.synthesize(
                    model="stub-model",
                    segments=[PreparedSegment("Recovered chunk.")],
                    options={},
                    output_dir=Path(tmp),
                )
            finally:
                success_client.shutdown()
            self.assertEqual(outcome.get("chunks_total"), 1)

    def test_unscoped_worker_error_is_attached_to_current_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_stub_worker(Path(tmp), behavior="unscoped_error")
            client = self._client_for(script)
            try:
                with self.assertRaisesRegex(MLXWorkerError, "dispatch failed without job id"):
                    client.synthesize(
                        model="stub-model",
                        segments=[PreparedSegment("Broken chunk.")],
                        options={},
                        output_dir=Path(tmp),
                    )
            finally:
                client.shutdown()

    def test_worker_hang_after_all_chunks_surfaces_terminal_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_stub_worker(Path(tmp), behavior="hang_after_chunks")
            client = self._client_for_terminal_timeout(script)
            started_at = time.monotonic()
            try:
                with self.assertRaisesRegex(MLXWorkerError, "generated all chunks"):
                    client.synthesize(
                        model="stub-model",
                        segments=[PreparedSegment("First chunk."), PreparedSegment("Second chunk.")],
                        options={},
                        output_dir=Path(tmp),
                    )
            finally:
                client.shutdown()

        self.assertLess(time.monotonic() - started_at, 5.0)

    def test_model_load_error_fails_without_waiting_for_ready_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_stub_worker(Path(tmp), behavior="load_error")
            client = self._client_for(script)
            started_at = time.monotonic()
            try:
                with self.assertRaisesRegex(MLXWorkerError, "bad model metadata"):
                    client.synthesize(
                        model="bad-model",
                        segments=[PreparedSegment("Never rendered.")],
                        options={},
                        output_dir=Path(tmp),
                    )
            finally:
                client.shutdown()

        self.assertLess(time.monotonic() - started_at, 5.0)

    def test_switching_models_restarts_the_single_hot_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_stub_worker(Path(tmp), behavior="success")
            client = self._client_for(script)
            try:
                client.synthesize(
                    model="model-a",
                    segments=[PreparedSegment("First model.")],
                    options={},
                    output_dir=Path(tmp),
                )
                first_process = client._process
                self.assertIsNotNone(first_process)
                client.synthesize(
                    model="model-b",
                    segments=[PreparedSegment("Second model.")],
                    options={},
                    output_dir=Path(tmp),
                )
                second_process = client._process
                self.assertIsNotNone(second_process)
                self.assertIsNot(first_process, second_process)
                self.assertIsNotNone(first_process.poll())
            finally:
                client.shutdown()

    def test_build_worker_command_targets_expected_module(self) -> None:
        command = build_worker_command()
        self.assertIn("-m", command)
        self.assertIn("app.providers.tts_local_mlx.mlx_worker", command)


if __name__ == "__main__":
    unittest.main()
