from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP_BRIDGE_PATH = REPO_ROOT / "apps/desktop/src/lib/desktopBridge.ts"
HTTP_BRIDGE_PATH = REPO_ROOT / "apps/desktop/src/lib/httpBridge.ts"
BRIDGE_FACTORY_PATH = REPO_ROOT / "apps/desktop/src/lib/bridgeFactory.ts"
APP_PATH = REPO_ROOT / "apps/desktop/src/App.tsx"
MAIN_PATH = REPO_ROOT / "services/python-core/app/main.py"
CLI_PARSER_PATH = REPO_ROOT / "services/python-core/app/cli/parser.py"
HTTP_RUNTIME_PATH = REPO_ROOT / "services/python-core/app/api/http_runtime.py"
RUNTIME_TOKEN_HEADER = "X-AOD-Runtime-Token"
LOOPBACK_ONLY_HOSTS = ("127.0.0.1", "::1")

HTTP_ONLY_BRIDGE_OPERATIONS = (
    "show_latest_script",
    "show_script",
    "list_scripts",
    "delete_generated_audio",
    "delete_artifact_audio",
    "export_podcast_audio",
    "test_llm_connection",
    "show_llm_provider_status",
    "start_llm_provider_login",
    "test_tts_connection",
    "show_memory_overview",
    "update_memory_settings",
    "acknowledge_memory",
    "list_memory_items",
    "show_memory_item",
    "delete_memory_item",
    "clear_memory",
    "list_memory_usage",
    "set_session_memory_mode",
    "list_memory_candidates",
    "authorize_memory",
    "run_memory_maintenance",
    "list_memory_superseded",
    "list_forget_candidates",
    "supersede_memory",
    "update_episode_source",
    "create_speaker_reference",
    "update_speaker_reference",
    "delete_speaker_reference",
    "select_speaker_reference",
    "regenerate_audio_window",
)


@dataclass(frozen=True)
class BridgeContract:
    desktop_method: str
    http_method: str
    http_path: str
    operation: str
    cli_args: tuple[str, ...]
    streaming: bool = False


