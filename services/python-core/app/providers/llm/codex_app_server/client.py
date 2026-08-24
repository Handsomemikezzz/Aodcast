from __future__ import annotations

import atexit
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse


PROVIDER_ID = "codex_subscription"
_CLIENT_NAME = "aodcast"
_BASE_INSTRUCTIONS = """You are the language-model engine embedded in Aodcast, a podcast creation app.
Follow the supplied developer instructions and user request. Do not inspect files, run commands,
use tools, browse the web, invoke MCP servers or skills, or modify the local environment. Return only
the requested podcast interview, editorial, summarization, or structured-data content.
""".strip()


class CodexAppServerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CodexModelInfo:
    id: str
    display_name: str
    is_default: bool
    default_reasoning_effort: str | None
    supported_reasoning_efforts: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "is_default": self.is_default,
            "default_reasoning_effort": self.default_reasoning_effort,
            "supported_reasoning_efforts": list(self.supported_reasoning_efforts),
        }


@dataclass(frozen=True, slots=True)
class CodexRateLimit:
    used_percent: float
    window_duration_minutes: int | None
    resets_at: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "used_percent": self.used_percent,
            "window_duration_minutes": self.window_duration_minutes,
            "resets_at": self.resets_at,
        }


@dataclass(frozen=True, slots=True)
class CodexProviderStatus:
    installed: bool
    executable_path: str
    version: str
    authenticated: bool
    auth_mode: str | None
    plan_type: str | None
    account_email: str | None
    models: tuple[CodexModelInfo, ...]
    rate_limit: CodexRateLimit | None
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": PROVIDER_ID,
            "installed": self.installed,
            "executable_path": self.executable_path,
            "version": self.version,
            "authenticated": self.authenticated,
            "auth_mode": self.auth_mode,
            "plan_type": self.plan_type,
            "account_email": self.account_email,
            "models": [model.to_dict() for model in self.models],
            "rate_limit": self.rate_limit.to_dict() if self.rate_limit is not None else None,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class CodexLoginStart:
    login_id: str
    auth_url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": PROVIDER_ID,
            "login_id": self.login_id,
            "auth_url": self.auth_url,
        }


def find_codex_executable() -> str | None:
    configured = os.environ.get("AODCAST_CODEX_BIN", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())

    discovered = shutil.which("codex")
    if discovered:
        return str(Path(discovered).resolve())

    for raw_path in ("/opt/homebrew/bin/codex", "/usr/local/bin/codex"):
        candidate = Path(raw_path)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return None


def _read_codex_version(executable: str) -> str:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    output = (completed.stdout or completed.stderr or "").strip()
    return output


