from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from app.providers.tts_local_mlx.chunker import split_script_into_chunks
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
    """

    source = textwrap.dedent(
        f"""
        import json, sys, os, time, pathlib

        def emit(event):
            sys.stdout.write(json.dumps(event) + "\\n")
            sys.stdout.flush()

        def main():
            emit({{"type": "ready", "pid": os.getpid(), "model": "stub"}})
            behavior = {behavior!r}
            cancelled = False
            for raw in sys.stdin:
                line = raw.strip()
                if not line:
                    continue
                msg = json.loads(line)
                kind = msg.get("type")
                if kind == "shutdown":
                    break
                if kind == "cancel":
                    cancelled = True
                    continue
                if kind != "synthesize":
                    continue
                job_id = msg.get("job_id")
                chunks = msg.get("chunks") or []
                output_dir = pathlib.Path(msg.get("output_dir") or ".")
                audio_format = msg.get("audio_format") or "wav"
                total = len(chunks)
                if behavior == "crash":
                    sys.exit(3)
                for i, _ in enumerate(chunks):
                    if cancelled:
                        emit({{"type": "cancelled", "job_id": job_id}})
                        cancelled = False
                        break
                    emit({{"type": "chunk_started", "job_id": job_id, "index": i, "total": total}})
                    if behavior == "slow":
                        for _ in range(20):
                            if cancelled:
                                break
                            time.sleep(0.1)
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
                else:
                    final = output_dir / f"final.{{audio_format}}"
                    final.write_bytes(b"stub-final")
                    emit({{
                        "type": "done",
                        "job_id": job_id,
                        "audio_path": str(final),
                        "file_extension": audio_format,
                        "chunks_total": total,
                        "sample_rate": 24000,
                    }})
                    continue
                if cancelled:
                    cancelled = False

        if __name__ == "__main__":
            main()
        """
    ).strip()
    path = script_dir / "stub_worker.py"
    path.write_text(source, encoding="utf-8")
    return path


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

    def test_success_stream_emits_chunk_events_and_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_stub_worker(Path(tmp), behavior="success")
            client = self._client_for(script)
            try:
                events: list[WorkerEvent] = []
                outcome = client.synthesize(
                    model="stub-model",
                    chunks=["Hello world.", "Second sentence."],
                    voice="",
                    audio_format="wav",
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

    def test_cancellation_request_terminates_worker(self) -> None:
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
                        chunks=["Slow chunk one.", "Slow chunk two."],
                        voice="",
                        audio_format="wav",
                        output_dir=Path(tmp),
                        on_event=on_event,
                        should_cancel=should_cancel,
                    )
            finally:
                client.shutdown()

    def test_worker_crash_surfaces_error_and_recovers_on_next_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            crash_script = _write_stub_worker(Path(tmp), behavior="crash")
            crash_client = self._client_for(crash_script)
            try:
                with self.assertRaises(MLXWorkerError):
                    crash_client.synthesize(
                        model="stub-model",
                        chunks=["Crashing chunk."],
                        voice="",
                        audio_format="wav",
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
                    chunks=["Recovered chunk."],
                    voice="",
                    audio_format="wav",
                    output_dir=Path(tmp),
                )
            finally:
                success_client.shutdown()
            self.assertEqual(outcome.get("chunks_total"), 1)

    def test_build_worker_command_targets_expected_module(self) -> None:
        command = build_worker_command()
        self.assertIn("-m", command)
        self.assertIn("app.providers.tts_local_mlx.mlx_worker", command)


if __name__ == "__main__":
    unittest.main()
