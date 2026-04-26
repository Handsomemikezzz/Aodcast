"""Voice-generation model catalog + status from TTS config."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import json
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
DOWNLOAD_STALL_TIMEOUT_SECONDS = 180.0


def _storage_config_file(config_store: ConfigStore) -> Path:
    return config_store.config_dir / "model-storage.json"


def _base_default_download_base(cwd: Path) -> Path:
    env = os.environ.get("AODCAST_HF_MODEL_BASE")
    if env:
        return Path(env)
    hf_env = os.environ.get("HF_HUB_CACHE")
    if hf_env:
        return Path(hf_env)
    try:
        from huggingface_hub import constants as hf_constants

        return Path(hf_constants.HF_HUB_CACHE)
    except Exception:
        return cwd / "models"


def _load_custom_model_storage_base(config_store: ConfigStore) -> Path | None:
    path = _storage_config_file(config_store)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    custom = str(payload.get("custom_base") or "").strip()
    if not custom:
        return None
    return Path(custom)


def save_custom_model_storage_base(config_store: ConfigStore, base: Path) -> Path:
    resolved = base.expanduser().resolve()
    path = _storage_config_file(config_store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"custom_base": str(resolved)}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return path


def _clear_custom_model_storage_base(config_store: ConfigStore) -> None:
    path = _storage_config_file(config_store)
    if path.exists():
        path.unlink()


def _default_download_base(cwd: Path, config_store: ConfigStore | None = None) -> Path:
    if config_store is not None:
        custom = _load_custom_model_storage_base(config_store)
        if custom is not None:
            return custom
    return _base_default_download_base(cwd)


def _download_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    # hf_xet can stall indefinitely behind local proxy/VPN setups after the UI
    # has already advanced to its heartbeat cap. The direct HTTP path is slower
    # but more predictable for first-run desktop model downloads.
    env["HF_HUB_DISABLE_XET"] = "1"
    return env


def _safe_tree_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def model_storage_status(config_store: ConfigStore, cwd: Path) -> dict[str, object]:
    default_base = _base_default_download_base(cwd).expanduser().resolve()
    custom_base = _load_custom_model_storage_base(config_store)
    current_base = (custom_base or default_base).expanduser().resolve()
    return {
        "current_base": str(current_base),
        "default_base": str(default_base),
        "custom_base": str(custom_base.expanduser().resolve()) if custom_base is not None else "",
        "is_custom": custom_base is not None,
        "exists": current_base.exists(),
    }


def expected_voice_model_dir(cwd: Path, hf_repo_id: str, config_store: ConfigStore | None = None) -> Path:
    tail = hf_repo_id.rstrip("/").split("/")[-1]
    return _default_download_base(cwd, config_store) / tail


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
            expected_dir = expected_voice_model_dir(cwd, entry.hf_repo_id, config_store)
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
    config_store: ConfigStore | None = None,
    on_output_line: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    entry = _BY_NAME.get(model_name)
    if entry is None or entry.category != "voice" or not entry.hf_repo_id:
        raise ValueError(f"Unknown or non-downloadable model: {model_name}")
    script = cwd / "scripts" / "model-download" / "download_qwen3_tts_mlx.py"
    if not script.is_file():
        raise FileNotFoundError(f"Download script not found: {script}")
    base = _default_download_base(cwd, config_store)
    out_dir = expected_voice_model_dir(cwd, entry.hf_repo_id, config_store)
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
        env=_download_subprocess_env(),
    )
    tail_lines: deque[str] = deque(maxlen=40)
    stream = proc.stdout
    reader_done = threading.Event()
    activity_lock = threading.Lock()
    last_activity_at = time.monotonic()
    last_observed_size = _safe_tree_size(out_dir)

    def read_output() -> None:
        nonlocal last_activity_at
        if stream is None:
            reader_done.set()
            return
        try:
            for raw_line in stream:
                line = raw_line.rstrip()
                if not line:
                    continue
                with activity_lock:
                    last_activity_at = time.monotonic()
                tail_lines.append(line)
                if on_output_line is not None:
                    on_output_line(line)
        finally:
            reader_done.set()

    reader_thread = threading.Thread(target=read_output, daemon=True)
    reader_thread.start()

    cancelled = False
    stalled = False
    last_size_check_at = 0.0
    while proc.poll() is None:
        if should_cancel is not None and should_cancel():
            cancelled = True
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            break
        now = time.monotonic()
        if now - last_size_check_at >= 2.0:
            current_size = _safe_tree_size(out_dir)
            if current_size != last_observed_size:
                last_observed_size = current_size
                with activity_lock:
                    last_activity_at = now
            last_size_check_at = now
        with activity_lock:
            idle_seconds = now - last_activity_at
        if DOWNLOAD_STALL_TIMEOUT_SECONDS > 0 and idle_seconds >= DOWNLOAD_STALL_TIMEOUT_SECONDS:
            stalled = True
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
    if stalled:
        raise RuntimeError(
            f"Download stalled for {model_name}: no output or file growth for "
            f"{int(DOWNLOAD_STALL_TIMEOUT_SECONDS)} seconds. Please retry the download."
        )
    if proc.returncode != 0:
        msg = "\n".join(tail_lines).strip() or "download failed"
        raise RuntimeError(msg)
    return {"message": "ok", "path": str(out_dir.resolve())}


def delete_voice_model(cwd: Path, model_name: str, config_store: ConfigStore | None = None) -> dict[str, object]:
    entry = _BY_NAME.get(model_name)
    if entry is None or entry.category != "voice" or not entry.hf_repo_id:
        raise ValueError(f"Unknown or non-removable model: {model_name}")
    target = expected_voice_model_dir(cwd, entry.hf_repo_id, config_store).resolve()
    base = _default_download_base(cwd, config_store).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Refusing to delete outside model base: {target}") from exc
    if not target.is_dir():
        raise FileNotFoundError(f"Model directory not found: {target}")
    shutil.rmtree(target)
    return {"message": "deleted", "path": str(target)}


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _copytree_with_progress(
    source: Path,
    destination: Path,
    *,
    total_bytes: int,
    copied_so_far: int,
    on_progress: Callable[[int, int, str], None] | None,
    should_cancel: Callable[[], bool] | None,
) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if should_cancel is not None and should_cancel():
            raise TaskCancellationRequested("Model storage migration cancelled.")
        target = destination / item.name
        if item.is_dir():
            copied_so_far = _copytree_with_progress(
                item,
                target,
                total_bytes=total_bytes,
                copied_so_far=copied_so_far,
                on_progress=on_progress,
                should_cancel=should_cancel,
            )
            continue
        size = item.stat().st_size
        shutil.copy2(item, target)
        copied_so_far += size
        if on_progress is not None:
            on_progress(copied_so_far, total_bytes, item.name)
    return copied_so_far


def migrate_model_storage(
    config_store: ConfigStore,
    cwd: Path,
    destination: Path,
    *,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    source_base = _default_download_base(cwd, config_store).expanduser().resolve()
    dest_base = destination.expanduser().resolve()
    if source_base == dest_base:
        raise ValueError("Destination is already the current model storage directory.")
    try:
        dest_base.relative_to(source_base)
    except ValueError:
        pass
    else:
        raise ValueError("Destination cannot be inside the current model storage directory.")

    dest_base.mkdir(parents=True, exist_ok=True)
    model_dirs: list[tuple[Path, Path]] = []
    for entry in CATALOG:
        if entry.category != "voice" or not entry.hf_repo_id:
            continue
        source = source_base / entry.hf_repo_id.rstrip("/").split("/")[-1]
        if source.is_dir():
            model_dirs.append((source, dest_base / source.name))

    total_bytes = sum(_directory_size(source) for source, _ in model_dirs)
    copied = 0
    moved = 0
    for source, target in model_dirs:
        if should_cancel is not None and should_cancel():
            raise TaskCancellationRequested("Model storage migration cancelled.")
        if target.exists():
            shutil.rmtree(target)
        copied = _copytree_with_progress(
            source,
            target,
            total_bytes=max(total_bytes, 1),
            copied_so_far=copied,
            on_progress=on_progress,
            should_cancel=should_cancel,
        )
        shutil.rmtree(source)
        moved += 1
        if on_progress is not None:
            on_progress(copied, max(total_bytes, 1), source.name)

    save_custom_model_storage_base(config_store, dest_base)
    return {
        "message": "migrated",
        "source": str(source_base),
        "destination": str(dest_base),
        "moved": moved,
        "total_bytes": total_bytes,
    }


def reset_model_storage(config_store: ConfigStore, cwd: Path) -> dict[str, object]:
    _clear_custom_model_storage_base(config_store)
    return model_storage_status(config_store, cwd)
