"""Voice-generation and transcription model catalog (Voicebox-aligned ids) + status from TTS config."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability
from app.storage.config_store import ConfigStore


@dataclass(frozen=True)
class CatalogEntry:
    model_name: str
    display_name: str
    category: str  # "voice" | "transcription"
    size_mb: float
    hf_repo_id: str | None


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        "qwen-tts-1.7B",
        "Qwen TTS 1.7B",
        "voice",
        4.23 * 1024,
        "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
    ),
    CatalogEntry(
        "qwen-tts-0.6B",
        "Qwen TTS 0.6B",
        "voice",
        4.23 * 1024,
        "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
    ),
    CatalogEntry("whisper-base", "Whisper Base", "transcription", 140, None),
    CatalogEntry("whisper-small", "Whisper Small", "transcription", 460, None),
    CatalogEntry("whisper-medium", "Whisper Medium", "transcription", 1400, None),
    CatalogEntry("whisper-large", "Whisper Large", "transcription", 2900, None),
    CatalogEntry("whisper-turbo", "Whisper Large v3 Turbo", "transcription", 1600, None),
)

_BY_NAME: dict[str, CatalogEntry] = {e.model_name: e for e in CATALOG}


def _default_download_base(cwd: Path) -> Path:
    env = os.environ.get("AODCAST_HF_MODEL_BASE")
    if env:
        return Path(env)
    return cwd / "models"


def expected_voice_model_dir(cwd: Path, hf_repo_id: str) -> Path:
    tail = hf_repo_id.rstrip("/").split("/")[-1]
    return _default_download_base(cwd) / tail


def _path_matches_qwen_variant(model_name: str, path_str: str) -> bool:
    low = path_str.lower()
    if model_name == "qwen-tts-0.6B":
        return "0.6" in low or "0_6" in low
    if model_name == "qwen-tts-1.7B":
        return "1.7" in low or "1_7" in low
    return False


def _whisper_markers(name: str) -> tuple[str, ...]:
    if name == "whisper-turbo":
        return ("large-v3-turbo", "turbo", "large-v3")
    size = name.replace("whisper-", "")
    return (size,)


def _whisper_downloaded(model_name: str) -> bool:
    base = Path.home() / ".cache" / "whisper"
    if not base.is_dir():
        return False
    markers = _whisper_markers(model_name)
    for p in base.iterdir():
        if not p.is_file():
            continue
        name_low = p.name.lower()
        for m in markers:
            if m.lower() in name_low and name_low.endswith((".pt", ".bin", ".safetensors")):
                return True
    return False


def _voice_active(entry: CatalogEntry, cap_d: dict[str, object]) -> bool:
    if not entry.hf_repo_id:
        return False
    resolved = str(cap_d.get("resolved_model") or "").rstrip("/")
    repo = entry.hf_repo_id.rstrip("/")
    model_path = str(cap_d.get("model_path") or "")
    if cap_d.get("model_source") == "huggingface_repo" and resolved == repo:
        return True
    if cap_d.get("model_source") == "local_path" and model_path and bool(cap_d.get("model_path_exists")):
        return _path_matches_qwen_variant(entry.model_name, model_path) or (
            entry.hf_repo_id.split("/")[-1] in model_path.replace("\\", "/")
        )
    return False


def build_models_status(config_store: ConfigStore, cwd: Path) -> list[dict[str, object]]:
    tts_config = config_store.load_tts_config()
    cap = detect_local_mlx_capability(tts_config)
    cap_d = cap.to_dict()
    resolved = str(cap_d.get("resolved_model") or "").rstrip("/")
    model_path = str(cap_d.get("model_path") or "")
    path_exists = bool(cap_d.get("model_path_exists"))
    available = bool(cap_d.get("available"))

    out: list[dict[str, object]] = []
    for entry in CATALOG:
        downloaded = False
        loaded = False
        if entry.category == "voice" and entry.hf_repo_id:
            expected_dir = expected_voice_model_dir(cwd, entry.hf_repo_id)
            on_disk = expected_dir.is_dir() and any(expected_dir.glob("*.safetensors"))
            repo = entry.hf_repo_id.rstrip("/")
            hf_resolved = resolved == repo
            path_match = path_exists and model_path and (
                _path_matches_qwen_variant(entry.model_name, model_path)
                or (entry.hf_repo_id.split("/")[-1] in model_path.replace("\\", "/"))
            )
            downloaded = on_disk or hf_resolved or path_match
            active = _voice_active(entry, cap_d)
            loaded = bool(downloaded and available and active)
        elif entry.category == "transcription":
            downloaded = _whisper_downloaded(entry.model_name)

        out.append(
            {
                "model_name": entry.model_name,
                "display_name": entry.display_name,
                "category": entry.category,
                "hf_repo_id": entry.hf_repo_id,
                "downloaded": downloaded,
                "downloading": False,
                "size_mb": entry.size_mb,
                "loaded": loaded,
            }
        )
    return out


def download_voice_model(cwd: Path, model_name: str) -> dict[str, object]:
    entry = _BY_NAME.get(model_name)
    if entry is None or entry.category != "voice" or not entry.hf_repo_id:
        raise ValueError(f"Unknown or non-downloadable model: {model_name}")
    script = cwd / "scripts" / "model-download" / "download_qwen3_tts_mlx.py"
    if not script.is_file():
        raise FileNotFoundError(f"Download script not found: {script}")
    base = _default_download_base(cwd)
    base.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(script),
        "--repo-id",
        entry.hf_repo_id,
        "--base-dir",
        str(base),
    ]
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "download failed").strip()
        raise RuntimeError(msg)
    out_dir = expected_voice_model_dir(cwd, entry.hf_repo_id)
    return {"message": "ok", "path": str(out_dir.resolve())}


def delete_voice_model(cwd: Path, model_name: str) -> dict[str, object]:
    entry = _BY_NAME.get(model_name)
    if entry is None or entry.category != "voice" or not entry.hf_repo_id:
        raise ValueError(f"Unknown or non-removable model: {model_name}")
    target = expected_voice_model_dir(cwd, entry.hf_repo_id).resolve()
    base = _default_download_base(cwd).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Refusing to delete outside model base: {target}") from exc
    if not target.is_dir():
        raise FileNotFoundError(f"Model directory not found: {target}")
    shutil.rmtree(target)
    return {"message": "deleted", "path": str(target)}
