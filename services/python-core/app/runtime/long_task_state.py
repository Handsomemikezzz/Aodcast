from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from app.runtime.request_state_store import RequestStateStore


@dataclass(slots=True)
class LongTaskStateManager:
    request_state_store: RequestStateStore
    task_id: str
    operation: str
    build_request_state: Callable[..., dict[str, object]]
    should_cancel: Callable[[], bool] | None = None
    _progress_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _current_progress: float = field(default=0.0, init=False, repr=False)

    def start(self, *, progress_percent: float, message: str) -> None:
        self._set_current_progress(progress_percent)
        self.request_state_store.save(
            self.task_id,
            self.build_request_state(
                operation=self.operation,
                phase="running",
                progress_percent=progress_percent,
                message=message,
            ),
        )

    def update_running(self, next_percent: float, message: str, *, max_percent: float = 95.0) -> None:
        if self.should_cancel is not None and self.should_cancel():
            return
        with self._progress_lock:
            bounded = min(max_percent, max(self._current_progress, next_percent))
            if bounded <= self._current_progress:
                return
            self._current_progress = bounded
            progress_percent = self._current_progress
        self.request_state_store.save_if_current_phase(
            self.task_id,
            self.build_request_state(
                operation=self.operation,
                phase="running",
                progress_percent=progress_percent,
                message=message,
            ),
            allowed_phases={"running"},
        )

    def start_heartbeat(
        self,
        *,
        start_percent: float,
        max_percent: float,
        step_percent: float,
        interval_seconds: float,
        message: str,
    ) -> tuple[threading.Event, threading.Thread]:
        stop_event = threading.Event()
        self._set_current_progress(start_percent)

        def loop() -> None:
            while not stop_event.wait(interval_seconds):
                if self.should_cancel is not None and self.should_cancel():
                    break
                self.update_running(
                    self._heartbeat_progress_snapshot() + step_percent,
                    message,
                    max_percent=max_percent,
                )

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        return stop_event, thread

    def stop_heartbeat(self, stop_event: threading.Event, thread: threading.Thread, *, timeout_seconds: float = 2.0) -> None:
        stop_event.set()
        thread.join(timeout=timeout_seconds)

    def save_cancelled(self, *, progress_percent: float, message: str) -> None:
        self.request_state_store.save(
            self.task_id,
            self.build_request_state(
                operation=self.operation,
                phase="cancelled",
                progress_percent=progress_percent,
                message=message,
            ),
        )

    def save_failed(self, *, message: str) -> None:
        self.request_state_store.save(
            self.task_id,
            self.build_request_state(
                operation=self.operation,
                phase="failed",
                progress_percent=0.0,
                message=message,
            ),
        )

    def save_finalizing(self, *, progress_percent: float, message: str) -> bool:
        self._set_current_progress(progress_percent)
        return self.request_state_store.save_if_current_phase(
            self.task_id,
            self.build_request_state(
                operation=self.operation,
                phase="running",
                progress_percent=progress_percent,
                message=message,
            ),
            allowed_phases={"running"},
        )

    def save_succeeded(self, *, message: str) -> bool:
        return self.request_state_store.save_if_current_phase(
            self.task_id,
            self.build_request_state(
                operation=self.operation,
                phase="succeeded",
                progress_percent=100.0,
                message=message,
            ),
            allowed_phases={"running"},
        )

    def current_phase(self) -> str:
        state = self.request_state_store.load(self.task_id)
        if isinstance(state, dict):
            phase_value = state.get("phase")
            if isinstance(phase_value, str):
                return phase_value.strip().lower()
        return ""

    def current_progress(self, default: float = 0.0) -> float:
        state = self.request_state_store.load(self.task_id)
        if isinstance(state, dict):
            value = state.get("progress_percent")
            if isinstance(value, (int, float)):
                return float(min(100.0, max(0.0, value)))
        return default

    def _set_current_progress(self, progress_percent: float) -> None:
        with self._progress_lock:
            self._current_progress = progress_percent

    def _heartbeat_progress_snapshot(self) -> float:
        with self._progress_lock:
            return self._current_progress
