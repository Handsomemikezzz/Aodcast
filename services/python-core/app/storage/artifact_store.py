from __future__ import annotations

from pathlib import Path
from uuid import uuid4


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

    def write_named_transcript(self, session_id: str, text: str, stem: str) -> Path:
        export_dir = self.session_export_dir(session_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"{stem}.txt"
        path.write_text(text + "\n", encoding="utf-8")
        return path

    def write_audio(self, session_id: str, audio_bytes: bytes, extension: str) -> Path:
        export_dir = self.session_export_dir(session_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        suffix = extension.lstrip(".")
        path = export_dir / f"audio.{suffix}"
        path.write_bytes(audio_bytes)
        return path

    def write_named_audio(self, session_id: str, audio_bytes: bytes, extension: str, stem: str) -> Path:
        export_dir = self.session_export_dir(session_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        suffix = extension.lstrip(".")
        path = export_dir / f"{stem}.{suffix}"
        path.write_bytes(audio_bytes)
        return path

    def write_preview_audio(self, audio_bytes: bytes, extension: str) -> Path:
        preview_dir = self.exports_dir / "_previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        suffix = extension.lstrip(".")
        path = preview_dir / f"preview-{uuid4().hex}.{suffix}"
        path.write_bytes(audio_bytes)
        return path

    def delete_export_file(self, path: str | Path) -> bool:
        exports_dir = self.exports_dir.resolve()
        target = Path(path).expanduser().resolve()
        try:
            target.relative_to(exports_dir)
        except ValueError as exc:
            raise ValueError("Artifact path must be inside the exports directory.") from exc
        if not target.exists():
            return False
        if not target.is_file():
            raise ValueError("Artifact path does not point to a file.")
        target.unlink()
        return True
