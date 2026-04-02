from __future__ import annotations

import time
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_local_mlx.runtime import resolve_local_model_target
from app.runtime.task_cancellation import TaskCancellationRequested


@dataclass(frozen=True, slots=True)
class LocalMLXRunResult:
    audio_bytes: bytes
    file_extension: str
    model_name: str
    output_path: str


class MLXAudioQwenRunner:
    _CANCEL_POLL_INTERVAL_SECONDS = 0.25
    _MIN_MAX_TOKENS = 4096
    _MAX_MAX_TOKENS = 16384

    def __init__(self, config: TTSProviderConfig) -> None:
        self.config = config

    def synthesize(
        self,
        text: str,
        *,
        audio_format: str,
        should_cancel: Callable[[], bool] | None = None,
    ) -> LocalMLXRunResult:
        model_target, _ = resolve_local_model_target(self.config)
        file_extension = (self.config.audio_format or audio_format).lstrip(".")
        max_tokens = self._recommended_max_tokens(text)

        with tempfile.TemporaryDirectory(prefix="aodcast-mlx-tts-") as temp_dir:
            output_dir = Path(temp_dir)
            prefix = output_dir / "render"
            command = [
                sys.executable,
                "-m",
                "mlx_audio.tts.generate",
                "--model",
                model_target,
                "--text",
                text,
                "--file_prefix",
                str(prefix),
                "--audio_format",
                file_extension,
                "--join_audio",
                "--max_tokens",
                str(max_tokens),
            ]
            if self.config.local_ref_audio_path:
                command.extend(["--ref_audio", self.config.local_ref_audio_path])

            if should_cancel is not None and should_cancel():
                raise TaskCancellationRequested("Local MLX synthesis cancelled before start.")

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            while process.poll() is None:
                if should_cancel is not None and should_cancel():
                    self._terminate_process(process)
                    raise TaskCancellationRequested("Local MLX synthesis cancelled.")
                time.sleep(self._CANCEL_POLL_INTERVAL_SECONDS)

            stdout, stderr = process.communicate()
            if process.returncode != 0:
                stderr = stderr.strip() or stdout.strip() or "Unknown mlx-audio failure."
                raise RuntimeError(f"mlx-audio generation failed. {stderr}")

            output_path = self._resolve_output_file(prefix, output_dir, file_extension)
            return LocalMLXRunResult(
                audio_bytes=output_path.read_bytes(),
                file_extension=file_extension,
                model_name=self.config.model,
                output_path=str(output_path),
            )

    def _resolve_output_file(self, prefix: Path, output_dir: Path, extension: str) -> Path:
        direct_path = prefix.with_suffix(f".{extension}")
        if direct_path.exists():
            return direct_path

        candidates = sorted(output_dir.glob(f"{prefix.name}*.{extension}"))
        if candidates:
            return candidates[0]

        raise RuntimeError(
            f"mlx-audio did not produce an output .{extension} file in {output_dir}."
        )

    def _recommended_max_tokens(self, text: str) -> int:
        estimated = len(text.strip()) * 4
        return min(self._MAX_MAX_TOKENS, max(self._MIN_MAX_TOKENS, estimated))

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            process.communicate()
            return
        process.terminate()
        try:
            process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=2.0)
