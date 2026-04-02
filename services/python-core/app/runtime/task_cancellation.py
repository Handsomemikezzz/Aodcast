from __future__ import annotations


class TaskCancellationRequested(RuntimeError):
    """Raised when a long-running task should stop due to cancellation."""

