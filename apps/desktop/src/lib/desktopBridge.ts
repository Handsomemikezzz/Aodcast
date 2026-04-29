import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  LLMProviderConfig,
  ModelStorageStatus,
  ModelStatus,
  RequestState,
  ScriptRecord,
  ScriptRevisionRecord,
  SessionProject,
  TTSProviderConfig,
  TTSCapability,
  VoicePresetCatalog,
  VoicePreviewResult,
  VoiceRenderSettings,
  VoiceTakeRenderResult,
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
  voiceSettings?: VoiceRenderSettings;
};

export type DeleteGeneratedAudioOptions = {
  scriptId?: string;
};

export type RenderVoicePreviewOptions = {
  onState?: (state: RequestState) => void;
  sessionId?: string;
  scriptId?: string;
  providerOverride?: string;
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
  /** Create a new interview session from the landing topic and creation intent. */
  createSession(input: CreateSessionInput): Promise<SessionProject>;
  /** Load a full session project, optionally including soft-deleted data. */
  showSession(sessionId: string, options?: ShowSessionOptions): Promise<SessionProject>;
  /** Rename a session topic without changing its transcript or script snapshots. */
  renameSession(sessionId: string, topic: string): Promise<SessionProject>;
  /** Soft-delete the session and its active workspace until it is restored. */
  deleteSession(sessionId: string): Promise<SessionProject>;
  /** Restore a previously soft-deleted session. */
  restoreSession(sessionId: string): Promise<SessionProject>;
  /** Start the guided interview for a session and return the next prompt plus readiness metadata. */
  startInterview(sessionId: string): Promise<InterviewTurnResult>;
  /** Stream the assistant reply token-by-token while preserving the final bridge envelope. */
  submitReplyStream(
    sessionId: string,
    message: string,
    onChunk: (delta: string) => void,
    userRequestedFinish?: boolean,
    signal?: AbortSignal,
  ): Promise<InterviewTurnResult>;
  /** Ask the orchestrator to finish the interview and move into readiness evaluation. */
  requestFinish(sessionId: string): Promise<InterviewTurnResult>;
  /** Generate the current script draft from the interview transcript. */
  generateScript(sessionId: string): Promise<GenerationResult>;
  /** Render audio once, optionally overriding the configured TTS provider or targeting a specific script snapshot. */
  renderAudio(sessionId: string, options?: RenderAudioOptions): Promise<AudioRenderResult>;
  /** Delete the generated audio artifact for a session, optionally scoped to a script snapshot. */
  deleteGeneratedAudio(sessionId: string, options?: DeleteGeneratedAudioOptions): Promise<SessionProject>;
  /** Delete a standalone preview/export audio file by artifact path. */
  deleteArtifactAudio(path: string): Promise<{ path?: string; deleted?: boolean; message?: string }>;
  /** List packaged voice and style presets for the Voice Studio MVP. */
  listVoicePresets(): Promise<VoicePresetCatalog>;
  /** Render a short preview for quick voice/style/text comparison. */
  renderVoicePreview(settings: VoiceRenderSettings, options?: RenderVoicePreviewOptions): Promise<VoicePreviewResult>;
  /** Render a candidate take for one script snapshot. */
  renderVoiceTake(sessionId: string, scriptId: string, settings: VoiceRenderSettings, options?: RenderAudioOptions): Promise<VoiceTakeRenderResult>;
  /** Mark a generated take as the final script audio. */
  setFinalVoiceTake(sessionId: string, takeId: string): Promise<SessionProject>;
  /** Delete a generated Voice Studio take and clear final audio if it was selected. */
  deleteVoiceTake(sessionId: string, takeId: string): Promise<SessionProject>;
  /** Resolve the most recent script snapshot for a session-level navigation entry point. */
  showLatestScript(sessionId: string): Promise<SessionProject>;
  /** Load a specific script snapshot workspace. */
  showScript(sessionId: string, scriptId: string): Promise<SessionProject>;
  /** List every script snapshot that belongs to the session. */
  listScripts(sessionId: string): Promise<ScriptRecord[]>;
  /** Persist a script snapshot's final text. */
  saveEditedScript(sessionId: string, scriptId: string, finalText: string): Promise<SessionProject>;
  /** Soft-delete one script snapshot without deleting the session. */
  deleteScript(sessionId: string, scriptId: string): Promise<SessionProject>;
  /** Restore one soft-deleted script snapshot. */
  restoreScript(sessionId: string, scriptId: string): Promise<SessionProject>;
  /** List the revision history for one script snapshot. */
  listScriptRevisions(sessionId: string, scriptId: string): Promise<ScriptRevisionRecord[]>;
  /** Replace the current script contents with a saved revision. */
  rollbackScriptRevision(sessionId: string, scriptId: string, revisionId: string): Promise<SessionProject>;
  /** Report whether local MLX TTS is available on this machine and why/why not. */
  getLocalTTSCapability(): Promise<TTSCapability>;
  showLLMConfig(): Promise<LLMProviderConfig>;
  configureLLMProvider(input: ConfigureLLMInput): Promise<LLMProviderConfig>;
  showTTSConfig(): Promise<TTSProviderConfig>;
  configureTTSProvider(input: ConfigureTTSInput): Promise<TTSProviderConfig>;
  listModelsStatus(): Promise<ModelStatus[]>;
  showModelStorage(): Promise<ModelStorageStatus>;
  migrateModelStorage(destination: string): Promise<{ message: string; task_id?: string; request_state?: RequestState }>;
  resetModelStorage(): Promise<ModelStorageStatus>;
  /** Start a long-running voice model download and return its task metadata. */
  downloadModel(modelName: string): Promise<{ message: string; path?: string; task_id?: string; request_state?: RequestState }>;
  deleteModel(modelName: string): Promise<{ message: string; path?: string }>;
  /** Poll the latest persisted request state for a long-running task. */
  showTaskState(taskId: string): Promise<RequestState | null>;
  /** Request cooperative cancellation for a long-running task. */
  cancelTask(taskId: string): Promise<RequestState | null>;
}
