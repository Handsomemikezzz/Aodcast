import { invoke } from "@tauri-apps/api/core";

import {
  ConfigureLLMInput,
  ConfigureTTSInput,
  CreateSessionInput,
  DesktopBridge,
  DesktopBridgeError,
  ListProjectsOptions,
  ShowSessionOptions,
} from "./desktopBridge";
import { asRequestState } from "./requestState";
import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  ModelStatus,
  RequestState,
  ScriptRevisionRecord,
  SessionProject,
  TTSProviderConfig,
  TTSCapability,
  LLMProviderConfig,
} from "../types";

type BridgeShape<T> = {
  project?: SessionProject;
  projects?: SessionProject[];
  revisions?: ScriptRevisionRecord[];
  llm_config?: LLMProviderConfig;
  tts_capability?: TTSCapability;
  tts_config?: TTSProviderConfig;
  models?: ModelStatus[];
  request_state?: RequestState;
  task_state?: RequestState | null;
  task_id?: string;
  message?: string;
  path?: string;
} & T;

export class TauriBridgeInvocationError extends Error {
  readonly code: string;
  readonly details?: Record<string, unknown>;
  readonly requestState?: RequestState;

  constructor(
    message: string,
    options: {
      code: string;
      details?: Record<string, unknown>;
      requestState?: RequestState;
    },
  ) {
    super(message);
    this.name = options.code || "desktop_bridge_error";
    this.code = options.code;
    this.details = options.details;
    this.requestState = options.requestState;
  }
}

function normalizeError(error: unknown): Error {
  if (typeof error === "object" && error !== null) {
    const candidate = error as Partial<DesktopBridgeError>;
    if (typeof candidate.message === "string") {
      const details =
        typeof candidate.details === "object" && candidate.details !== null
          ? (candidate.details as Record<string, unknown>)
          : undefined;
      const requestState = asRequestState(details?.request_state) ?? undefined;
      return new TauriBridgeInvocationError(candidate.message, {
        code: candidate.code || "desktop_bridge_error",
        details,
        requestState,
      });
    }
  }
  if (error instanceof Error) {
    return error;
  }
  return new Error(String(error));
}

async function callBridge<T>(command: string, payload?: Record<string, unknown>): Promise<BridgeShape<T>> {
  try {
    return await invoke<BridgeShape<T>>(command, payload);
  } catch (error) {
    throw normalizeError(error);
  }
}

function cleanPayload(payload: Record<string, unknown>): Record<string, unknown> | undefined {
  const entries = Object.entries(payload).filter(([, value]) => value !== undefined && value !== "");
  if (entries.length === 0) {
    return undefined;
  }
  return Object.fromEntries(entries);
}

