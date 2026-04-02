"""Voice-generation model catalog + status from TTS config."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability
from app.runtime.task_cancellation import TaskCancellationRequested
from app.storage.config_store import ConfigStore


@dataclass(frozen=True)
class CatalogEntry:
    model_name: str
    display_name: str
    category: str  # "voice"
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


def download_voice_model(
    cwd: Path,
    model_name: str,
    *,
    on_output_line: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
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
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    tail_lines: deque[str] = deque(maxlen=40)
    stream = proc.stdout
    reader_done = threading.Event()

    def read_output() -> None:
        if stream is None:
            reader_done.set()
            return
        try:
            for raw_line in stream:
                line = raw_line.rstrip()
                if not line:
                    continue
                tail_lines.append(line)
                if on_output_line is not None:
                    on_output_line(line)
        finally:
            reader_done.set()

    reader_thread = threading.Thread(target=read_output, daemon=True)
    reader_thread.start()

    cancelled = False
    while proc.poll() is None:
        if should_cancel is not None and should_cancel():
            cancelled = True
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            break
        time.sleep(0.2)

    if proc.poll() is None:
        proc.wait()
    reader_done.wait(timeout=2.0)
    reader_thread.join(timeout=2.0)
    if cancelled:
        raise TaskCancellationRequested(f"Download cancelled for {model_name}.")
    if proc.returncode != 0:
        msg = "\n".join(tail_lines).strip() or "download failed"
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
