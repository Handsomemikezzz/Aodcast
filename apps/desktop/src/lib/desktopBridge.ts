import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  ModelStatus,
  SessionProject,
  TTSProviderConfig,
  TTSCapability,
} from "../types";

export type CreateSessionInput = {
  topic: string;
  creationIntent: string;
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
};

export interface DesktopBridge {
  listProjects(): Promise<SessionProject[]>;
  createSession(input: CreateSessionInput): Promise<SessionProject>;
  startInterview(sessionId: string): Promise<InterviewTurnResult>;
  submitReply(sessionId: string, message: string, userRequestedFinish?: boolean): Promise<InterviewTurnResult>;
  requestFinish(sessionId: string): Promise<InterviewTurnResult>;
  generateScript(sessionId: string): Promise<GenerationResult>;
  renderAudio(sessionId: string): Promise<AudioRenderResult>;
  saveEditedScript(sessionId: string, finalText: string): Promise<SessionProject>;
  getLocalTTSCapability(): Promise<TTSCapability>;
  showTTSConfig(): Promise<TTSProviderConfig>;
  configureTTSProvider(input: ConfigureTTSInput): Promise<TTSProviderConfig>;
  listModelsStatus(): Promise<ModelStatus[]>;
  downloadModel(modelName: string): Promise<{ message: string; path?: string }>;
  deleteModel(modelName: string): Promise<{ message: string; path?: string }>;
}
