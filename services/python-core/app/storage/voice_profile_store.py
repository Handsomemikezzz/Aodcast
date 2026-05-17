from __future__ import annotations

import json
import shutil
import wave
from pathlib import Path
from uuid import uuid4

from app.domain.common import utc_now_iso
from app.domain.voice_profile import VoiceProfileRecord
from app.domain.voice_studio import resolve_style_preset, resolve_voice_preset
from app.orchestration.audio_rendering import VoiceRenderSettings
from app.storage.artifact_store import ArtifactStore


BUILTIN_PROFILE_TEXT = "Hello, welcome to use Aodcast. What shall we talk about today?"
BUILTIN_PROFILE_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "voice-profiles"
MAX_REFERENCE_AUDIO_BYTES = 50 * 1024 * 1024
MAX_REFERENCE_AUDIO_SECONDS = 30.0

_BUILTIN_PROFILE_SPECS = (
    {
        "voice_profile_id": "builtin_warm_knowledge",
        "name": "温和知识型",
        "description": "适合知识解释、通用播客和长时间收听。",
        "voice_id": "warm_narrator",
        "style_id": "natural",
        "speed": 1.0,
        "asset": "builtin_warm_knowledge.wav",
    },
    {
        "voice_profile_id": "builtin_clear_broadcast",
        "name": "清晰播报型",
        "description": "适合资讯、分析和正式播报内容。",
        "voice_id": "news_anchor",
        "style_id": "news",
        "speed": 0.95,
        "asset": "builtin_clear_broadcast.wav",
    },
)


