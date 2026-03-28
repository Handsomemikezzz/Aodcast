from __future__ import annotations

from pathlib import Path


class ArtifactStore:
    def __init__(self, data_dir: Path) -> None:
        self.exports_dir = data_dir / "exports"

    def bootstrap(self) -> None:
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def session_export_dir(self, session_id: str) -> Path:
        return self.exports_dir / session_id

    def write_transcript(self, session_id: str, text: str) -> Path:
        export_dir = self.session_export_dir(session_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / "transcript.txt"
        path.write_text(text + "\n", encoding="utf-8")
        return path

    def write_audio(self, session_id: str, audio_bytes: bytes, extension: str) -> Path:
        export_dir = self.session_export_dir(session_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        suffix = extension.lstrip(".")
        path = export_dir / f"audio.{suffix}"
        path.write_bytes(audio_bytes)
        return path