class CodexAppServerClient:
    def __init__(
        self,
        executable: str,
        *,
        request_timeout_seconds: float = 30.0,
        turn_timeout_seconds: float = 600.0,
    ) -> None:
        self.executable = executable
        self.version = _read_codex_version(executable)
        self.request_timeout_seconds = request_timeout_seconds
        self.turn_timeout_seconds = turn_timeout_seconds
        self.runtime_dir = Path(tempfile.mkdtemp(prefix="aodcast-codex-app-server-"))
        self._process: subprocess.Popen[str] | None = None
        self._initialized = False
        self._next_request_id = 0
        self._lifecycle_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._subscribers_lock = threading.Lock()
        self._subscribers: dict[str, list[queue.Queue[dict[str, Any]]]] = {}
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._read_only_permission_id = ""

    def ensure_started(self) -> None:
        with self._lifecycle_lock:
            if self._initialized and self._process is not None and self._process.poll() is None:
                return
            self._stop_process_locked()
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            try:
                process = subprocess.Popen(
                    [self.executable, "app-server", "--listen", "stdio://"],
                    cwd=self.runtime_dir,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
            except OSError as exc:
                raise CodexAppServerError(f"Failed to start Codex app-server: {exc}") from exc
            if process.stdin is None or process.stdout is None or process.stderr is None:
                process.terminate()
                raise CodexAppServerError("Codex app-server did not expose stdio pipes.")
            self._process = process
            threading.Thread(target=self._read_stdout, args=(process,), daemon=True).start()
            threading.Thread(target=self._read_stderr, args=(process,), daemon=True).start()
            try:
                self._request_started(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": _CLIENT_NAME,
                            "title": "Aodcast",
                            "version": "0.1.0",
                        },
                        "capabilities": {"experimentalApi": True},
                    },
                )
                self._send_message({"method": "initialized", "params": {}})
            except Exception:
                self._stop_process_locked()
                raise
            self._initialized = True

    def close(self) -> None:
        with self._lifecycle_lock:
            self._stop_process_locked()
        shutil.rmtree(self.runtime_dir, ignore_errors=True)

    def _stop_process_locked(self) -> None:
        process = self._process
        self._process = None
        self._initialized = False
        self._read_only_permission_id = ""
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def _next_id(self) -> int:
        with self._pending_lock:
            self._next_request_id += 1
            return self._next_request_id

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_started()
        return self._request_started(method, params)

    def _request_started(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        request_id = self._next_id()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = response_queue
        try:
            message: dict[str, Any] = {"method": method, "id": request_id}
            if params is not None:
                message["params"] = params
            self._send_message(message)
            try:
                response = response_queue.get(
                    timeout=timeout_seconds or self.request_timeout_seconds
                )
            except queue.Empty as exc:
                raise CodexAppServerError(f"Codex app-server request timed out: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

        transport_error = response.get("_transport_error")
        if transport_error:
            raise CodexAppServerError(str(transport_error))
        error = response.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "Codex app-server request failed.")
            raise CodexAppServerError(message)
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    def _send_message(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise CodexAppServerError(self._transport_failure_message("Codex app-server is not running."))
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            with self._write_lock:
                process.stdin.write(encoded)
                process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodexAppServerError(self._transport_failure_message(str(exc))) from exc

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            request_id = message.get("id")
            if isinstance(request_id, int):
                if message.get("method"):
                    self._reject_server_request(request_id)
                    continue
                with self._pending_lock:
                    response_queue = self._pending.get(request_id)
                if response_queue is not None:
                    try:
                        response_queue.put_nowait(message)
                    except queue.Full:
                        pass
                continue
            self._dispatch_notification(message)
        self._notify_transport_closed(process)

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        assert process.stderr is not None
        for raw_line in process.stderr:
            line = raw_line.strip()
            if line:
                self._stderr_tail.append(line)

    def _dispatch_notification(self, message: dict[str, Any]) -> None:
        params = message.get("params")
        if not isinstance(params, dict):
            return
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        if not thread_id:
            return
        with self._subscribers_lock:
            subscribers = list(self._subscribers.get(thread_id, ()))
        for subscriber in subscribers:
            subscriber.put(message)

    def _notify_transport_closed(self, process: subprocess.Popen[str]) -> None:
        with self._lifecycle_lock:
            if self._process is process:
                self._initialized = False
        message = self._transport_failure_message("Codex app-server stopped unexpectedly.")
        payload = {"_transport_error": message}
        with self._pending_lock:
            pending = list(self._pending.values())
        for response_queue in pending:
            try:
                response_queue.put_nowait(payload)
            except queue.Full:
                pass
        with self._subscribers_lock:
            subscribers = [item for group in self._subscribers.values() for item in group]
        for subscriber in subscribers:
            subscriber.put(payload)

    def _transport_failure_message(self, fallback: str) -> str:
        if not self._stderr_tail:
            return fallback
        return f"{fallback} Codex reported: {self._stderr_tail[-1]}"

    def _reject_server_request(self, request_id: int) -> None:
        try:
            self._send_message(
                {
                    "id": request_id,
                    "error": {
                        "code": -32000,
                        "message": "Aodcast does not allow Codex tool use or interactive approvals.",
                    },
                }
            )
        except CodexAppServerError:
            return

    def read_account(self) -> dict[str, Any]:
        return self._request("account/read", {"refreshToken": False})

    def list_models(self) -> tuple[CodexModelInfo, ...]:
        result = self._request("model/list", {"limit": 100, "includeHidden": False})
        raw_models = result.get("data")
        if not isinstance(raw_models, list):
            return ()
        models: list[CodexModelInfo] = []
        for raw_model in raw_models:
            if not isinstance(raw_model, dict):
                continue
            model_id = str(raw_model.get("id") or raw_model.get("model") or "").strip()
            if not model_id:
                continue
            efforts: list[str] = []
            raw_efforts = raw_model.get("supportedReasoningEfforts")
            if isinstance(raw_efforts, list):
                for raw_effort in raw_efforts:
                    if isinstance(raw_effort, dict):
                        effort = str(raw_effort.get("reasoningEffort") or "").strip()
                    else:
                        effort = str(raw_effort or "").strip()
                    if effort:
                        efforts.append(effort)
            default_effort = str(raw_model.get("defaultReasoningEffort") or "").strip() or None
            models.append(
                CodexModelInfo(
                    id=model_id,
                    display_name=str(raw_model.get("displayName") or model_id),
                    is_default=bool(raw_model.get("isDefault", False)),
                    default_reasoning_effort=default_effort,
                    supported_reasoning_efforts=tuple(efforts),
                )
            )
        return tuple(models)

    def require_chatgpt_subscription(self) -> None:
        account_result = self.read_account()
        raw_account = account_result.get("account")
        account = raw_account if isinstance(raw_account, dict) else {}
        auth_mode = str(
            account.get("type")
            or account_result.get("authMode")
            or ""
        ).strip()
        if auth_mode not in {
            "chatgpt",
            "chatgptAuthTokens",
            "personalAccessToken",
            "agentIdentity",
        }:
            if auth_mode in {"apiKey", "apikey"}:
                raise CodexAppServerError(
                    "Codex is using API-key billing. Sign in with ChatGPT before using the "
                    "subscription provider."
                )
            raise CodexAppServerError(
                "Codex is not signed in with ChatGPT. Connect ChatGPT in Aodcast Settings."
            )

    def resolve_model(self, requested_model: str) -> str:
        self.require_chatgpt_subscription()
        requested = requested_model.strip()
        models = self.list_models()
        if requested:
            if models and requested not in {model.id for model in models}:
                raise CodexAppServerError(
                    f"Codex model '{requested}' is not available for the signed-in account."
                )
            return requested
        default_model = next((model.id for model in models if model.is_default), "")
        if default_model:
            return default_model
        if models:
            return models[0].id
        raise CodexAppServerError("Codex did not report any available subscription models.")

    def resolve_reasoning_effort(
        self,
        model: str,
        requested_effort: str,
    ) -> str | None:
        effort = requested_effort.strip().lower() or "auto"
        if effort == "auto":
            return None
        selected_model = next((item for item in self.list_models() if item.id == model), None)
        if selected_model is None:
            raise CodexAppServerError(
                f"Cannot validate reasoning effort because Codex model '{model}' is unavailable."
            )
        if effort not in selected_model.supported_reasoning_efforts:
            supported = ", ".join(selected_model.supported_reasoning_efforts) or "model default only"
            raise CodexAppServerError(
                f"Reasoning effort '{effort}' is not supported by Codex model '{model}'. "
                f"Supported values: {supported}."
            )
        return effort

    def read_only_permission_id(self) -> str:
        if self._read_only_permission_id:
            return self._read_only_permission_id
        result = self._request(
            "permissionProfile/list",
            {"cwd": str(self.runtime_dir), "limit": 100},
        )
        profiles = result.get("data")
        if not isinstance(profiles, list):
            raise CodexAppServerError("Codex did not report any permission profiles.")
        for raw_profile in profiles:
            if not isinstance(raw_profile, dict) or not bool(raw_profile.get("allowed", False)):
                continue
            profile_id = str(raw_profile.get("id") or "").strip()
            if profile_id == ":read-only" or "read-only" in profile_id:
                self._read_only_permission_id = profile_id
                return profile_id
        raise CodexAppServerError("Codex does not allow a read-only permission profile.")

    def read_rate_limit(self) -> CodexRateLimit | None:
        try:
            result = self._request("account/rateLimits/read")
        except CodexAppServerError:
            return None
        rate_limits = result.get("rateLimits")
        if not isinstance(rate_limits, dict):
            return None
        primary = rate_limits.get("primary")
        if not isinstance(primary, dict):
            return None
        try:
            used_percent = float(primary.get("usedPercent", 0.0))
        except (TypeError, ValueError):
            used_percent = 0.0
        duration = primary.get("windowDurationMins")
        resets_at = primary.get("resetsAt")
        return CodexRateLimit(
            used_percent=max(0.0, min(100.0, used_percent)),
            window_duration_minutes=int(duration) if isinstance(duration, (int, float)) else None,
            resets_at=int(resets_at) if isinstance(resets_at, (int, float)) else None,
        )

    def status(self) -> CodexProviderStatus:
        account_result = self.read_account()
        raw_account = account_result.get("account")
        account = raw_account if isinstance(raw_account, dict) else {}
        auth_mode = str(
            account.get("type")
            or account_result.get("authMode")
            or ""
        ).strip() or None
        authenticated = auth_mode in {
            "chatgpt",
            "chatgptAuthTokens",
            "personalAccessToken",
            "agentIdentity",
        }
        plan_type = str(
            account.get("planType")
            or account_result.get("planType")
            or ""
        ).strip() or None
        account_email = str(account.get("email") or "").strip() or None
        if authenticated:
            self.read_only_permission_id()
        models = self.list_models() if authenticated else ()
        rate_limit = self.read_rate_limit() if authenticated else None
        if authenticated:
            plan_label = f" ({plan_type})" if plan_type else ""
            message = f"Connected to ChatGPT subscription{plan_label}."
        elif auth_mode in {"apiKey", "apikey"}:
            message = (
                "Codex is currently using API-key billing. Connect ChatGPT before selecting "
                "the subscription provider."
            )
        else:
            message = "Codex is installed but is not signed in with ChatGPT."
        return CodexProviderStatus(
            installed=True,
            executable_path=self.executable,
            version=self.version,
            authenticated=authenticated,
            auth_mode=auth_mode,
            plan_type=plan_type,
            account_email=account_email,
            models=models,
            rate_limit=rate_limit,
            message=message,
        )

    def start_chatgpt_login(self) -> CodexLoginStart:
        result = self._request(
            "account/login/start",
            {
                "type": "chatgpt",
                "useHostedLoginSuccessPage": True,
                "appBrand": "chatgpt",
            },
        )
        login_id = str(result.get("loginId") or "").strip()
        auth_url = str(result.get("authUrl") or "").strip()
        parsed_auth_url = urlparse(auth_url)
        if (
            not login_id
            or parsed_auth_url.scheme != "https"
            or parsed_auth_url.hostname not in {"chatgpt.com", "auth.openai.com"}
        ):
            raise CodexAppServerError("Codex did not return a valid ChatGPT login URL.")
        return CodexLoginStart(login_id=login_id, auth_url=auth_url)

    def stream_turn(
        self,
        *,
        model: str,
        reasoning_effort: str,
        developer_instructions: str,
        user_content: str,
        output_schema: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        self.require_chatgpt_subscription()
        resolved_model = model.strip() or self.resolve_model("")
        resolved_effort = self.resolve_reasoning_effort(resolved_model, reasoning_effort)
        permission_id = self.read_only_permission_id()
        thread_result = self._request(
            "thread/start",
            {
                "model": resolved_model,
                "cwd": str(self.runtime_dir),
                "approvalPolicy": "never",
                "permissions": permission_id,
                "baseInstructions": _BASE_INSTRUCTIONS,
                "developerInstructions": developer_instructions,
                "ephemeral": True,
                "serviceName": _CLIENT_NAME,
            },
        )
        raw_thread = thread_result.get("thread")
        thread = raw_thread if isinstance(raw_thread, dict) else {}
        thread_id = str(thread.get("id") or "").strip()
        if not thread_id:
            raise CodexAppServerError("Codex app-server did not return a thread id.")

        notification_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._subscribers_lock:
            self._subscribers.setdefault(thread_id, []).append(notification_queue)

        turn_id = ""
        turn_finished = False
        accumulated = ""
        final_item_text = ""
        try:
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": user_content}],
                "model": resolved_model,
                "cwd": str(self.runtime_dir),
                "approvalPolicy": "never",
                "permissions": permission_id,
            }
            if resolved_effort is not None:
                turn_params["effort"] = resolved_effort
            if output_schema is not None:
                turn_params["outputSchema"] = output_schema
            turn_result = self._request("turn/start", turn_params)
            raw_turn = turn_result.get("turn")
            turn = raw_turn if isinstance(raw_turn, dict) else {}
            turn_id = str(turn.get("id") or "").strip()
            deadline = time.monotonic() + self.turn_timeout_seconds

            while not turn_finished:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexAppServerError("Codex generation timed out.")
                try:
                    notification = notification_queue.get(timeout=min(remaining, 5.0))
                except queue.Empty:
                    process = self._process
                    if process is None or process.poll() is not None:
                        raise CodexAppServerError(
                            self._transport_failure_message("Codex app-server stopped during generation.")
                        )
                    continue
                transport_error = notification.get("_transport_error")
                if transport_error:
                    raise CodexAppServerError(str(transport_error))
                method = str(notification.get("method") or "")
                params = notification.get("params")
                payload = params if isinstance(params, dict) else {}
                if method == "item/agentMessage/delta":
                    delta = str(payload.get("delta") or "")
                    if delta:
                        accumulated += delta
                        yield delta
                elif method == "item/started":
                    raw_item = payload.get("item")
                    item = raw_item if isinstance(raw_item, dict) else {}
                    item_type = str(item.get("type") or "")
                    if item_type in {
                        "commandExecution",
                        "fileChange",
                        "mcpToolCall",
                        "dynamicToolCall",
                        "webSearch",
                    }:
                        raise CodexAppServerError(
                            f"Codex attempted disallowed tool use: {item_type}."
                        )
                elif method == "item/completed":
                    raw_item = payload.get("item")
                    item = raw_item if isinstance(raw_item, dict) else {}
                    if str(item.get("type") or "") == "agentMessage":
                        final_item_text = str(item.get("text") or "")
                elif method == "turn/completed":
                    completed_turn = payload.get("turn")
                    completed = completed_turn if isinstance(completed_turn, dict) else {}
                    status = str(completed.get("status") or "completed")
                    if status not in {"completed", "succeeded"}:
                        raw_error = completed.get("error")
                        error = raw_error if isinstance(raw_error, dict) else {}
                        message = str(error.get("message") or f"Codex turn ended with status '{status}'.")
                        raise CodexAppServerError(message)
                    turn_finished = True

            if not accumulated and final_item_text:
                yield final_item_text
        except GeneratorExit:
            if turn_id and not turn_finished:
                self._interrupt_turn(thread_id, turn_id)
            raise
        except Exception:
            if turn_id and not turn_finished:
                self._interrupt_turn(thread_id, turn_id)
            raise
        finally:
            with self._subscribers_lock:
                subscribers = self._subscribers.get(thread_id, [])
                if notification_queue in subscribers:
                    subscribers.remove(notification_queue)
                if not subscribers:
                    self._subscribers.pop(thread_id, None)

    def complete_turn(
        self,
        *,
        model: str,
        reasoning_effort: str,
        developer_instructions: str,
        user_content: str,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        return "".join(
            self.stream_turn(
                model=model,
                reasoning_effort=reasoning_effort,
                developer_instructions=developer_instructions,
                user_content=user_content,
                output_schema=output_schema,
            )
        ).strip()

    def _interrupt_turn(self, thread_id: str, turn_id: str) -> None:
        try:
            self._request_started(
                "turn/interrupt",
                {"threadId": thread_id, "turnId": turn_id},
                timeout_seconds=5.0,
            )
        except Exception:
            return


_CLIENT_LOCK = threading.Lock()
_CLIENT: CodexAppServerClient | None = None


def get_codex_app_server_client() -> CodexAppServerClient:
    global _CLIENT
    executable = find_codex_executable()
    if executable is None:
        raise CodexAppServerError(
            "Codex CLI is not installed. Install the official Codex CLI, then try again."
        )
    with _CLIENT_LOCK:
        if _CLIENT is None or _CLIENT.executable != executable:
            if _CLIENT is not None:
                _CLIENT.close()
            _CLIENT = CodexAppServerClient(executable)
        return _CLIENT


def codex_provider_status() -> CodexProviderStatus:
    executable = find_codex_executable()
    if executable is None:
        return CodexProviderStatus(
            installed=False,
            executable_path="",
            version="",
            authenticated=False,
            auth_mode=None,
            plan_type=None,
            account_email=None,
            models=(),
            rate_limit=None,
            message="Codex CLI is not installed.",
        )
    try:
        return get_codex_app_server_client().status()
    except CodexAppServerError as exc:
        return CodexProviderStatus(
            installed=True,
            executable_path=executable,
            version=_read_codex_version(executable),
            authenticated=False,
            auth_mode=None,
            plan_type=None,
            account_email=None,
            models=(),
            rate_limit=None,
            message=str(exc),
        )


def start_codex_login() -> CodexLoginStart:
    return get_codex_app_server_client().start_chatgpt_login()


def _close_global_client() -> None:
    global _CLIENT
    with _CLIENT_LOCK:
        client = _CLIENT
        _CLIENT = None
    if client is not None:
        client.close()


atexit.register(_close_global_client)
