import { invoke } from "@tauri-apps/api/core";

import type {
  ConfigureLLMInput,
  ConfigureTTSInput,
  CreateSessionInput,
  DesktopBridge,
  DesktopBridgeError,
  ListProjectsOptions,
  RenderAudioOptions,
  RenderVoicePreviewOptions,
  ShowSessionOptions,
} from "./desktopBridge";
import { asRequestState } from "./requestState";
import type {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  LLMProviderConfig,
  ModelStorageStatus,
  ModelStatus,
  RequestState,
  RuntimeInfo,
  ScriptRecord,
  ScriptRevisionRecord,
  SessionProject,
  TTSCapability,
  TTSProviderConfig,
  VoicePreset,
  VoicePresetCatalog,
  VoicePreviewResult,
  VoiceRenderSettings,
  VoiceStylePreset,
  VoiceTakeRenderResult,
} from "../types";

export const HTTP_BACKEND_UNAVAILABLE =
  "Aodcast backend runtime is unavailable. Start the desktop app or a local HTTP runtime before using the browser shell.";

type HttpBridgeOptions = {
  ensureRuntime?: () => Promise<{ base_url: string }>;
  baseUrl?: string;
};

type EnvelopeSuccess<T> = {
  ok: true;
  data: T;
};

type EnvelopeFailure = {
  ok: false;
  request_state?: RequestState;
  error?: DesktopBridgeError;
};

type BridgeEnvelope<T> = EnvelopeSuccess<T> | EnvelopeFailure;

type BridgeShape<T> = {
  project?: SessionProject;
  projects?: SessionProject[];
  scripts?: ScriptRecord[];
  session_id?: string;
  script_id?: string;
  revisions?: ScriptRevisionRecord[];
  llm_config?: LLMProviderConfig;
  tts_capability?: TTSCapability;
  tts_config?: TTSProviderConfig;
  models?: ModelStatus[];
  model_storage?: ModelStorageStatus;
  request_state?: RequestState;
  task_state?: RequestState | null;
  task_id?: string;
  message?: string;
  path?: string;
  runtime?: RuntimeInfo;
  voices?: VoicePreset[];
  styles?: VoiceStylePreset[];
  standard_preview_text?: string;
  take?: VoiceTakeRenderResult["take"];
  settings?: VoiceRenderSettings;
} & T;

type RuntimeContext = {
  base_url: string;
};

export class HttpBridgeInvocationError extends Error {
  readonly code: string;
  readonly details?: Record<string, unknown>;
  readonly requestState?: RequestState;
  readonly runtime?: RuntimeInfo;

  constructor(
    message: string,
    options: {
      code: string;
      details?: Record<string, unknown>;
      requestState?: RequestState;
      runtime?: RuntimeInfo;
    },
  ) {
    super(message);
    this.name = options.code || "desktop_bridge_error";
    this.code = options.code;
    this.details = options.details;
    this.requestState = options.requestState;
    this.runtime = options.runtime;
  }
}

function asRuntimeInfo(value: unknown): RuntimeInfo | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const candidate = value as Partial<RuntimeInfo>;
  if (
    typeof candidate.pid !== "number"
    || !Number.isFinite(candidate.pid)
    || typeof candidate.started_at_unix !== "number"
    || !Number.isFinite(candidate.started_at_unix)
    || typeof candidate.build_token !== "string"
    || candidate.build_token.length === 0
  ) {
    return undefined;
  }
  const runtimeInfo: RuntimeInfo = {
    pid: candidate.pid,
    started_at_unix: candidate.started_at_unix,
    build_token: candidate.build_token,
  };
  return runtimeInfo;
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function ensureDesktopRuntime(): Promise<RuntimeContext> {
  return invoke<RuntimeContext>("ensure_http_runtime");
}

function normalizeError(error: unknown): Error {
  if (typeof error === "object" && error !== null && (error as { name?: string }).name === "AbortError") {
    return new Error("Reply stream was interrupted. You can send again.");
  }
  if (error instanceof TypeError) {
    const message = error.message.trim();
    if (/failed to fetch|networkerror|load failed/i.test(message)) {
      return new Error(HTTP_BACKEND_UNAVAILABLE);
    }
  }
  if (typeof error === "object" && error !== null) {
    const candidate = error as Partial<DesktopBridgeError>;
    if (typeof candidate.message === "string") {
      const details =
        typeof candidate.details === "object" && candidate.details !== null
          ? (candidate.details as Record<string, unknown>)
          : undefined;
      const requestState = asRequestState(details?.request_state) ?? undefined;
      const runtime = asRuntimeInfo(candidate.details?.runtime);
      return new HttpBridgeInvocationError(candidate.message, {
        code: candidate.code || "desktop_bridge_error",
        details,
        requestState,
        runtime,
      });
    }
  }
  if (error instanceof Error) {
    return error;
  }
  return new Error(String(error));
}

