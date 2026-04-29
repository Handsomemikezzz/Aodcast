from __future__ import annotations

import hashlib
import json
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_task_file_name(task_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]", "_", task_id).strip("._")
    if not normalized:
        normalized = "task"
    digest = hashlib.sha1(task_id.encode("utf-8")).hexdigest()[:10]
    max_prefix = max(1, 180 - len(digest) - 1)
    prefix = normalized[:max_prefix].rstrip("._-") or "task"
    return f"{prefix}-{digest}"


class RequestStateStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "runtime" / "request-state"
        self._cancel_dir = data_dir / "runtime" / "cancel-request"
        self._lock_dir = data_dir / "runtime" / "locks"
        self._locks_guard = threading.Lock()
        self._task_locks: dict[str, threading.Lock] = {}

    def bootstrap(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cancel_dir.mkdir(parents=True, exist_ok=True)
        self._lock_dir.mkdir(parents=True, exist_ok=True)

    def save(self, task_id: str, request_state: dict[str, object]) -> Path:
        with self._task_guard(task_id):
            payload = {
                "task_id": task_id,
                "request_state": request_state,
                "updated_at": _now_iso(),
            }
            path = self._path(task_id)
            self._atomic_write_json(path, payload)
            return path

    def save_if_current_phase(
        self,
        task_id: str,
        request_state: dict[str, object],
        *,
        allowed_phases: set[str],
    ) -> bool:
        normalized_allowed = {phase.strip().lower() for phase in allowed_phases}
        with self._task_guard(task_id):
            current = self._load_request_state(self._path(task_id))
            current_phase = ""
            if isinstance(current, dict):
                value = current.get("phase")
                if isinstance(value, str):
                    current_phase = value.strip().lower()
            if current_phase not in normalized_allowed:
                return False
            payload = {
                "task_id": task_id,
                "request_state": request_state,
                "updated_at": _now_iso(),
            }
            self._atomic_write_json(self._path(task_id), payload)
            return True

    def load(self, task_id: str) -> dict[str, object] | None:
        with self._task_guard(task_id, mode="read"):
            return self._load_request_state(self._path(task_id))

    def cleanup_terminal_states(self, *, prefix: str, max_age_seconds: float) -> int:
        """Remove old completed task state files for a task-id namespace.

        Voice preview tasks intentionally use unique task ids so stale polling
        from an earlier preview cannot overwrite a newer preview in the UI.
        That means terminal preview state files are append-only unless the
        runtime periodically prunes them.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(0.0, max_age_seconds))
        removed = 0
        terminal_phases = {"succeeded", "failed", "cancelled"}
        for path in list(self._dir.glob("*.json")):
            payload = self._load_payload(path)
            if payload is None:
                continue
            task_id = str(payload.get("task_id") or "")
            if not task_id.startswith(prefix):
                continue
            request_state = payload.get("request_state")
            if not isinstance(request_state, dict):
                continue
            phase = str(request_state.get("phase") or "").strip().lower()
            if phase not in terminal_phases:
                continue
            updated_at = _parse_iso_datetime(str(payload.get("updated_at") or ""))
            if updated_at is None or updated_at > cutoff:
                continue
            with self._task_guard(task_id):
                current_payload = self._load_payload(self._path(task_id))
                if current_payload is None:
                    continue
                current_state = current_payload.get("request_state")
                current_phase = (
                    str(current_state.get("phase") or "").strip().lower()
                    if isinstance(current_state, dict)
                    else ""
                )
                current_updated_at = _parse_iso_datetime(str(current_payload.get("updated_at") or ""))
                if current_phase not in terminal_phases or current_updated_at is None or current_updated_at > cutoff:
                    continue
                self._path(task_id).unlink(missing_ok=True)
                self._cancel_path(task_id).unlink(missing_ok=True)
                removed += 1
        return removed

    def _path(self, task_id: str) -> Path:
        return self._dir / f"{_safe_task_file_name(task_id)}.json"

    def request_cancel(self, task_id: str) -> Path:
        with self._task_guard(task_id):
            path = self._cancel_path(task_id)
            payload = {
                "task_id": task_id,
                "cancel_requested": True,
                "updated_at": _now_iso(),
            }
            self._atomic_write_json(path, payload)
            return path

    def clear_cancel_request(self, task_id: str) -> None:
        with self._task_guard(task_id):
            try:
                self._cancel_path(task_id).unlink()
            except FileNotFoundError:
                return

    def is_cancel_requested(self, task_id: str) -> bool:
        with self._task_guard(task_id, mode="read"):
            path = self._cancel_path(task_id)
            if not path.is_file():
                return False
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return True
            return bool(payload.get("cancel_requested"))

    def _cancel_path(self, task_id: str) -> Path:
        return self._cancel_dir / f"{_safe_task_file_name(task_id)}.json"

    def _lock_path(self, task_id: str) -> Path:
        return self._lock_dir / f"{_safe_task_file_name(task_id)}.lock"

    def _task_lock(self, task_id: str) -> threading.Lock:
        normalized = _safe_task_file_name(task_id)
        with self._locks_guard:
            lock = self._task_locks.get(normalized)
            if lock is None:
                lock = threading.Lock()
                self._task_locks[normalized] = lock
            return lock

    @contextmanager
    def _task_guard(self, task_id: str, *, mode: str = "write"):
        with self._task_lock(task_id):
            if fcntl is None:
                yield
                return
            if mode not in {"read", "write"}:
                raise ValueError(f"Unsupported lock mode '{mode}'.")
            lock_path = self._lock_path(task_id)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+", encoding="utf-8") as handle:
                lock_mode = fcntl.LOCK_SH if mode == "read" else fcntl.LOCK_EX
                fcntl.flock(handle.fileno(), lock_mode)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load_request_state(self, path: Path) -> dict[str, object] | None:
        payload = self._load_payload(path)
        if payload is None:
            return None
        request_state = payload.get("request_state")
        if isinstance(request_state, dict):
            return request_state
        return None

    def _load_payload(self, path: Path) -> dict[str, object] | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _atomic_write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, indent=2)
                temp_path = handle.name
            Path(temp_path).replace(path)
        finally:
            if temp_path:
                maybe_path = Path(temp_path)
                if maybe_path.exists():
                    maybe_path.unlink(missing_ok=True)


def _parse_iso_datetime(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