HTTP_BRIDGE_CONTRACTS: tuple[BridgeContract, ...] = (
    BridgeContract("listProjects", "GET", "/api/v1/projects", "list_projects", ("--list-projects",)),
    BridgeContract("createSession", "POST", "/api/v1/sessions", "create_session", ("--create-session",)),
    BridgeContract("updateEpisodeSource", "PUT", "/api/v1/sessions/{session_id}/source", "update_episode_source", ()),
    BridgeContract("showSession", "GET", "/api/v1/sessions/{session_id}", "show_session", ("--show-session", "session-123")),
    BridgeContract("renameSession", "PATCH", "/api/v1/sessions/{session_id}", "rename_session", ("--rename-session", "session-123", "--session-topic", "Renamed")),
    BridgeContract("deleteSession", "POST", "/api/v1/sessions/{session_id}:delete", "delete_session", ("--delete-session", "session-123")),
    BridgeContract("restoreSession", "POST", "/api/v1/sessions/{session_id}:restore", "restore_session", ("--restore-session", "session-123")),
    BridgeContract("startInterview", "POST", "/api/v1/sessions/{session_id}/interview:start", "start_interview", ("--start-interview", "session-123")),
    BridgeContract("submitReplyStream", "POST", "/api/v1/sessions/{session_id}/interview:reply-stream", "submit_reply", ("--reply-session", "session-123", "--message", "hello"), streaming=True),
    BridgeContract("requestFinish", "POST", "/api/v1/sessions/{session_id}/interview:finish", "request_finish", ("--finish-session", "session-123")),
    BridgeContract("generateScript", "POST", "/api/v1/sessions/{session_id}/script:generate", "generate_script", ("--generate-script", "session-123")),
    BridgeContract("showLatestScript", "GET", "/api/v1/sessions/{session_id}/scripts/latest", "show_latest_script", ("--show-session", "session-123")),
    BridgeContract("showScript", "GET", "/api/v1/sessions/{session_id}/scripts/{script_id}", "show_script", ("--show-session", "session-123")),
    BridgeContract("listScripts", "GET", "/api/v1/sessions/{session_id}/scripts", "list_scripts", ("--list-projects",)),
    BridgeContract("renderAudio", "POST", "/api/v1/sessions/{session_id}/audio:render", "render_audio", ("--render-audio", "session-123")),
    BridgeContract("regenerateAudioWindow", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}/audio/segments/{segment_id}:regenerate", "regenerate_audio_window", ()),
    BridgeContract("deleteGeneratedAudio", "DELETE", "/api/v1/sessions/{session_id}/audio", "delete_generated_audio", ("--render-audio", "session-123")),
    BridgeContract("deleteArtifactAudio", "DELETE", "/api/v1/artifacts/audio", "delete_artifact_audio", ("--render-voice-preview",)),
    BridgeContract("exportPodcastAudio", "POST", "/api/v1/artifacts/audio/export", "export_podcast_audio", ()),
    BridgeContract("listVoicePresets", "GET", "/api/v1/voice-studio/presets", "list_voice_presets", ("--list-voice-presets",)),
    BridgeContract("renderVoicePreview", "POST", "/api/v1/voice-studio/preview", "render_voice_preview", ("--render-voice-preview",)),
    BridgeContract("listSpeakerReferences", "GET", "/api/v1/speaker-references", "list_speaker_references", ("--list-speaker-references",)),
    BridgeContract("createSpeakerReference", "POST", "/api/v1/speaker-references", "create_speaker_reference", ()),
    BridgeContract("updateSpeakerReference", "PATCH", "/api/v1/speaker-references/{reference_id}", "update_speaker_reference", ()),
    BridgeContract("deleteSpeakerReference", "DELETE", "/api/v1/speaker-references/{reference_id}", "delete_speaker_reference", ()),
    BridgeContract("selectSpeakerReference", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}/speaker-reference:select", "select_speaker_reference", ()),
    BridgeContract("saveEditedScript", "PUT", "/api/v1/sessions/{session_id}/scripts/{script_id}/final", "save_script", ("--save-script", "session-123", "--script-final-text", "draft")),
    BridgeContract("deleteScript", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}:delete", "delete_script", ("--delete-script", "session-123")),
    BridgeContract("restoreScript", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}:restore", "restore_script", ("--restore-script", "session-123")),
    BridgeContract("listScriptRevisions", "GET", "/api/v1/sessions/{session_id}/scripts/{script_id}/revisions", "list_script_revisions", ("--list-script-revisions", "session-123")),
    BridgeContract("rollbackScriptRevision", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}/revisions/{revision_id}:rollback", "rollback_script_revision", ("--rollback-script-revision", "session-123", "--revision-id", "rev-1")),
    BridgeContract("getLocalTTSCapability", "GET", "/api/v1/runtime/tts/local-capability", "show_local_tts_capability", ("--show-local-tts-capability",)),
    BridgeContract("showLLMConfig", "GET", "/api/v1/config/llm", "show_llm_config", ("--show-llm-config",)),
    BridgeContract("checkLLMConfig", "GET", "/api/v1/config/llm/preflight", "check_llm_config", ("--check-llm-config",)),
    BridgeContract("configureLLMProvider", "PUT", "/api/v1/config/llm", "configure_llm_provider", ("--configure-llm-provider", "openai")),
    BridgeContract("testLLMConnection", "POST", "/api/v1/config/llm/test", "test_llm_connection", ()),
    BridgeContract("showLLMProviderStatus", "GET", "/api/v1/config/llm/status", "show_llm_provider_status", ()),
    BridgeContract("startLLMProviderLogin", "POST", "/api/v1/config/llm/auth:start", "start_llm_provider_login", ()),
    BridgeContract("showTTSConfig", "GET", "/api/v1/config/tts", "show_tts_config", ("--show-tts-config",)),
    BridgeContract("configureTTSProvider", "PUT", "/api/v1/config/tts", "configure_tts_provider", ("--configure-tts-provider", "local_mlx")),
    BridgeContract("testTTSConnection", "POST", "/api/v1/config/tts/test", "test_tts_connection", ()),
    BridgeContract("listModelsStatus", "GET", "/api/v1/models", "list_models_status", ("--list-models-status",)),
    BridgeContract("showModelStorage", "GET", "/api/v1/models/storage", "show_model_storage", ("--show-model-storage",)),
    BridgeContract("migrateModelStorage", "POST", "/api/v1/models/storage:migrate", "migrate_model_storage", ("--migrate-model-storage", "/tmp/aodcast-models")),
    BridgeContract("resetModelStorage", "POST", "/api/v1/models/storage:reset", "reset_model_storage", ("--reset-model-storage",)),
    BridgeContract("downloadModel", "POST", "/api/v1/models/{model_name}:download", "download_model", ("--download-model", "qwen-tts-0.6B")),
    BridgeContract("deleteModel", "POST", "/api/v1/models/{model_name}:delete", "delete_model", ("--delete-model", "qwen-tts-0.6B")),
    BridgeContract("showTaskState", "GET", "/api/v1/tasks/{task_id}", "show_task_state", ("--show-task-state", "render_audio:session-123")),
    BridgeContract("cancelTask", "POST", "/api/v1/tasks/{task_id}:cancel", "cancel_task", ("--cancel-task", "render_audio:session-123")),
    BridgeContract("getMemoryOverview", "GET", "/api/v1/memory", "show_memory_overview", ()),
    BridgeContract("updateMemorySettings", "PATCH", "/api/v1/memory/settings", "update_memory_settings", ()),
    BridgeContract("acknowledgeMemory", "POST", "/api/v1/memory:acknowledge", "acknowledge_memory", ()),
    BridgeContract("listMemories", "GET", "/api/v1/memory/items", "list_memory_items", ()),
    BridgeContract("getMemory", "GET", "/api/v1/memory/items/{memory_id}", "show_memory_item", ()),
    BridgeContract("deleteMemory", "DELETE", "/api/v1/memory/items/{memory_id}", "delete_memory_item", ()),
    BridgeContract("clearAllMemory", "POST", "/api/v1/memory:clear", "clear_memory", ()),
    BridgeContract("listMemoryUsage", "GET", "/api/v1/memory/usage", "list_memory_usage", ()),
    BridgeContract("setSessionMemoryMode", "POST", "/api/v1/sessions/{session_id}:memory-mode", "set_session_memory_mode", ()),
    BridgeContract("listMemoryCandidates", "GET", "/api/v1/sessions/{session_id}/memory-candidates", "list_memory_candidates", ()),
    BridgeContract("authorizeMemory", "POST", "/api/v1/sessions/{session_id}/memory:authorize", "authorize_memory", ()),
    BridgeContract("runMemoryMaintenance", "POST", "/api/v1/memory:maintain", "run_memory_maintenance", ()),
    BridgeContract("listMemorySuperseded", "GET", "/api/v1/memory/superseded", "list_memory_superseded", ()),
    BridgeContract("findForgetCandidates", "GET", "/api/v1/memory/forget-candidates", "list_forget_candidates", ()),
    BridgeContract("supersedeMemory", "POST", "/api/v1/memory:supersede", "supersede_memory", ()),
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
    if path == HTTP_BRIDGE_PATH and anchor == "return {":
        anchor = "return {\n    async listProjects"
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
