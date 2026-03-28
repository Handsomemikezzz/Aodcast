import { invoke } from "@tauri-apps/api/core";

import { CreateSessionInput, DesktopBridge, DesktopBridgeError } from "./desktopBridge";
import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  SessionProject,
  TTSCapability,
} from "../types";

type BridgeShape<T> = {
  project?: SessionProject;
  projects?: SessionProject[];
  tts_capability?: TTSCapability;
} & T;

function normalizeError(error: unknown): Error {
  if (typeof error === "object" && error !== null) {
    const candidate = error as Partial<DesktopBridgeError>;
    if (typeof candidate.message === "string") {
      const wrapped = new Error(candidate.message);
      wrapped.name = candidate.code || "desktop_bridge_error";
      return wrapped;
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
        creationIntent: input.creationIntent,
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
    async getLocalTTSCapability() {
      const response = await callBridge<{}>("show_local_tts_capability");
      return response.tts_capability!;
    },
  };
}
