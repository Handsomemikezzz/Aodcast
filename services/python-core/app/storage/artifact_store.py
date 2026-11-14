from __future__ import annotations

from pathlib import Path
from uuid import uuid4


BUILTIN_REFERENCE_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "speaker-references"
_BUILTIN_PREFIX = "builtin:"


class ArtifactStore:
    """Owns file locations. Persisted paths are POSIX paths relative to the data dir
    (packaged reference assets are `builtin:<file>`); they are resolved only at the point of use."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.exports_dir = data_dir / "exports"

    def stored_path(self, path: str | Path) -> str:
        """Persistent form of a file inside the data dir or the packaged reference assets."""
        target = Path(path).resolve()
        try:
            return _BUILTIN_PREFIX + target.relative_to(BUILTIN_REFERENCE_ASSETS_DIR.resolve()).as_posix()
        except ValueError:
            pass
        try:
            return target.relative_to(self.data_dir.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError("Path must be inside the app data directory or packaged reference assets.") from exc

    def resolve_stored(self, stored: str | Path) -> Path:
        """Absolute path for a persisted path; refuses anything outside the data dir or packaged assets."""
        text = str(stored).strip()
        if not text:
            raise ValueError("Path is empty.")
        if text.startswith(_BUILTIN_PREFIX):
            base, relative = BUILTIN_REFERENCE_ASSETS_DIR.resolve(), text[len(_BUILTIN_PREFIX):]
        else:
            base, relative = self.data_dir.resolve(), text
        target = (base / relative).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise ValueError("Path must be inside the app data directory or packaged reference assets.") from exc
        return target

    def bootstrap(self) -> None:
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def session_export_dir(self, session_id: str) -> Path:
        return self.exports_dir / session_id

    def segment_assets_dir(self, session_id: str) -> Path:
        return self.session_export_dir(session_id) / "segment-assets"

    def render_export_dir(self, session_id: str, render_id: str) -> Path:
        return self.session_export_dir(session_id) / "renders" / render_id

    def write_preview_audio(self, audio_bytes: bytes, extension: str) -> Path:
        preview_dir = self.exports_dir / "_previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        suffix = extension.lstrip(".")
        path = preview_dir / f"preview-{uuid4().hex}.{suffix}"
        path.write_bytes(audio_bytes)
        return path

    def write_segment_audio(self, session_id: str, segment_artifact_id: str, audio_bytes: bytes) -> Path:
        target_dir = self.segment_assets_dir(session_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{segment_artifact_id}.wav"
        self._write_bytes_atomically(path, audio_bytes)
        return path

    def write_render_audio(self, session_id: str, render_id: str, audio_bytes: bytes) -> Path:
        target_dir = self.render_export_dir(session_id, render_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "podcast.wav"
        self._write_bytes_atomically(path, audio_bytes)
        return path

    def write_render_transcript(self, session_id: str, render_id: str, text: str) -> Path:
        target_dir = self.render_export_dir(session_id, render_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "transcript.txt"
        temporary = path.with_suffix(".txt.tmp")
        temporary.write_text(text.rstrip() + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    @staticmethod
    def _write_bytes_atomically(path: Path, value: bytes) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(value)
        temporary.replace(path)

    def delete_export_file(self, path: str | Path) -> bool:
        exports_dir = self.exports_dir.resolve()
        target = self.resolve_stored(path)
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
