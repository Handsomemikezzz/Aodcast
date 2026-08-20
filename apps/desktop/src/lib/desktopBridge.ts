import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  LLMConfigPreflight,
  LLMProviderConfig,
  MemoryEntry,
  MemoryOverview,
  MemoryUsageEvent,
  ModelStorageStatus,
  ModelStatus,
  RequestState,
  ScriptRecord,
  ScriptRevisionRecord,
  SessionProject,
  SpeakerReference,
  TTSProviderConfig,
  TTSCapability,
  VoicePresetCatalog,
  VoicePreviewResult,
  VoiceRenderSettings,
} from "../types";

export type MemorySettingsInput = {
  writingEnabled?: boolean;
  usageEnabled?: boolean;
};

export type ListMemoriesOptions = {
  search?: string;
  type?: string;
};

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
  source?: EpisodeSourceInput;
};

export type EpisodeSourceInput = {
  rawMarkdown: string;
  name: string;
  importKind: "file" | "paste";
  conversionMode: "adapt" | "narrate";
  targetLength: "auto" | "short" | "standard" | "long";
  focusInstructions: string;
};

export type RenderAudioOptions = {
  providerOverride?: string;
  scriptId?: string;
  modelId?: string;
  voiceSettings?: VoiceRenderSettings;
  requireSpeakerReference?: boolean;
};

export type RegenerateAudioWindowInput = {
  speechPlanId: string;
  renderManifestId: string;
};

export type LongTaskHandle = {
  taskId: string;
  runToken: string;
};

export type DeleteGeneratedAudioOptions = {
  scriptId?: string;
};

export type RenderVoicePreviewOptions = {
  onState?: (state: RequestState) => void;
  onTaskStarted?: (handle: LongTaskHandle) => void;
  sessionId?: string;
  scriptId?: string;
  providerOverride?: string;
  modelId?: string;
  speakerReferenceId?: string;
};

export type CreateSpeakerReferenceInput = {
  name: string;
  referenceText: string;
  language: string;
  audioFile: Blob;
  audioFileName: string;
};

export type UpdateSpeakerReferenceInput = {
  name?: string;
  referenceText?: string;
  language?: string;
  audioFile?: Blob;
  audioFileName?: string;
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
  /** Replace the imported Markdown snapshot and increment its source version. */
  updateEpisodeSource(sessionId: string, input: EpisodeSourceInput): Promise<SessionProject>;
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
  /** Regenerate the target speech segment together with its immediate context window. */
  regenerateAudioWindow(
    sessionId: string,
    scriptId: string,
    targetSegmentId: string,
    input: RegenerateAudioWindowInput,
  ): Promise<AudioRenderResult>;
  /** Delete the generated audio artifact for a session, optionally scoped to a script snapshot. */
  deleteGeneratedAudio(sessionId: string, options?: DeleteGeneratedAudioOptions): Promise<SessionProject>;
  /** Delete a standalone preview/export audio file by artifact path. */
  deleteArtifactAudio(path: string): Promise<{ path?: string; deleted?: boolean; message?: string }>;
  /** Export intermediate WAV to MP3/M4A/WAV with custom settings. */
  exportPodcastAudio(audioPath: string, format: string, bitrate: string, filename: string): Promise<{ audio_url: string; file_name: string; audio_path: string }>;
  /** List packaged voice and style presets for the Voice Studio MVP. */
  listVoicePresets(): Promise<VoicePresetCatalog>;
  /** Render a short preview for quick voice/style/text comparison. */
  renderVoicePreview(settings: VoiceRenderSettings, options?: RenderVoicePreviewOptions): Promise<VoicePreviewResult>;
  /** List built-in and user-saved provider-neutral speaker references. */
  listSpeakerReferences(): Promise<SpeakerReference[]>;
  /** Create one reusable speaker reference with its audio sample in a single upload. */
  createSpeakerReference(input: CreateSpeakerReferenceInput): Promise<SpeakerReference>;
  /** Update a user-saved speaker reference and optionally replace its sample. */
  updateSpeakerReference(referenceId: string, input: UpdateSpeakerReferenceInput): Promise<SpeakerReference>;
  /** Delete a user-saved speaker reference. */
  deleteSpeakerReference(referenceId: string): Promise<{ speaker_reference_id?: string; deleted?: boolean }>;
  /** Select a reusable speaker reference for the current script. */
  selectSpeakerReference(sessionId: string, scriptId: string, referenceId: string): Promise<SessionProject>;
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
  checkLLMConfig(): Promise<LLMConfigPreflight>;
  configureLLMProvider(input: ConfigureLLMInput): Promise<LLMProviderConfig>;
  showTTSConfig(): Promise<TTSProviderConfig>;
  configureTTSProvider(input: ConfigureTTSInput): Promise<TTSProviderConfig>;
  testLLMConnection(input: ConfigureLLMInput): Promise<{ status: string; latency_ms: number; message: string }>;
  testTTSConnection(input: ConfigureTTSInput): Promise<{ status: string; latency_ms: number; message: string }>;
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
  cancelTask(taskId: string, runToken: string): Promise<RequestState | null>;
  /** Read long-term memory settings plus background worker status. */
  getMemoryOverview(): Promise<MemoryOverview>;
  /** Toggle global memory writing and/or usage. */
  updateMemorySettings(input: MemorySettingsInput): Promise<MemoryOverview>;
  /** Complete the first-run notice and enable memory writing + usage. */
  acknowledgeMemory(): Promise<MemoryOverview>;
  /** List long-term memory entries, optionally filtered by search text or type. */
  listMemories(options?: ListMemoriesOptions): Promise<MemoryEntry[]>;
  /** Load one memory entry with body and evidence. */
  getMemory(memoryId: string): Promise<MemoryEntry>;
  /** Delete one memory entry and write an irreversible forget fingerprint. */
  deleteMemory(memoryId: string): Promise<{ memory_id: string; deleted: boolean }>;
  /** Clear all long-term memory and reset memory state. */
  clearAllMemory(): Promise<MemoryOverview>;
  /** List recent memory usage events across episodes. */
  listMemoryUsage(): Promise<MemoryUsageEvent[]>;
  /** Enable or disable memory for one episode (gates both reading and writing). */
  setSessionMemoryMode(sessionId: string, mode: "enabled" | "disabled"): Promise<SessionProject>;
  /** List relevant experience/sensitive memories that need this episode's authorization before script use. */
  listMemoryCandidates(sessionId: string): Promise<MemoryEntry[]>;
  /** Authorize one memory for use in the current episode's script. */
  authorizeMemory(sessionId: string, memoryId: string): Promise<SessionProject>;
  /** Schedule a background memory maintenance (merge/dedup/evict) batch. */
  runMemoryMaintenance(): Promise<MemoryOverview>;
  /** List recently superseded memories (read-only history). */
  listMemorySuperseded(): Promise<MemoryEntry[]>;
  /** §10.4: Find active memories matching a free-text query for forget disambiguation. */
  findForgetCandidates(query: string): Promise<MemoryEntry[]>;
  /** §10.3: Move a specific memory to superseded/ (user-confirmed correction target). */
  supersedeMemory(memoryId: string): Promise<{ memory_id: string; superseded: boolean }>;
}
