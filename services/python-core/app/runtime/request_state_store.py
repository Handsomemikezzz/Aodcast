from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


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

    def bootstrap(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, task_id: str, request_state: dict[str, object]) -> Path:
        path = self._path(task_id)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        payload = {
            "task_id": task_id,
            "request_state": request_state,
            "updated_at": _now_iso(),
        }
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(path)
        return path

    def load(self, task_id: str) -> dict[str, object] | None:
        path = self._path(task_id)
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

    def _path(self, task_id: str) -> Path:
        return self._dir / f"{_safe_task_file_name(task_id)}.json"
