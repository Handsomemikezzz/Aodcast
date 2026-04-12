import { DesktopBridge } from "./desktopBridge";
import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  LLMProviderConfig,
  ModelStatus,
  RequestState,
  ScriptRevisionRecord,
  SessionProject,
  TTSProviderConfig,
  TTSCapability,
} from "../types";

/** Shown when the UI runs in a plain browser (no Tauri → no Python bridge). */
export const WEB_BACKEND_UNAVAILABLE =
  "Aodcast backend runs only inside the Tauri desktop app. Use ./scripts/dev/run-desktop.sh — plain Vite in a browser has no Python/LLM bridge.";

function deny<T>(): () => Promise<T> {
  return async () => {
    throw new Error(WEB_BACKEND_UNAVAILABLE);
  };
}

/** Used when `window` has no Tauri shell (e.g. `pnpm dev:web`). No in-browser mock data. */
export function createWebBackendUnavailableBridge(): DesktopBridge {
  return {
    listProjects: deny<SessionProject[]>(),
    createSession: deny<SessionProject>(),
    showSession: deny<SessionProject>(),
    renameSession: deny<SessionProject>(),
    deleteSession: deny<SessionProject>(),
    restoreSession: deny<SessionProject>(),
    startInterview: deny<InterviewTurnResult>(),
    submitReply: deny<InterviewTurnResult>(),
    requestFinish: deny<InterviewTurnResult>(),
    generateScript: deny<GenerationResult>(),
    renderAudio: deny<AudioRenderResult>(),
    saveEditedScript: deny<SessionProject>(),
    deleteScript: deny<SessionProject>(),
    restoreScript: deny<SessionProject>(),
    listScriptRevisions: deny<ScriptRevisionRecord[]>(),
    rollbackScriptRevision: deny<SessionProject>(),
    getLocalTTSCapability: deny<TTSCapability>(),
    showLLMConfig: deny<LLMProviderConfig>(),
    configureLLMProvider: deny<LLMProviderConfig>(),
    showTTSConfig: deny<TTSProviderConfig>(),
    configureTTSProvider: deny<TTSProviderConfig>(),
    listModelsStatus: deny<ModelStatus[]>(),
    downloadModel: deny<{ message: string; path?: string; task_id?: string; request_state?: RequestState }>(),
    deleteModel: deny<{ message: string; path?: string }>(),
    showTaskState: deny<RequestState | null>(),
    cancelTask: deny<RequestState | null>(),
  };
}