export function createTauriBridge(): DesktopBridge {
  return {
    async listProjects(options?: ListProjectsOptions) {
      const response = await callBridge<{}>("list_projects", cleanPayload({
        search: options?.search?.trim(),
        includeDeleted: options?.includeDeleted ?? undefined,
      }));
      return response.projects ?? [];
    },
    async createSession(input: CreateSessionInput) {
      const response = await callBridge<{}>("create_session", {
        topic: input.topic,
        creationIntent: input.creationIntent,
      });
      return response.project!;
    },
    async showSession(sessionId: string, options?: ShowSessionOptions) {
      const response = await callBridge<{}>("show_session", cleanPayload({
        sessionId,
        includeDeleted: options?.includeDeleted ?? undefined,
      }));
      return response.project!;
    },
    async renameSession(sessionId: string, topic: string) {
      const response = await callBridge<{}>("rename_session", {
        sessionId,
        topic,
      });
      return response.project!;
    },
    async deleteSession(sessionId: string) {
      const response = await callBridge<{}>("delete_session", {
        sessionId,
      });
      return response.project!;
    },
    async restoreSession(sessionId: string) {
      const response = await callBridge<{}>("restore_session", {
        sessionId,
      });
      return response.project!;
    },
    async startInterview(sessionId: string) {
      return callBridge<InterviewTurnResult>("start_interview", { sessionId });
    },
    async submitReply(sessionId: string, message: string, userRequestedFinish = false) {
      return callBridge<InterviewTurnResult>("submit_reply", {
        sessionId,
        message,
        userRequestedFinish,
      });
    },
    async requestFinish(sessionId: string) {
      return callBridge<InterviewTurnResult>("request_finish", { sessionId });
    },
    async generateScript(sessionId: string) {
      return callBridge<GenerationResult>("generate_script", { sessionId });
    },
    async renderAudio(sessionId: string) {
      return callBridge<AudioRenderResult>("render_audio", { sessionId });
    },
    async saveEditedScript(sessionId: string, finalText: string) {
      const response = await callBridge<{}>("save_edited_script", {
        sessionId,
        finalText,
      });
      return response.project!;
    },
    async deleteScript(sessionId: string) {
      const response = await callBridge<{}>("delete_script", {
        sessionId,
      });
      return response.project!;
    },
    async restoreScript(sessionId: string) {
      const response = await callBridge<{}>("restore_script", {
        sessionId,
      });
      return response.project!;
    },
    async listScriptRevisions(sessionId: string) {
      const response = await callBridge<{}>("list_script_revisions", {
        sessionId,
      });
      return response.revisions ?? [];
    },
    async rollbackScriptRevision(sessionId: string, revisionId: string) {
      const response = await callBridge<{}>("rollback_script_revision", {
        sessionId,
        revisionId,
      });
      return response.project!;
    },
    async getLocalTTSCapability() {
      const response = await callBridge<{}>("show_local_tts_capability");
      return response.tts_capability!;
    },
    async showLLMConfig() {
      const response = await callBridge<{}>("show_llm_config");
      return response.llm_config!;
    },
    async configureLLMProvider(input: ConfigureLLMInput) {
      const response = await callBridge<{}>("configure_llm_provider", {
        provider: input.provider,
        model: input.model,
        baseUrl: input.base_url,
        apiKey: input.api_key,
      });
      return response.llm_config!;
    },
    async showTTSConfig() {
      const response = await callBridge<{}>("show_tts_config");
      return response.tts_config!;
    },
    async configureTTSProvider(input: ConfigureTTSInput) {
      const shouldClearLocalModelPath = input.local_model_path.trim() === "";
      const response = await callBridge<{}>("configure_tts_provider", {
        provider: input.provider,
        model: input.model,
        baseUrl: input.base_url,
        apiKey: input.api_key,
        voice: input.voice,
        audioFormat: input.audio_format,
        localRuntime: input.local_runtime,
        localModelPath: shouldClearLocalModelPath ? null : input.local_model_path,
        clearLocalModelPath: shouldClearLocalModelPath,
      });
      return response.tts_config!;
    },
    async listModelsStatus() {
      const response = await callBridge<{}>("list_models_status");
      return response.models ?? [];
    },
    async downloadModel(modelName: string) {
      const response = await callBridge<{}>("download_model", { modelName });
      return {
        message: typeof response.message === "string" ? response.message : "ok",
        path: typeof response.path === "string" ? response.path : undefined,
        task_id: typeof response.task_id === "string" ? response.task_id : undefined,
        request_state: asRequestState(response.request_state) ?? undefined,
      };
    },
    async deleteModel(modelName: string) {
      const response = await callBridge<{}>("delete_model", { modelName });
      return {
        message: typeof response.message === "string" ? response.message : "ok",
        path: typeof response.path === "string" ? response.path : undefined,
      };
    },
    async showTaskState(taskId: string) {
      const response = await callBridge<{}>("show_task_state", { taskId });
      return asRequestState(response.task_state);
    },
    async cancelTask(taskId: string) {
      const response = await callBridge<{}>("cancel_task", { taskId });
      return asRequestState(response.task_state) ?? asRequestState(response.request_state);
    },
  };
}