function buildUrl(baseUrl: string, path: string, query?: Record<string, string | boolean | undefined>): string {
  const url = new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  for (const [key, value] of Object.entries(query || {})) {
    if (value === undefined || value === "") continue;
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function voicePreviewFromState(state: RequestState): VoicePreviewResult | null {
  if (state.phase !== "succeeded" || !state.audio_path || !state.provider || !state.model || !state.settings) {
    return null;
  }
  const result: VoicePreviewResult = {
    provider: state.provider,
    model: state.model,
    audio_path: state.audio_path,
    settings: state.settings,
    request_state: state,
  };
  return result;
}

async function waitForVoicePreview(
  showTaskState: (taskId: string) => Promise<RequestState | null>,
  taskId: string,
  options?: RenderVoicePreviewOptions,
): Promise<VoicePreviewResult> {
  const started = Date.now();
  const timeoutMs = 10 * 60 * 1000;
  while (Date.now() - started < timeoutMs) {
    await delay(1000);
    const state = await showTaskState(taskId);
    if (!state) continue;
    options?.onState?.(state);
    const result = voicePreviewFromState(state);
    if (result) return result;
    if (state.phase === "failed" || state.phase === "cancelled") {
      throw new Error(state.message || "Voice preview rendering failed.");
    }
  }
  throw new Error("Voice preview rendering timed out.");
}

function serializeVoiceSettings(settings: VoiceRenderSettings): Record<string, string | number> {
  const payload: Record<string, string | number> = {
    voice_id: settings.voice_id,
    voice_name: settings.voice_name ?? "",
    style_id: settings.style_id,
    style_name: settings.style_name ?? "",
    speed: settings.speed,
    language: settings.language ?? "zh",
    audio_format: settings.audio_format ?? "wav",
    preview_text: settings.preview_text ?? "",
  };
  return payload;
}

export function createHttpBridge(options?: HttpBridgeOptions): DesktopBridge {
  let runtimePromise: Promise<RuntimeContext> | null = null;
  let runtimeTokenPromise: Promise<string | null> | null = null;
  const fallbackBaseUrl = options?.baseUrl ?? "http://127.0.0.1:8765";

  async function getRuntime(): Promise<RuntimeContext> {
    if (!runtimePromise) {
      runtimePromise = (async () => {
        if (options?.ensureRuntime) return options.ensureRuntime();
        if (isTauriRuntime()) return ensureDesktopRuntime();
        return ({ base_url: fallbackBaseUrl });
      })();
    }
    return runtimePromise;
  }

  async function getRuntimeToken(baseUrl: string): Promise<string | null> {
    if (!runtimeTokenPromise) {
      runtimeTokenPromise = (async () => {
        try {
          const response = await fetch(buildUrl(baseUrl, "/api/v1/runtime/bootstrap"), {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({}),
          });
          if (!response.ok) return null;
          const payload = (await response.json()) as BridgeEnvelope<{ token?: string }>;
          if (payload.ok && typeof payload.data.token === "string") {
            return payload.data.token;
          }
          return null;
        } catch {
          return null;
        }
      })();
    }
    const token = await runtimeTokenPromise;
    if (token === null) {
      runtimeTokenPromise = null;
    }
    return token;
  }

  async function callHttp<T>(
    path: string,
    init?: RequestInit & { query?: Record<string, string | boolean | undefined>; needsToken?: boolean },
    retryOnAuthFailure = true,
  ): Promise<BridgeShape<T>> {
    try {
      const runtime = await getRuntime();
      const headers = new Headers(init?.headers);
      headers.set("Content-Type", "application/json");
      if (init?.needsToken) {
        const token = await getRuntimeToken(runtime.base_url);
        if (token) headers.set("X-AOD-Runtime-Token", token);
      }
      const response = await fetch(buildUrl(runtime.base_url, path, init?.query), {
        method: init?.method ?? "GET",
        headers,
        body: init?.body,
      });
      if (init?.needsToken && retryOnAuthFailure && (response.status === 401 || response.status === 403)) {
        runtimeTokenPromise = null;
        return callHttp<T>(path, init, false);
      }
      let payload: BridgeEnvelope<BridgeShape<T>>;
      try {
        payload = (await response.json()) as BridgeEnvelope<BridgeShape<T>>;
      } catch {
        throw new Error(HTTP_BACKEND_UNAVAILABLE);
      }
      if (payload.ok) {
        return payload.data;
      }
      throw payload.error ?? new Error("HTTP bridge request failed.");
    } catch (error) {
      throw normalizeError(error);
    }
  }

  async function streamReply(
    sessionId: string,
    message: string,
    onChunk: (delta: string) => void,
    userRequestedFinish = false,
    signal?: AbortSignal,
  ): Promise<InterviewTurnResult> {
    const runtime = await getRuntime();
    const response = await fetch(buildUrl(runtime.base_url, `/api/v1/sessions/${encodeURIComponent(sessionId)}/interview:reply-stream`), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        user_requested_finish: userRequestedFinish,
      }),
      signal,
    });
    if (!response.ok || !response.body) {
      let payload: BridgeEnvelope<InterviewTurnResult> | null = null;
      try {
        payload = (await response.json()) as BridgeEnvelope<InterviewTurnResult>;
      } catch {
        throw new Error(HTTP_BACKEND_UNAVAILABLE);
      }
      if (payload && !payload.ok) {
        throw payload.error ?? new Error("Streaming reply failed.");
      }
      throw new Error("Streaming reply failed.");
    }

    const decoder = new TextDecoder();
    const reader = response.body.getReader();
    let buffer = "";
    let finalPayload: BridgeEnvelope<InterviewTurnResult> | null = null;

    const flushEvent = (chunk: string): boolean => {
      const lines = chunk.split("\n");
      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      if (dataLines.length === 0) return false;
      const parsed = JSON.parse(dataLines.join("\n")) as BridgeEnvelope<InterviewTurnResult> | { ok: true; type: "chunk"; delta: string };
      if ("type" in parsed && parsed.type === "chunk") {
        onChunk(parsed.delta);
        return false;
      }
      if (eventName === "final") {
        finalPayload = parsed as BridgeEnvelope<InterviewTurnResult>;
        return true;
      }
      return false;
    };

    try {
      readLoop:
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let separatorIndex = buffer.indexOf("\n\n");
        while (separatorIndex >= 0) {
          const eventChunk = buffer.slice(0, separatorIndex);
          buffer = buffer.slice(separatorIndex + 2);
          const reachedFinalEvent = flushEvent(eventChunk);
          if (reachedFinalEvent) {
            try {
              await reader.cancel();
            } catch {
              /* ignore */
            }
            break readLoop;
          }
          separatorIndex = buffer.indexOf("\n\n");
        }
      }
    } catch (err) {
      try {
        await reader.cancel();
      } catch {
        /* ignore */
      }
      throw normalizeError(err);
    }
    if (!finalPayload) {
      throw new Error("Streaming reply finished without a final payload.");
    }
    const resolvedFinalPayload = finalPayload as BridgeEnvelope<InterviewTurnResult>;
    if (!resolvedFinalPayload.ok) {
      throw resolvedFinalPayload.error ?? new Error("Streaming reply failed.");
    }
    return resolvedFinalPayload.data;
  }

  return {
    async listProjects(options?: ListProjectsOptions) {
      const response = await callHttp<{}>("/api/v1/projects", {
        query: {
          search: options?.search?.trim(),
          include_deleted: options?.includeDeleted,
        },
      });
      return response.projects ?? [];
    },
    async createSession(input: CreateSessionInput) {
      const response = await callHttp<{}>("/api/v1/sessions", {
        method: "POST",
        body: JSON.stringify({
          topic: input.topic,
          creation_intent: input.creationIntent,
        }),
      });
      return response.project!;
    },
    async showSession(sessionId: string, options?: ShowSessionOptions) {
      const response = await callHttp<{}>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, {
        query: {
          include_deleted: options?.includeDeleted,
        },
      });
      return response.project!;
    },
    async renameSession(sessionId: string, topic: string) {
      const response = await callHttp<{}>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, {
        method: "PATCH",
        body: JSON.stringify({ topic }),
      });
      return response.project!;
    },
    async deleteSession(sessionId: string) {
      const response = await callHttp<{}>(`/api/v1/sessions/${encodeURIComponent(sessionId)}:delete`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      return response.project!;
    },
    async restoreSession(sessionId: string) {
      const response = await callHttp<{}>(`/api/v1/sessions/${encodeURIComponent(sessionId)}:restore`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      return response.project!;
    },
    async startInterview(sessionId: string) {
      return callHttp<InterviewTurnResult>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/interview:start`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    async submitReply(sessionId: string, message: string, userRequestedFinish = false) {
      return callHttp<InterviewTurnResult>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/interview:reply`, {
        method: "POST",
        body: JSON.stringify({
          message,
          user_requested_finish: userRequestedFinish,
        }),
      });
    },
    async submitReplyStream(sessionId, message, onChunk, userRequestedFinish = false, signal?: AbortSignal) {
      return streamReply(sessionId, message, onChunk, userRequestedFinish, signal);
    },
    async requestFinish(sessionId: string) {
      return callHttp<InterviewTurnResult>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/interview:finish`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    async generateScript(sessionId: string) {
      return callHttp<GenerationResult>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/script:generate`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    async showLatestScript(sessionId: string) {
      const response = await callHttp<{}>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts/latest`);
      return response.project!;
    },
    async showScript(sessionId: string, scriptId: string) {
      const response = await callHttp<{}>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts/${encodeURIComponent(scriptId)}`,
      );
      return response.project!;
    },
    async listScripts(sessionId: string) {
      const response = await callHttp<{}>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts`);
      return (response.scripts as ScriptRecord[]) ?? [];
    },
    async renderAudio(sessionId: string, options?: RenderAudioOptions) {
      const response = await callHttp<AudioRenderResult>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/audio:render`,
        {
          method: "POST",
          body: JSON.stringify({
            provider_override: options?.providerOverride ?? "",
            script_id: options?.scriptId ?? "",
          }),
        },
      );
      if (typeof response.run_token !== "string" && typeof response.request_state?.run_token === "string") {
        response.run_token = response.request_state.run_token;
      }
      return response;
    },
    async listVoicePresets() {
      const response = await callHttp<VoicePresetCatalog>("/api/v1/voice-studio/presets");
      return {
        voices: response.voices ?? [],
        styles: response.styles ?? [],
        standard_preview_text: response.standard_preview_text ?? "",
        request_state: response.request_state,
        runtime: response.runtime,
      };
    },
    async renderVoicePreview(settings: VoiceRenderSettings, options?: RenderVoicePreviewOptions) {
      const response = await callHttp<VoicePreviewResult & { task_id?: string }>("/api/v1/voice-studio/preview", {
        method: "POST",
        body: JSON.stringify(serializeVoiceSettings(settings)),
      });
      const initialState = asRequestState(response.request_state);
      if (initialState) options?.onState?.(initialState);
      if (response.audio_path) {
        return response;
      }
      const taskId = response.task_id ?? initialState?.task_id ?? "render_voice_preview";
      return waitForVoicePreview(this.showTaskState, taskId, options);
    },
    async renderVoiceTake(sessionId: string, scriptId: string, settings: VoiceRenderSettings, options?: RenderAudioOptions) {
      const response = await callHttp<VoiceTakeRenderResult>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts/${encodeURIComponent(scriptId)}/voice-takes:render`,
        {
          method: "POST",
          body: JSON.stringify({
            ...serializeVoiceSettings(settings),
            provider_override: options?.providerOverride ?? "",
          }),
        },
      );
      if (typeof response.run_token !== "string" && typeof response.request_state?.run_token === "string") {
        response.run_token = response.request_state.run_token;
      }
      return response;
    },
    async setFinalVoiceTake(sessionId: string, takeId: string) {
      const response = await callHttp<{}>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/voice-takes/${encodeURIComponent(takeId)}:final`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      return response.project!;
    },
    async saveEditedScript(sessionId: string, scriptId: string, finalText: string) {
      const response = await callHttp<{}>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts/${encodeURIComponent(scriptId)}/final`,
        {
          method: "PUT",
          body: JSON.stringify({ final_text: finalText }),
        },
      );
      return response.project!;
    },
    async deleteScript(sessionId: string, scriptId: string) {
      const response = await callHttp<{}>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts/${encodeURIComponent(scriptId)}:delete`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      return response.project!;
    },
    async restoreScript(sessionId: string, scriptId: string) {
      const response = await callHttp<{}>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts/${encodeURIComponent(scriptId)}:restore`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      return response.project!;
    },
    async listScriptRevisions(sessionId: string, scriptId: string) {
      const response = await callHttp<{}>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts/${encodeURIComponent(scriptId)}/revisions`,
      );
      return response.revisions ?? [];
    },
    async rollbackScriptRevision(sessionId: string, scriptId: string, revisionId: string) {
      const response = await callHttp<{}>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/scripts/${encodeURIComponent(scriptId)}/revisions/${encodeURIComponent(revisionId)}:rollback`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      return response.project!;
    },
    async getLocalTTSCapability() {
      const response = await callHttp<{}>("/api/v1/runtime/tts/local-capability");
      return response.tts_capability!;
    },
    async showLLMConfig() {
      const response = await callHttp<{}>("/api/v1/config/llm", { needsToken: true });
      return response.llm_config!;
    },
    async configureLLMProvider(input: ConfigureLLMInput) {
      const response = await callHttp<{}>("/api/v1/config/llm", {
        method: "PUT",
        needsToken: true,
        body: JSON.stringify({
          provider: input.provider,
          model: input.model,
          base_url: input.base_url,
          api_key: input.api_key,
        }),
      });
      return response.llm_config!;
    },
    async showTTSConfig() {
      const response = await callHttp<{}>("/api/v1/config/tts", { needsToken: true });
      return response.tts_config!;
    },
    async configureTTSProvider(input: ConfigureTTSInput) {
      const shouldClearLocalModelPath = input.local_model_path.trim() === "";
      const response = await callHttp<{}>("/api/v1/config/tts", {
        method: "PUT",
        needsToken: true,
        body: JSON.stringify({
          provider: input.provider,
          model: input.model,
          base_url: input.base_url,
          api_key: input.api_key,
          voice: input.voice,
          audio_format: input.audio_format,
          local_runtime: input.local_runtime,
          local_model_path: shouldClearLocalModelPath ? null : input.local_model_path,
          local_ref_audio_path: input.local_ref_audio_path,
          clear_local_model_path: shouldClearLocalModelPath,
        }),
      });
      return response.tts_config!;
    },
    async listModelsStatus() {
      const response = await callHttp<{}>("/api/v1/models");
      return response.models ?? [];
    },
    async showModelStorage() {
      const response = await callHttp<{}>("/api/v1/models/storage");
      if (!response.model_storage) throw new Error("Model storage response was missing storage details.");
      return response.model_storage;
    },
    async migrateModelStorage(destination: string) {
      const response = await callHttp<{}>("/api/v1/models/storage:migrate", {
        method: "POST",
        body: JSON.stringify({ destination }),
      });
      return {
        message: typeof response.message === "string" ? response.message : "Migrating model storage...",
        task_id: typeof response.task_id === "string" ? response.task_id : undefined,
        request_state: asRequestState(response.request_state) ?? undefined,
      };
    },
    async resetModelStorage() {
      const response = await callHttp<{}>("/api/v1/models/storage:reset", {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!response.model_storage) throw new Error("Model storage response was missing storage details.");
      return response.model_storage;
    },
    async downloadModel(modelName: string) {
      const response = await callHttp<{}>(`/api/v1/models/${encodeURIComponent(modelName)}:download`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      return {
        message: typeof response.message === "string" ? response.message : "ok",
        path: typeof response.path === "string" ? response.path : undefined,
        task_id: typeof response.task_id === "string" ? response.task_id : undefined,
        request_state: asRequestState(response.request_state) ?? undefined,
      };
    },
    async deleteModel(modelName: string) {
      const response = await callHttp<{}>(`/api/v1/models/${encodeURIComponent(modelName)}:delete`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      return {
        message: typeof response.message === "string" ? response.message : "ok",
        path: typeof response.path === "string" ? response.path : undefined,
      };
    },
    async showTaskState(taskId: string) {
      const response = await callHttp<{}>(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
      return asRequestState(response.task_state);
    },
    async cancelTask(taskId: string) {
      const response = await callHttp<{}>(`/api/v1/tasks/${encodeURIComponent(taskId)}:cancel`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      return asRequestState(response.task_state) ?? asRequestState(response.request_state);
    },
  };
}
