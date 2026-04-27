from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP_BRIDGE_PATH = REPO_ROOT / "apps/desktop/src/lib/desktopBridge.ts"
HTTP_BRIDGE_PATH = REPO_ROOT / "apps/desktop/src/lib/httpBridge.ts"
BRIDGE_FACTORY_PATH = REPO_ROOT / "apps/desktop/src/lib/bridgeFactory.ts"
TAURI_COMMANDS_PATH = REPO_ROOT / "apps/desktop/src-tauri/src/commands.rs"
MAIN_PATH = REPO_ROOT / "services/python-core/app/main.py"
CLI_PARSER_PATH = REPO_ROOT / "services/python-core/app/cli/parser.py"
HTTP_RUNTIME_PATH = REPO_ROOT / "services/python-core/app/api/http_runtime.py"
RUNTIME_TOKEN_HEADER = "X-AOD-Runtime-Token"
LOOPBACK_ONLY_HOSTS = ("127.0.0.1", "::1")


@dataclass(frozen=True)
class BridgeContract:
    desktop_method: str
    tauri_command: str
    http_method: str
    http_path: str
    operation: str
    cli_args: tuple[str, ...]
    migration_phase: str
    long_task: bool = False
    streaming: bool = False


HTTP_BRIDGE_CONTRACTS: tuple[BridgeContract, ...] = (
    BridgeContract("listProjects", "list_projects", "GET", "/api/v1/projects", "list_projects", ("--list-projects",), "P1-core"),
    BridgeContract("createSession", "create_session", "POST", "/api/v1/sessions", "create_session", ("--create-session",), "P1-core"),
    BridgeContract("showSession", "show_session", "GET", "/api/v1/sessions/{session_id}", "show_session", ("--show-session", "session-123"), "P1-core"),
    BridgeContract("renameSession", "rename_session", "PATCH", "/api/v1/sessions/{session_id}", "rename_session", ("--rename-session", "session-123", "--session-topic", "Renamed"), "P1-complete"),
    BridgeContract("deleteSession", "delete_session", "POST", "/api/v1/sessions/{session_id}:delete", "delete_session", ("--delete-session", "session-123"), "P1-complete"),
    BridgeContract("restoreSession", "restore_session", "POST", "/api/v1/sessions/{session_id}:restore", "restore_session", ("--restore-session", "session-123"), "P1-complete"),
    BridgeContract("startInterview", "start_interview", "POST", "/api/v1/sessions/{session_id}/interview:start", "start_interview", ("--start-interview", "session-123"), "P1-core"),
    BridgeContract("submitReplyStream", "submit_reply_stream", "POST", "/api/v1/sessions/{session_id}/interview:reply-stream", "submit_reply", ("--reply-session", "session-123", "--message", "hello"), "P1-core", streaming=True),
    BridgeContract("requestFinish", "request_finish", "POST", "/api/v1/sessions/{session_id}/interview:finish", "request_finish", ("--finish-session", "session-123"), "P1-core"),
    BridgeContract("generateScript", "generate_script", "POST", "/api/v1/sessions/{session_id}/script:generate", "generate_script", ("--generate-script", "session-123"), "P1-core"),
    BridgeContract("showLatestScript", "show_latest_script", "GET", "/api/v1/sessions/{session_id}/scripts/latest", "show_latest_script", ("--show-session", "session-123"), "P1-core"),
    BridgeContract("showScript", "show_script", "GET", "/api/v1/sessions/{session_id}/scripts/{script_id}", "show_script", ("--show-session", "session-123"), "P1-core"),
    BridgeContract("listScripts", "list_scripts", "GET", "/api/v1/sessions/{session_id}/scripts", "list_scripts", ("--list-projects",), "P1-core"),
    BridgeContract("renderAudio", "render_audio", "POST", "/api/v1/sessions/{session_id}/audio:render", "render_audio", ("--render-audio", "session-123"), "P1-core", long_task=True),
    BridgeContract("listVoicePresets", "list_voice_presets", "GET", "/api/v1/voice-studio/presets", "list_voice_presets", ("--list-voice-presets",), "P2-voice-studio"),
    BridgeContract("renderVoicePreview", "render_voice_preview", "POST", "/api/v1/voice-studio/preview", "render_voice_preview", ("--render-voice-preview",), "P2-voice-studio"),
    BridgeContract("renderVoiceTake", "render_voice_take", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}/voice-takes:render", "render_voice_take", ("--render-voice-take", "session-123"), "P2-voice-studio", long_task=True),
    BridgeContract("setFinalVoiceTake", "set_final_voice_take", "POST", "/api/v1/sessions/{session_id}/voice-takes/{take_id}:final", "set_final_voice_take", ("--set-final-voice-take", "session-123"), "P2-voice-studio"),
    BridgeContract("saveEditedScript", "save_edited_script", "PUT", "/api/v1/sessions/{session_id}/scripts/{script_id}/final", "save_script", ("--save-script", "session-123", "--script-final-text", "draft"), "P1-complete"),
    BridgeContract("deleteScript", "delete_script", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}:delete", "delete_script", ("--delete-script", "session-123"), "P1-complete"),
    BridgeContract("restoreScript", "restore_script", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}:restore", "restore_script", ("--restore-script", "session-123"), "P1-complete"),
    BridgeContract("listScriptRevisions", "list_script_revisions", "GET", "/api/v1/sessions/{session_id}/scripts/{script_id}/revisions", "list_script_revisions", ("--list-script-revisions", "session-123"), "P1-complete"),
    BridgeContract("rollbackScriptRevision", "rollback_script_revision", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}/revisions/{revision_id}:rollback", "rollback_script_revision", ("--rollback-script-revision", "session-123", "--revision-id", "rev-1"), "P1-complete"),
    BridgeContract("getLocalTTSCapability", "show_local_tts_capability", "GET", "/api/v1/runtime/tts/local-capability", "show_local_tts_capability", ("--show-local-tts-capability",), "P1-complete"),
    BridgeContract("showLLMConfig", "show_llm_config", "GET", "/api/v1/config/llm", "show_llm_config", ("--show-llm-config",), "P1-complete"),
    BridgeContract("configureLLMProvider", "configure_llm_provider", "PUT", "/api/v1/config/llm", "configure_llm_provider", ("--configure-llm-provider", "openai"), "P1-complete"),
    BridgeContract("showTTSConfig", "show_tts_config", "GET", "/api/v1/config/tts", "show_tts_config", ("--show-tts-config",), "P1-complete"),
    BridgeContract("configureTTSProvider", "configure_tts_provider", "PUT", "/api/v1/config/tts", "configure_tts_provider", ("--configure-tts-provider", "mock"), "P1-complete"),
    BridgeContract("listModelsStatus", "list_models_status", "GET", "/api/v1/models", "list_models_status", ("--list-models-status",), "P1-complete"),
    BridgeContract("showModelStorage", "show_model_storage", "GET", "/api/v1/models/storage", "show_model_storage", ("--show-model-storage",), "P1-complete"),
    BridgeContract("migrateModelStorage", "migrate_model_storage", "POST", "/api/v1/models/storage:migrate", "migrate_model_storage", ("--migrate-model-storage", "/tmp/aodcast-models"), "P1-complete", long_task=True),
    BridgeContract("resetModelStorage", "reset_model_storage", "POST", "/api/v1/models/storage:reset", "reset_model_storage", ("--reset-model-storage",), "P1-complete"),
    BridgeContract("downloadModel", "download_model", "POST", "/api/v1/models/{model_name}:download", "download_model", ("--download-model", "qwen-tts-0.6B"), "P1-complete", long_task=True),
    BridgeContract("deleteModel", "delete_model", "POST", "/api/v1/models/{model_name}:delete", "delete_model", ("--delete-model", "qwen-tts-0.6B"), "P1-complete"),
    BridgeContract("showTaskState", "show_task_state", "GET", "/api/v1/tasks/{task_id}", "show_task_state", ("--show-task-state", "render_audio:session-123"), "P1-core", long_task=True),
    BridgeContract("cancelTask", "cancel_task", "POST", "/api/v1/tasks/{task_id}:cancel", "cancel_task", ("--cancel-task", "render_audio:session-123"), "P1-core", long_task=True),
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_balanced_block(text: str, anchor: str) -> str:
    start = text.find(anchor)
    if start == -1:
        raise AssertionError(f"Could not find anchor {anchor!r}")
    brace_start = text.find("{", start)
    if brace_start == -1:
        raise AssertionError(f"Could not find opening brace after {anchor!r}")

    depth = 0
    block_start = brace_start + 1
    block_end = None
    for index in range(brace_start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                block_end = index
                break
    if block_end is None:
        raise AssertionError(f"Could not find closing brace after {anchor!r}")
    return text[block_start:block_end]


def extract_interface_methods(path: Path = DESKTOP_BRIDGE_PATH, interface_name: str = "DesktopBridge") -> list[str]:
    body = extract_balanced_block(read_text(path), f"export interface {interface_name}")
    return re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", body, re.MULTILINE)


def extract_return_object_methods(path: Path, anchor: str = "return {") -> list[str]:
    body = extract_balanced_block(read_text(path), anchor)
    methods: list[str] = []
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        if depth == 0:
            match = re.match(r"(?:async\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?::|\()", stripped)
            if match:
                methods.append(match.group(1))
        depth += line.count("{") - line.count("}")
    return methods


def extract_tauri_commands(path: Path = TAURI_COMMANDS_PATH) -> list[str]:
    text = read_text(path)
    return re.findall(r"#\[tauri::command\]\s*pub(?:\s+async)?\s+fn\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.MULTILINE)
