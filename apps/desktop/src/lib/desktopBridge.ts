import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  SessionProject,
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
}
