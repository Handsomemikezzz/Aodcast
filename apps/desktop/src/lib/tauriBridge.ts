import { invoke } from "@tauri-apps/api/core";

import {
  ConfigureTTSInput,
  CreateSessionInput,
  DesktopBridge,
  DesktopBridgeError,
} from "./desktopBridge";
import { asRequestState } from "./requestState";
import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  ModelStatus,
  RequestState,
  SessionProject,
  TTSProviderConfig,
  TTSCapability,
} from "../types";

type BridgeShape<T> = {
  project?: SessionProject;
  projects?: SessionProject[];
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

export function createTauriBridge(): DesktopBridge {
  return {
    async listProjects() {
      const response = await callBridge<{}>("list_projects");
      return response.projects ?? [];
    },
    async createSession(input: CreateSessionInput) {
      const response = await callBridge<{}>("create_session", {
        topic: input.topic,
        creation_intent: input.creationIntent,
      });
      return response.project!;
    },
    async startInterview(sessionId: string) {
      return callBridge<InterviewTurnResult>("start_interview", { session_id: sessionId });
    },
    async submitReply(sessionId: string, message: string, userRequestedFinish = false) {
      return callBridge<InterviewTurnResult>("submit_reply", {
        session_id: sessionId,
        message,
        user_requested_finish: userRequestedFinish,
      });
    },
    async requestFinish(sessionId: string) {
      return callBridge<InterviewTurnResult>("request_finish", { session_id: sessionId });
    },
    async generateScript(sessionId: string) {
      return callBridge<GenerationResult>("generate_script", { session_id: sessionId });
    },
    async renderAudio(sessionId: string) {
      return callBridge<AudioRenderResult>("render_audio", { session_id: sessionId });
    },
    async saveEditedScript(sessionId: string, finalText: string) {
      const response = await callBridge<{}>("save_edited_script", {
        session_id: sessionId,
        final_text: finalText,
      });
      return response.project!;
    },
    async getLocalTTSCapability() {
      const response = await callBridge<{}>("show_local_tts_capability");
      return response.tts_capability!;
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
        base_url: input.base_url,
        api_key: input.api_key,
        voice: input.voice,
        audio_format: input.audio_format,
        local_runtime: input.local_runtime,
        local_model_path: shouldClearLocalModelPath ? null : input.local_model_path,
        clear_local_model_path: shouldClearLocalModelPath,
      });
      return response.tts_config!;
    },
    async listModelsStatus() {
      const response = await callBridge<{}>("list_models_status");
      return response.models ?? [];
    },
    async downloadModel(modelName: string) {
      const response = await callBridge<{}>("download_model", { model_name: modelName });
      return {
        message: typeof response.message === "string" ? response.message : "ok",
        path: typeof response.path === "string" ? response.path : undefined,
        task_id: typeof response.task_id === "string" ? response.task_id : undefined,
        request_state: asRequestState(response.request_state) ?? undefined,
      };
    },
    async deleteModel(modelName: string) {
      const response = await callBridge<{}>("delete_model", { model_name: modelName });
      return {
        message: typeof response.message === "string" ? response.message : "ok",
        path: typeof response.path === "string" ? response.path : undefined,
      };
    },
    async showTaskState(taskId: string) {
      const response = await callBridge<{}>("show_task_state", { task_id: taskId });
      return asRequestState(response.task_state);
    },
    async cancelTask(taskId: string) {
      const response = await callBridge<{}>("cancel_task", { task_id: taskId });
      return asRequestState(response.task_state) ?? asRequestState(response.request_state);
    },
  };
}
