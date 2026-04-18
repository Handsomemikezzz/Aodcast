import { invoke } from "@tauri-apps/api/core";

import type {
  ConfigureLLMInput,
  ConfigureTTSInput,
  CreateSessionInput,
  DesktopBridge,
  DesktopBridgeError,
  ListProjectsOptions,
  ShowSessionOptions,
} from "./desktopBridge";
import { asRequestState } from "./requestState";
import type {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  LLMProviderConfig,
  ModelStatus,
  RequestState,
  ScriptRecord,
  ScriptRevisionRecord,
  SessionProject,
  TTSCapability,
  TTSProviderConfig,
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
  request_state?: RequestState;
  task_state?: RequestState | null;
  task_id?: string;
  message?: string;
  path?: string;
} & T;

type RuntimeContext = {
  base_url: string;
};

function runtimeContext(baseUrl: string): RuntimeContext {
  const context: RuntimeContext = { base_url: baseUrl };
  return context;
}

export class HttpBridgeInvocationError extends Error {
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
      return new HttpBridgeInvocationError(candidate.message, {
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

function buildUrl(baseUrl: string, path: string, query?: Record<string, string | boolean | undefined>): string {
  const url = new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  for (const [key, value] of Object.entries(query || {})) {
    if (value === undefined || value === "") continue;
    url.searchParams.set(key, String(value));
  }
  return url.toString();
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
        return runtimeContext(fallbackBaseUrl);
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
    return runtimeTokenPromise;
  }

  async function callHttp<T>(
    path: string,
    init?: RequestInit & { query?: Record<string, string | boolean | undefined>; needsToken?: boolean },
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

    const flushEvent = (chunk: string) => {
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
      if (dataLines.length === 0) return;
      const parsed = JSON.parse(dataLines.join("\n")) as BridgeEnvelope<InterviewTurnResult> | { ok: true; type: "chunk"; delta: string };
      if ("type" in parsed && parsed.type === "chunk") {
        onChunk(parsed.delta);
        return;
      }
      if (eventName === "final") {
        finalPayload = parsed as BridgeEnvelope<InterviewTurnResult>;
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let separatorIndex = buffer.indexOf("\n\n");
        while (separatorIndex >= 0) {
          const eventChunk = buffer.slice(0, separatorIndex);
          buffer = buffer.slice(separatorIndex + 2);
          flushEvent(eventChunk);
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
    async renderAudio(sessionId: string) {
      return callHttp<AudioRenderResult>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/audio:render`, {
        method: "POST",
        body: JSON.stringify({}),
      });
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
          clear_local_model_path: shouldClearLocalModelPath,
        }),
      });
      return response.tts_config!;
    },
    async listModelsStatus() {
      const response = await callHttp<{}>("/api/v1/models");
      return response.models ?? [];
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
