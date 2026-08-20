from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path
from uuid import uuid4

from app.domain.common import sha256_bytes, utc_now_iso
from app.domain.speaker_reference import SpeakerReference
from app.storage.artifact_store import ArtifactStore


BUILTIN_REFERENCE_TEXT = "Hello, welcome to use Aodcast. What shall we talk about today?"
BUILTIN_REFERENCE_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "speaker-references"
MAX_REFERENCE_AUDIO_BYTES = 100 * 1024 * 1024
MAX_REFERENCE_AUDIO_SECONDS = 10 * 60.0

_BUILTIN_REFERENCES = (
    {
        "speaker_reference_id": "builtin_warm_knowledge",
        "name": "温和知识型",
        "description": "适合知识解释、通用播客和长时间收听。",
        "asset": "builtin_warm_knowledge.wav",
    },
    {
        "speaker_reference_id": "builtin_clear_broadcast",
        "name": "清晰播报型",
        "description": "适合资讯、分析和正式播报内容。",
        "asset": "builtin_clear_broadcast.wav",
    },
)


class SpeakerReferenceStore:
    def __init__(self, data_dir: Path, artifact_store: ArtifactStore) -> None:
        self.data_dir = data_dir
        self.artifact_store = artifact_store
        self.references_dir = data_dir / "speaker-references"
        self.audio_dir = artifact_store.exports_dir / "_speaker_references"

    def bootstrap(self) -> None:
        self.references_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        for spec in _BUILTIN_REFERENCES:
            path = self._builtin_audio_path(str(spec["asset"]))
            if not path.exists():
                raise FileNotFoundError(f"Missing built-in speaker reference asset: {path}")

    def list_references(self) -> list[SpeakerReference]:
        references = self._builtin_references()
        for path in sorted(self.references_dir.glob("*.json")):
            references.append(SpeakerReference.from_dict(self._read_json(path)))
        return references

    def get_reference(self, reference_id: str) -> SpeakerReference:
        cleaned = reference_id.strip()
        for reference in self.list_references():
            if reference.speaker_reference_id == cleaned:
                return reference
        raise ValueError(f"Unknown speaker_reference_id '{reference_id}'.")

    def create_user_reference(
        self,
        *,
        name: str,
        source_audio_path: Path,
        reference_text: str,
        language: str = "zh",
        audio_format: str = "",
    ) -> SpeakerReference:
        source_audio = self._validate_source_audio(source_audio_path)
        text = reference_text.strip()
        if not text:
            raise ValueError("Field 'reference_text' is required.")
        reference_id = f"speaker_{uuid4().hex}"
        suffix = (audio_format.strip().lstrip(".") or source_audio.suffix.lower().lstrip(".") or "wav").lower()
        target = self._copy_audio_blob(source_audio, reference_id=reference_id, suffix=suffix)
        now = utc_now_iso()
        reference = self._build_reference(
            reference_id=reference_id,
            name=name.strip() or "我的音色",
            source="user_saved",
            audio_path=target,
            reference_text=text,
            language=language.strip() or "zh",
            description="用户添加的参考音色",
            created_at=now,
            updated_at=now,
        )
        self._write_reference(reference)
        return reference

    def update_reference(
        self,
        reference_id: str,
        *,
        name: str | None = None,
        reference_text: str | None = None,
        source_audio_path: Path | None = None,
        language: str | None = None,
        audio_format: str = "",
    ) -> SpeakerReference:
        current = self.get_reference(reference_id)
        if current.source != "user_saved":
            raise ValueError("Only user-saved speaker references can be updated.")
        target = Path(current.audio_path)
        if source_audio_path is not None:
            source = self._validate_source_audio(source_audio_path)
            suffix = (audio_format.strip().lstrip(".") or source.suffix.lower().lstrip(".") or current.audio_format).lower()
            target = self._copy_audio_blob(
                source,
                reference_id=current.speaker_reference_id,
                suffix=suffix,
            )
        next_text = current.reference_text if reference_text is None else reference_text.strip()
        if not next_text:
            raise ValueError("Field 'reference_text' is required.")
        updated = self._build_reference(
            reference_id=current.speaker_reference_id,
            name=(name.strip() if name is not None else current.name) or current.name,
            source=current.source,
            audio_path=target,
            reference_text=next_text,
            language=(language.strip() if language is not None else current.language) or current.language,
            description=current.description,
            created_at=current.created_at,
            updated_at=utc_now_iso(),
            last_used_at=current.last_used_at,
        )
        self._write_reference(updated)
        return updated

    def mark_used(self, reference_id: str) -> SpeakerReference:
        current = self.get_reference(reference_id)
        if current.source != "user_saved":
            return current
        updated = self._build_reference(
            reference_id=current.speaker_reference_id,
            name=current.name,
            source=current.source,
            audio_path=Path(current.audio_path),
            reference_text=current.reference_text,
            language=current.language,
            description=current.description,
            created_at=current.created_at,
            updated_at=utc_now_iso(),
            last_used_at=utc_now_iso(),
        )
        self._write_reference(updated)
        return updated

    def delete_reference(self, reference_id: str) -> bool:
        current = self.get_reference(reference_id)
        if current.source == "built_in":
            raise ValueError("Built-in speaker references cannot be deleted.")
        metadata_path = self._reference_file(current.speaker_reference_id)
        if not metadata_path.exists():
            return False
        metadata_path.unlink()
        for audio_path in self.audio_dir.glob(f"{current.speaker_reference_id}-*"):
            if audio_path.is_file():
                audio_path.unlink(missing_ok=True)
        return True

    def _builtin_references(self) -> list[SpeakerReference]:
        now = utc_now_iso()
        return [
            self._build_reference(
                reference_id=str(spec["speaker_reference_id"]),
                name=str(spec["name"]),
                source="built_in",
                audio_path=self._builtin_audio_path(str(spec["asset"])),
                reference_text=BUILTIN_REFERENCE_TEXT,
                language="en",
                description=str(spec["description"]),
                created_at=now,
                updated_at=now,
            )
            for spec in _BUILTIN_REFERENCES
        ]

    def _build_reference(
        self,
        *,
        reference_id: str,
        name: str,
        source: str,
        audio_path: Path,
        reference_text: str,
        language: str,
        description: str,
        created_at: str,
        updated_at: str,
        last_used_at: str | None = None,
    ) -> SpeakerReference:
        audio_bytes = audio_path.read_bytes()
        reference = SpeakerReference(
            speaker_reference_id=reference_id,
            name=name,
            source=source,
            audio_path=str(audio_path.resolve()),
            audio_hash=sha256_bytes(audio_bytes),
            audio_format=audio_path.suffix.lower().lstrip(".") or "wav",
            duration_ms=self._probe_duration_ms(audio_path),
            reference_text=reference_text,
            language=language,
            description=description,
            created_at=created_at,
            updated_at=updated_at,
            last_used_at=last_used_at,
        )
        reference.validate()
        return reference

    def _reference_file(self, reference_id: str) -> Path:
        return self.references_dir / f"{reference_id}.json"

    def _write_reference(self, reference: SpeakerReference) -> None:
        path = self._reference_file(reference.speaker_reference_id)
        path.write_text(json.dumps(reference.to_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, object]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid speaker reference metadata: {path}")
        return payload

    def _builtin_audio_path(self, asset: str) -> Path:
        return BUILTIN_REFERENCE_ASSETS_DIR / asset

    def _copy_audio_blob(self, source: Path, *, reference_id: str, suffix: str) -> Path:
        audio_bytes = source.read_bytes()
        audio_hash = sha256_bytes(audio_bytes)
        target = self.audio_dir / f"{reference_id}-{audio_hash}.{suffix}"
        if target.exists():
            return target
        temporary = self.audio_dir / f".{reference_id}-{uuid4().hex}.tmp"
        try:
            temporary.write_bytes(audio_bytes)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def _validate_source_audio(self, path: Path) -> Path:
        target = path.expanduser().resolve()
        if not target.exists() or not target.is_file():
            raise ValueError("Speaker reference audio is missing or not a file.")
        if target.stat().st_size > MAX_REFERENCE_AUDIO_BYTES:
            raise ValueError("Speaker reference audio is too large.")
        if target.suffix.lower() not in {".wav", ".mp3", ".m4a", ".mp4", ".aac", ".flac", ".webm", ".ogg"}:
            raise ValueError("Speaker reference audio must be a supported audio file.")
        if self._probe_duration_ms(target) > int(MAX_REFERENCE_AUDIO_SECONDS * 1000):
            raise ValueError("Speaker reference audio must be 10 minutes or shorter.")
        return target

    def _probe_duration_ms(self, path: Path) -> int:
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as wav_file:
                    rate = wav_file.getframerate()
                    frames = wav_file.getnframes()
                if rate > 0 and frames > 0:
                    return max(1, round(frames * 1000 / rate))
            except (wave.Error, EOFError):
                pass
        decode_error: Exception | None = None
        try:
            import miniaudio  # type: ignore

            info = miniaudio.get_file_info(str(path))
            duration = float(getattr(info, "duration", 0.0) or 0.0)
            if duration > 0:
                return max(1, round(duration * 1000))
        except Exception as exc:
            decode_error = exc
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            try:
                duration = float(result.stdout.strip())
            except ValueError:
                duration = 0.0
            if result.returncode == 0 and duration > 0:
                return max(1, round(duration * 1000))
        raise ValueError("Unable to read speaker reference audio duration.") from decode_error