class VoiceProfileStore:
    def __init__(self, data_dir: Path, artifact_store: ArtifactStore) -> None:
        self.data_dir = data_dir
        self.artifact_store = artifact_store
        self.profiles_dir = data_dir / "voice-profiles"
        self.audio_dir = artifact_store.exports_dir / "_voice_profiles"
        self.user_profiles_file = self.profiles_dir / "user-profiles.json"

    def bootstrap(self) -> None:
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        if not self.user_profiles_file.exists():
            self._write_user_profiles([])
        for spec in _BUILTIN_PROFILE_SPECS:
            path = self._builtin_audio_path(str(spec["asset"]))
            if not path.exists():
                raise FileNotFoundError(f"Missing built-in voice profile asset: {path}")

    def list_profiles(self) -> list[VoiceProfileRecord]:
        profiles = self._builtin_profiles()
        profiles.extend(self._read_user_profiles())
        return profiles

    def get_profile(self, profile_id: str) -> VoiceProfileRecord:
        cleaned = profile_id.strip()
        for profile in self.list_profiles():
            if profile.voice_profile_id == cleaned:
                return profile
        raise ValueError(f"Unknown voice_profile_id '{profile_id}'.")

    def create_user_profile(
        self,
        *,
        name: str,
        preview_audio_path: str = "",
        reference_audio_path: str = "",
        reference_text: str = "",
        settings: VoiceRenderSettings | None = None,
        provider: str = "",
        model: str = "",
        language: str = "zh",
        audio_format: str = "wav",
    ) -> VoiceProfileRecord:
        raw_audio_path = reference_audio_path.strip() or preview_audio_path.strip()
        source_audio = self._validate_reference_audio_path(raw_audio_path)
        text = reference_text.strip()
        if not text and settings is not None:
            text = settings.preview_text.strip()
        if not text:
            raise ValueError("Field 'reference_text' is required.")
        normalized = self._normalize_settings(settings or VoiceRenderSettings(language=language, audio_format=audio_format, preview_text=text))
        profile_id = f"user_{uuid4().hex}"
        suffix = source_audio.suffix.lower().lstrip(".") or normalized.audio_format or "wav"
        target = self.audio_dir / f"{profile_id}.{suffix}"
        shutil.copyfile(source_audio, target)
        now = utc_now_iso()
        profile = VoiceProfileRecord(
            voice_profile_id=profile_id,
            name=name.strip() or "我的音色",
            source="user_saved",
            audio_path=str(target),
            preview_text=text,
            provider=provider.strip() or "local_mlx",
            model=model.strip(),
            voice_id=normalized.voice_id,
            voice_name=normalized.voice_name,
            style_id=normalized.style_id,
            style_name=normalized.style_name,
            speed=normalized.speed,
            language=normalized.language,
            audio_format=suffix,
            description="用户添加的参考音色",
            created_at=now,
            updated_at=now,
        )
        profiles = self._read_user_profiles()
        profiles.append(profile)
        self._write_user_profiles(profiles)
        return profile

    def create_user_profile_metadata(
        self,
        *,
        name: str,
        settings: VoiceRenderSettings | None = None,
        provider: str = "",
        model: str = "",
        language: str = "zh",
        audio_format: str = "wav",
    ) -> VoiceProfileRecord:
        normalized = self._normalize_settings(
            settings or VoiceRenderSettings(language=language, audio_format=audio_format)
        )
        profile_id = f"user_{uuid4().hex}"
        now = utc_now_iso()
        profile = VoiceProfileRecord(
            voice_profile_id=profile_id,
            name=name.strip() or "我的音色",
            source="user_saved",
            audio_path="",
            preview_text="",
            provider=provider.strip() or "local_mlx",
            model=model.strip(),
            voice_id=normalized.voice_id,
            voice_name=normalized.voice_name,
            style_id=normalized.style_id,
            style_name=normalized.style_name,
            speed=normalized.speed,
            language=normalized.language,
            audio_format=(normalized.audio_format or audio_format or "wav").lstrip("."),
            description="用户添加的参考音色",
            created_at=now,
            updated_at=now,
        )
        profiles = self._read_user_profiles()
        profiles.append(profile)
        self._write_user_profiles(profiles)
        return profile

    def attach_user_profile_sample(
        self,
        profile_id: str,
        *,
        source_audio_path: Path,
        reference_text: str,
        audio_format: str = "",
    ) -> VoiceProfileRecord:
        text = reference_text.strip()
        if not text:
            raise ValueError("Field 'reference_text' is required.")
        source_audio = self._validate_reference_audio_path(str(source_audio_path))
        profile = self.get_profile(profile_id)
        if profile.source != "user_saved":
            raise ValueError("Only user-saved voice profiles can receive uploaded samples.")
        previous_audio_path = Path(profile.audio_path).expanduser().resolve() if profile.audio_path else None
        suffix = (audio_format.strip().lstrip(".") or source_audio.suffix.lower().lstrip(".") or profile.audio_format or "wav")
        target = self.audio_dir / f"{profile.voice_profile_id}.{suffix}"
        shutil.copyfile(source_audio, target)
        if previous_audio_path and previous_audio_path != target.resolve():
            try:
                previous_audio_path.relative_to(self.audio_dir.resolve())
            except ValueError:
                pass
            else:
                if previous_audio_path.exists() and previous_audio_path.is_file():
                    previous_audio_path.unlink()
        updated = VoiceProfileRecord.from_dict(
            {
                **profile.to_dict(),
                "audio_path": str(target),
                "preview_text": text,
                "reference_text": text,
                "audio_format": suffix,
                "updated_at": utc_now_iso(),
            }
        )
        return self._replace_user_profile(updated)

    def update_profile(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        reference_text: str | None = None,
    ) -> VoiceProfileRecord:
        cleaned = profile_id.strip()
        if name is None and reference_text is None:
            raise ValueError("At least one of 'name' or 'reference_text' is required.")
        profiles = self._read_user_profiles()
        updated: VoiceProfileRecord | None = None
        next_profiles: list[VoiceProfileRecord] = []
        for profile in profiles:
            if profile.voice_profile_id != cleaned:
                next_profiles.append(profile)
                continue
            next_name = profile.name if name is None else (name.strip() or profile.name)
            next_text = profile.preview_text if reference_text is None else reference_text.strip()
            if not next_text:
                raise ValueError("Field 'reference_text' is required.")
            updated = VoiceProfileRecord.from_dict(
                {
                    **profile.to_dict(),
                    "name": next_name,
                    "preview_text": next_text,
                    "reference_text": next_text,
                    "updated_at": utc_now_iso(),
                }
            )
            next_profiles.append(updated)
        if updated is None:
            raise ValueError("Only user-saved voice profiles can be updated.")
        self._write_user_profiles(next_profiles)
        return updated

    def mark_used(self, profile_id: str) -> VoiceProfileRecord:
        profile = self.get_profile(profile_id)
        if profile.source != "user_saved":
            return profile
        return self._replace_user_profile(
            VoiceProfileRecord.from_dict(
                {
                    **profile.to_dict(),
                    "last_used_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                }
            )
        )

    def delete_profile(self, profile_id: str) -> bool:
        cleaned = profile_id.strip()
        if any(profile.voice_profile_id == cleaned for profile in self._builtin_profiles()):
            raise ValueError("Built-in voice profiles cannot be deleted.")
        profiles = self._read_user_profiles()
        next_profiles = [profile for profile in profiles if profile.voice_profile_id != cleaned]
        if len(next_profiles) == len(profiles):
            return False
        removed = next(profile for profile in profiles if profile.voice_profile_id == cleaned)
        audio_path = Path(removed.audio_path).expanduser().resolve()
        try:
            audio_path.relative_to(self.audio_dir.resolve())
        except ValueError:
            pass
        else:
            if audio_path.exists() and audio_path.is_file():
                audio_path.unlink()
        self._write_user_profiles(next_profiles)
        return True

    def _replace_user_profile(self, updated: VoiceProfileRecord) -> VoiceProfileRecord:
        profiles = self._read_user_profiles()
        replaced = False
        next_profiles: list[VoiceProfileRecord] = []
        for profile in profiles:
            if profile.voice_profile_id == updated.voice_profile_id:
                next_profiles.append(updated)
                replaced = True
            else:
                next_profiles.append(profile)
        if not replaced:
            raise ValueError(f"Unknown voice_profile_id '{updated.voice_profile_id}'.")
        self._write_user_profiles(next_profiles)
        return updated

    def _builtin_profiles(self) -> list[VoiceProfileRecord]:
        now = utc_now_iso()
        profiles: list[VoiceProfileRecord] = []
        for spec in _BUILTIN_PROFILE_SPECS:
            voice = resolve_voice_preset(str(spec["voice_id"]))
            style = resolve_style_preset(str(spec["style_id"]))
            profiles.append(
                VoiceProfileRecord(
                    voice_profile_id=str(spec["voice_profile_id"]),
                    name=str(spec["name"]),
                    source="built_in",
                    audio_path=str(self._builtin_audio_path(str(spec["asset"]))),
                    preview_text=BUILTIN_PROFILE_TEXT,
                    provider="local_mlx",
                    model="built-in-reference",
                    voice_id=voice.voice_id,
                    voice_name=voice.name,
                    style_id=style.style_id,
                    style_name=style.name,
                    speed=float(spec["speed"]),
                    language="zh",
                    audio_format="wav",
                    description=str(spec["description"]),
                    created_at=now,
                    updated_at=now,
                )
            )
        return profiles

    def _normalize_settings(self, settings: VoiceRenderSettings) -> VoiceRenderSettings:
        voice = resolve_voice_preset(settings.voice_id)
        style = resolve_style_preset(settings.style_id)
        return VoiceRenderSettings(
            voice_id=voice.voice_id,
            voice_name=settings.voice_name.strip() or voice.name,
            style_id=style.style_id,
            style_name=settings.style_name.strip() or style.name,
            speed=min(1.2, max(0.8, float(settings.speed or 1.0))),
            language=settings.language.strip() or "zh",
            audio_format=(settings.audio_format.strip() or "wav").lstrip("."),
            preview_text=settings.preview_text.strip(),
        )

    def _builtin_audio_path(self, profile_id: str) -> Path:
        return BUILTIN_PROFILE_ASSETS_DIR / profile_id

    def _validate_reference_audio_path(self, path: str) -> Path:
        if not path.strip():
            raise ValueError("Voice profile reference audio path is required.")
        target = Path(path).expanduser().resolve()
        if not target.exists():
            raise ValueError("Voice profile reference audio is missing.")
        if not target.is_file():
            raise ValueError("Voice profile reference audio must point to a file.")
        if target.stat().st_size > MAX_REFERENCE_AUDIO_BYTES:
            raise ValueError("Voice profile reference audio is too large.")
        if target.suffix.lower() not in {".wav", ".mp3", ".m4a", ".mp4", ".aac", ".flac", ".webm", ".ogg"}:
            raise ValueError("Voice profile reference audio must be a supported audio file.")
        self._validate_reference_audio_duration(target)
        return target

    def _validate_reference_audio_duration(self, path: Path) -> None:
        if path.suffix.lower() != ".wav":
            return
        try:
            with wave.open(str(path), "rb") as wav_file:
                frame_rate = wav_file.getframerate()
                frame_count = wav_file.getnframes()
        except (wave.Error, EOFError):
            return
        if frame_rate <= 0:
            return
        duration = frame_count / float(frame_rate)
        if duration > MAX_REFERENCE_AUDIO_SECONDS:
            raise ValueError("Voice profile reference audio must be 30 seconds or shorter.")

    def _read_user_profiles(self) -> list[VoiceProfileRecord]:
        if not self.user_profiles_file.exists():
            return []
        payload = json.loads(self.user_profiles_file.read_text(encoding="utf-8"))
        raw_profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
        return [
            VoiceProfileRecord.from_dict(item)
            for item in raw_profiles
            if isinstance(item, dict)
        ]

    def _write_user_profiles(self, profiles: list[VoiceProfileRecord]) -> None:
        self.user_profiles_file.parent.mkdir(parents=True, exist_ok=True)
        self.user_profiles_file.write_text(
            json.dumps(
                {"profiles": [profile.to_dict() for profile in profiles]},
                indent=2,
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )
