from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP_BRIDGE_PATH = REPO_ROOT / "apps/desktop/src/lib/desktopBridge.ts"
HTTP_BRIDGE_PATH = REPO_ROOT / "apps/desktop/src/lib/httpBridge.ts"
BRIDGE_FACTORY_PATH = REPO_ROOT / "apps/desktop/src/lib/bridgeFactory.ts"
APP_PATH = REPO_ROOT / "apps/desktop/src/App.tsx"
HTTP_RUNTIME_PATH = REPO_ROOT / "services/python-core/app/api/http_runtime.py"
RUNTIME_TOKEN_HEADER = "X-AOD-Runtime-Token"
LOOPBACK_ONLY_HOSTS = ("127.0.0.1", "::1")


@dataclass(frozen=True)
class BridgeContract:
    desktop_method: str
    http_method: str
    http_path: str
    operation: str
    streaming: bool = False


HTTP_BRIDGE_CONTRACTS: tuple[BridgeContract, ...] = (
    BridgeContract("listProjects", "GET", "/api/v1/projects", "list_projects"),
    BridgeContract("createSession", "POST", "/api/v1/sessions", "create_session"),
    BridgeContract("updateEpisodeSource", "PUT", "/api/v1/sessions/{session_id}/source", "update_episode_source"),
    BridgeContract("showSession", "GET", "/api/v1/sessions/{session_id}", "show_session"),
    BridgeContract("renameSession", "PATCH", "/api/v1/sessions/{session_id}", "rename_session"),
    BridgeContract("deleteSession", "POST", "/api/v1/sessions/{session_id}:delete", "delete_session"),
    BridgeContract("restoreSession", "POST", "/api/v1/sessions/{session_id}:restore", "restore_session"),
    BridgeContract("startInterview", "POST", "/api/v1/sessions/{session_id}/interview:start", "start_interview"),
    BridgeContract("submitReplyStream", "POST", "/api/v1/sessions/{session_id}/interview:reply-stream", "submit_reply", streaming=True),
    BridgeContract("uploadAttachment", "POST", "/api/v1/sessions/{session_id}/attachments", "upload_attachment"),
    BridgeContract("readAttachment", "GET", "/api/v1/sessions/{session_id}/attachments/{attachment_id}/content", "show_attachment"),
    BridgeContract("requestFinish", "POST", "/api/v1/sessions/{session_id}/interview:finish", "request_finish"),
    BridgeContract("generateScript", "POST", "/api/v1/sessions/{session_id}/script:generate", "generate_script"),
    BridgeContract("showLatestScript", "GET", "/api/v1/sessions/{session_id}/scripts/latest", "show_latest_script"),
    BridgeContract("showScript", "GET", "/api/v1/sessions/{session_id}/scripts/{script_id}", "show_script"),
    BridgeContract("listScripts", "GET", "/api/v1/sessions/{session_id}/scripts", "list_scripts"),
    BridgeContract("renderAudio", "POST", "/api/v1/sessions/{session_id}/audio:render", "render_audio"),
    BridgeContract("regenerateAudioWindow", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}/audio/segments/{segment_id}:regenerate", "regenerate_audio_window"),
    BridgeContract("deleteGeneratedAudio", "DELETE", "/api/v1/sessions/{session_id}/audio", "delete_generated_audio"),
    BridgeContract("deleteArtifactAudio", "DELETE", "/api/v1/artifacts/audio", "delete_artifact_audio"),
    BridgeContract("exportPodcastAudio", "POST", "/api/v1/artifacts/audio/export", "export_podcast_audio"),
    BridgeContract("listVoicePresets", "GET", "/api/v1/voice-studio/presets", "list_voice_presets"),
    BridgeContract("renderVoicePreview", "POST", "/api/v1/voice-studio/preview", "render_voice_preview"),
    BridgeContract("listSpeakerReferences", "GET", "/api/v1/speaker-references", "list_speaker_references"),
    BridgeContract("createSpeakerReference", "POST", "/api/v1/speaker-references", "create_speaker_reference"),
    BridgeContract("updateSpeakerReference", "PATCH", "/api/v1/speaker-references/{reference_id}", "update_speaker_reference"),
    BridgeContract("deleteSpeakerReference", "DELETE", "/api/v1/speaker-references/{reference_id}", "delete_speaker_reference"),
    BridgeContract("selectSpeakerReference", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}/speaker-reference:select", "select_speaker_reference"),
    BridgeContract("saveEditedScript", "PUT", "/api/v1/sessions/{session_id}/scripts/{script_id}/final", "save_script"),
    BridgeContract("deleteScript", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}:delete", "delete_script"),
    BridgeContract("restoreScript", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}:restore", "restore_script"),
    BridgeContract("listScriptRevisions", "GET", "/api/v1/sessions/{session_id}/scripts/{script_id}/revisions", "list_script_revisions"),
    BridgeContract("rollbackScriptRevision", "POST", "/api/v1/sessions/{session_id}/scripts/{script_id}/revisions/{revision_id}:rollback", "rollback_script_revision"),
    BridgeContract("getLocalTTSCapability", "GET", "/api/v1/runtime/tts/local-capability", "show_local_tts_capability"),
    BridgeContract("showLLMConfig", "GET", "/api/v1/config/llm", "show_llm_config"),
    BridgeContract("checkLLMConfig", "GET", "/api/v1/config/llm/preflight", "check_llm_config"),
    BridgeContract("configureLLMProvider", "PUT", "/api/v1/config/llm", "configure_llm_provider"),
    BridgeContract("testLLMConnection", "POST", "/api/v1/config/llm/test", "test_llm_connection"),
    BridgeContract("showLLMProviderStatus", "GET", "/api/v1/config/llm/status", "show_llm_provider_status"),
    BridgeContract("startLLMProviderLogin", "POST", "/api/v1/config/llm/auth:start", "start_llm_provider_login"),
    BridgeContract("showTTSConfig", "GET", "/api/v1/config/tts", "show_tts_config"),
    BridgeContract("configureTTSProvider", "PUT", "/api/v1/config/tts", "configure_tts_provider"),
    BridgeContract("testTTSConnection", "POST", "/api/v1/config/tts/test", "test_tts_connection"),
    BridgeContract("listModelsStatus", "GET", "/api/v1/models", "list_models_status"),
    BridgeContract("showTaskState", "GET", "/api/v1/tasks/{task_id}", "show_task_state"),
    BridgeContract("cancelTask", "POST", "/api/v1/tasks/{task_id}:cancel", "cancel_task"),
    BridgeContract("getMemoryOverview", "GET", "/api/v1/memory", "show_memory_overview"),
    BridgeContract("updateMemorySettings", "PATCH", "/api/v1/memory/settings", "update_memory_settings"),
    BridgeContract("acknowledgeMemory", "POST", "/api/v1/memory:acknowledge", "acknowledge_memory"),
    BridgeContract("listMemories", "GET", "/api/v1/memory/items", "list_memory_items"),
    BridgeContract("getMemory", "GET", "/api/v1/memory/items/{memory_id}", "show_memory_item"),
    BridgeContract("deleteMemory", "DELETE", "/api/v1/memory/items/{memory_id}", "delete_memory_item"),
    BridgeContract("clearAllMemory", "POST", "/api/v1/memory:clear", "clear_memory"),
    BridgeContract("listMemoryUsage", "GET", "/api/v1/memory/usage", "list_memory_usage"),
    BridgeContract("setSessionMemoryMode", "POST", "/api/v1/sessions/{session_id}:memory-mode", "set_session_memory_mode"),
    BridgeContract("listMemoryCandidates", "GET", "/api/v1/sessions/{session_id}/memory-candidates", "list_memory_candidates"),
    BridgeContract("authorizeMemory", "POST", "/api/v1/sessions/{session_id}/memory:authorize", "authorize_memory"),
    BridgeContract("runMemoryMaintenance", "POST", "/api/v1/memory:maintain", "run_memory_maintenance"),
    BridgeContract("listMemorySuperseded", "GET", "/api/v1/memory/superseded", "list_memory_superseded"),
    BridgeContract("findForgetCandidates", "GET", "/api/v1/memory/forget-candidates", "list_forget_candidates"),
    BridgeContract("supersedeMemory", "POST", "/api/v1/memory:supersede", "supersede_memory"),
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
