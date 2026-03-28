from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_local_mlx.runtime import resolve_local_model_target


@dataclass(frozen=True, slots=True)
class LocalMLXRunResult:
    audio_bytes: bytes
    file_extension: str
    model_name: str
    output_path: str


class MLXAudioQwenRunner:
    def __init__(self, config: TTSProviderConfig) -> None:
        self.config = config

    def synthesize(self, text: str, *, audio_format: str) -> LocalMLXRunResult:
        model_target, _ = resolve_local_model_target(self.config)
        file_extension = (self.config.audio_format or audio_format).lstrip(".")

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
            ]
            if self.config.local_ref_audio_path:
                command.extend(["--ref_audio", self.config.local_ref_audio_path])

            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip() or result.stdout.strip() or "Unknown mlx-audio failure."
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
