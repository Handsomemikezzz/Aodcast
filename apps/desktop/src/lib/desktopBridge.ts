import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  LLMProviderConfig,
  ModelStatus,
  RequestState,
  ScriptRecord,
  ScriptRevisionRecord,
  SessionProject,
  TTSProviderConfig,
  TTSCapability,
} from "../types";

export type ListProjectsOptions = {
  search?: string;
  includeDeleted?: boolean;
};

export type ShowSessionOptions = {
  includeDeleted?: boolean;
};

export type CreateSessionInput = {
  topic: string;
  creationIntent: string;
};

export type RenderAudioOptions = {
  providerOverride?: string;
  scriptId?: string;
};

export type DesktopBridgeError = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};

export type ConfigureTTSInput = {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  voice: string;
  audio_format: string;
  local_runtime: string;
  local_model_path: string;
  local_ref_audio_path: string;
};

export type ConfigureLLMInput = {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
};

export interface DesktopBridge {
  /** List lightweight session summaries for the shell and history views. */
  listProjects(options?: ListProjectsOptions): Promise<SessionProject[]>;
  createSession(input: CreateSessionInput): Promise<SessionProject>;
  /** Load a full session project, optionally including soft-deleted data. */
  showSession(sessionId: string, options?: ShowSessionOptions): Promise<SessionProject>;
  renameSession(sessionId: string, topic: string): Promise<SessionProject>;
  deleteSession(sessionId: string): Promise<SessionProject>;
  restoreSession(sessionId: string): Promise<SessionProject>;
  startInterview(sessionId: string): Promise<InterviewTurnResult>;
  submitReply(sessionId: string, message: string, userRequestedFinish?: boolean): Promise<InterviewTurnResult>;
  submitReplyStream(
    sessionId: string,
    message: string,
    onChunk: (delta: string) => void,
    userRequestedFinish?: boolean,
    signal?: AbortSignal,
  ): Promise<InterviewTurnResult>;
  requestFinish(sessionId: string): Promise<InterviewTurnResult>;
  generateScript(sessionId: string): Promise<GenerationResult>;
  /** Render audio once, optionally overriding the configured TTS provider or targeting a specific script snapshot. */
  renderAudio(sessionId: string, options?: RenderAudioOptions): Promise<AudioRenderResult>;
  showLatestScript(sessionId: string): Promise<SessionProject>;
  showScript(sessionId: string, scriptId: string): Promise<SessionProject>;
  listScripts(sessionId: string): Promise<ScriptRecord[]>;
  /** Persist a script snapshot's final text. */
  saveEditedScript(sessionId: string, scriptId: string, finalText: string): Promise<SessionProject>;
  deleteScript(sessionId: string, scriptId: string): Promise<SessionProject>;
  restoreScript(sessionId: string, scriptId: string): Promise<SessionProject>;
  listScriptRevisions(sessionId: string, scriptId: string): Promise<ScriptRevisionRecord[]>;
  rollbackScriptRevision(sessionId: string, scriptId: string, revisionId: string): Promise<SessionProject>;
  getLocalTTSCapability(): Promise<TTSCapability>;
  showLLMConfig(): Promise<LLMProviderConfig>;
  configureLLMProvider(input: ConfigureLLMInput): Promise<LLMProviderConfig>;
  showTTSConfig(): Promise<TTSProviderConfig>;
  configureTTSProvider(input: ConfigureTTSInput): Promise<TTSProviderConfig>;
  listModelsStatus(): Promise<ModelStatus[]>;
  downloadModel(modelName: string): Promise<{ message: string; path?: string; task_id?: string; request_state?: RequestState }>;
  deleteModel(modelName: string): Promise<{ message: string; path?: string }>;
  showTaskState(taskId: string): Promise<RequestState | null>;
  cancelTask(taskId: string): Promise<RequestState | null>;
}
