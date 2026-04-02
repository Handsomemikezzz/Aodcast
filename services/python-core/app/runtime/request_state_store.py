from __future__ import annotations

import json
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
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
    return normalized[:180]


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
        with self._task_guard(task_id):
            return self._load_request_state(self._path(task_id))

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
        with self._task_guard(task_id):
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
    def _task_guard(self, task_id: str):
        with self._task_lock(task_id):
            if fcntl is None:
                yield
                return
            lock_path = self._lock_path(task_id)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load_request_state(self, path: Path) -> dict[str, object] | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        request_state = payload.get("request_state")
        if isinstance(request_state, dict):
            return request_state
        return None

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
