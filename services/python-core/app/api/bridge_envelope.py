from __future__ import annotations


def build_request_state(
    *,
    operation: str,
    phase: str,
    progress_percent: float,
    message: str,
    run_token: str | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {
        "operation": operation,
        "phase": phase,
        "progress_percent": progress_percent,
        "message": message,
    }
    if run_token:
        state["run_token"] = run_token
    return state


def progress_from_request_state(state: dict[str, object] | None, default: float = 0.0) -> float:
    if not isinstance(state, dict):
        return default
    value = state.get("progress_percent")
    if isinstance(value, (int, float)):
        return float(min(100.0, max(0.0, value)))
    return default


def success_envelope(
    data: dict[str, object],
    *,
    operation: str,
    message: str = "completed",
    phase: str = "succeeded",
    progress_percent: float = 100.0,
    run_token: str | None = None,
) -> dict[str, object]:
    payload = dict(data)
    payload["request_state"] = build_request_state(
        operation=operation,
        phase=phase,
        progress_percent=progress_percent,
        message=message,
        run_token=run_token,
    )
    return {"ok": True, "data": payload}


def error_envelope(
    *,
    operation: str,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    phase: str = "failed",
    progress_percent: float = 0.0,
) -> dict[str, object]:
    request_state = build_request_state(
        operation=operation,
        phase=phase,
        progress_percent=progress_percent,
        message=message,
    )
    payload_details = dict(details or {})
    payload_details["request_state"] = request_state
    return {
        "ok": False,
        "request_state": request_state,
        "error": {
            "code": code,
            "message": message,
            "details": payload_details,
        },
    }
