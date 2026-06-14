import { describe, expect, it } from "vitest";
import { deriveStudioState } from "./deriveStudioState";
import type { SessionProject, StudioProgressState } from "../types";
import type { ScriptCheckResult } from "../pages/script-workbench/spokenScriptTypes";

const emptyCheck: ScriptCheckResult = {
  issues: [],
  blockingCount: 0,
  warningCount: 0,
  infoCount: 0,
  statusLabel: "ok",
  blockingSummary: null,
  canRender: false, // empty script cannot render
  hasCleanableIssues: false,
};

const cleanCheck: ScriptCheckResult = {
  ...emptyCheck,
  canRender: true,
  statusLabel: "ready",
};

const blockedCheck: ScriptCheckResult = {
  ...emptyCheck,
  canRender: false,
  blockingCount: 1,
  blockingSummary: "Contains stage directions",
  statusLabel: "blocked",
};

function makeProject(overrides: Partial<SessionProject> = {}): SessionProject {
  return {
    session: {
      session_id: "s1",
      topic: "Test Episode",
      creation_intent: "",
      state: "topic_defined",
      llm_provider: "openai",
      tts_provider: "cloud",
      last_error: "",
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    },
    transcript: { session_id: "s1", turns: [] },
    script: null,
    artifact: null,
    ...overrides,
  };
}

function derive(
  project: SessionProject | null,
  opts: {
    scriptText?: string;
    check?: ScriptCheckResult;
    isDirty?: boolean;
    scriptId?: string;
  } = {},
): StudioProgressState {
  return deriveStudioState(
    project,
    opts.scriptText ?? "",
    opts.check ?? emptyCheck,
    opts.isDirty ?? false,
    opts.scriptId,
  );
}

describe("deriveStudioState", () => {
  it("returns needs_brief when project is null", () => {
    expect(derive(null)).toBe("needs_brief");
  });

  it("returns needs_brief for topic_defined with empty transcript", () => {
    const p = makeProject();
    expect(derive(p)).toBe("needs_brief");
  });

  it("returns needs_brief for topic_defined even with turns if state hasn't advanced", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "topic_defined" },
      transcript: { session_id: "s1", turns: [{ speaker: "user", content: "hi", created_at: "" }] },
    });
    expect(derive(p)).toBe("needs_brief");
  });

  it("returns needs_interview for interview_in_progress", () => {
    const p = makeProject({ session: { ...makeProject().session, state: "interview_in_progress" } });
    expect(derive(p)).toBe("needs_interview");
  });

  it("returns needs_interview for readiness_evaluation", () => {
    const p = makeProject({ session: { ...makeProject().session, state: "readiness_evaluation" } });
    expect(derive(p)).toBe("needs_interview");
  });

  it("returns ready_to_generate_script when state is ready_to_generate", () => {
    const p = makeProject({ session: { ...makeProject().session, state: "ready_to_generate" } });
    expect(derive(p)).toBe("ready_to_generate_script");
  });

  it("returns script_ready_needs_review when script_generated with no edits", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "script_generated" },
      script: {
        session_id: "s1",
        script_id: "sc1",
        name: "Draft",
        draft: "Hello world",
        final: "Hello world",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
    });
    expect(derive(p, { check: cleanCheck, isDirty: false })).toBe("script_ready_needs_review");
  });

  it("returns script_blocked_for_tts when script exists but canRender is false", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "script_edited" },
      script: {
        session_id: "s1",
        script_id: "sc1",
        name: "Draft",
        draft: "  Host: hello",
        final: "  Host: hello",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
    });
    expect(derive(p, { check: blockedCheck, isDirty: false })).toBe("script_blocked_for_tts");
  });

  it("returns needs_voice when script is clean but no voice selected", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "script_edited" },
      script: {
        session_id: "s1",
        script_id: "sc1",
        name: "Draft",
        draft: "Hello world",
        final: "Hello world",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
      artifact: null,
    });
    expect(derive(p, { check: cleanCheck, isDirty: false })).toBe("needs_voice");
  });

  it("returns ready_to_generate_audio when script is clean and voice is selected", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "script_edited" },
      script: {
        session_id: "s1",
        script_id: "sc1",
        name: "Draft",
        draft: "Hello world",
        final: "Hello world",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-02T00:00:00Z",
      },
      artifact: {
        session_id: "s1",
        transcript_path: "",
        audio_path: "",
        provider: "cloud",
        created_at: "2024-01-01T00:00:00Z",
        voice_reference: {
          lock_id: "lk1",
          audio_path: "/voice.wav",
          preview_text: "hello",
          provider: "cloud",
          model: "m1",
          voice_id: "v1",
          style_id: "s1",
          speed: 1,
          language: "en",
          audio_format: "mp3",
          created_at: "2024-01-01T00:00:00Z",
        },
      },
    });
    expect(derive(p, { check: cleanCheck, isDirty: false })).toBe("ready_to_generate_audio");
  });

  it("returns audio_ready when audio exists and script not changed", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "completed" },
      script: {
        session_id: "s1",
        script_id: "sc1",
        name: "Draft",
        draft: "Hello world",
        final: "Hello world",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
      artifact: {
        session_id: "s1",
        transcript_path: "/t.json",
        audio_path: "/audio.mp3",
        provider: "cloud",
        created_at: "2024-01-02T00:00:00Z",
        voice_reference: {
          lock_id: "lk1",
          audio_path: "/voice.wav",
          preview_text: "hello",
          provider: "cloud",
          model: "m1",
          voice_id: "v1",
          style_id: "s1",
          speed: 1,
          language: "en",
          audio_format: "mp3",
          created_at: "2024-01-01T00:00:00Z",
        },
      },
    });
    expect(derive(p, { check: cleanCheck, isDirty: false })).toBe("audio_ready");
  });

  it("returns script_changed_after_audio when isDirty and audio exists", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "completed" },
      script: {
        session_id: "s1",
        script_id: "sc1",
        name: "Draft",
        draft: "Hello world",
        final: "Hello world",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      },
      artifact: {
        session_id: "s1",
        transcript_path: "/t.json",
        audio_path: "/audio.mp3",
        provider: "cloud",
        created_at: "2024-01-02T00:00:00Z",
      },
    });
    expect(derive(p, { check: cleanCheck, isDirty: true })).toBe("script_changed_after_audio");
  });

  it("returns script_changed_after_audio when script updated_at is after artifact created_at", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "completed" },
      script: {
        session_id: "s1",
        script_id: "sc1",
        name: "Draft",
        draft: "Updated text",
        final: "Updated text",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-05T00:00:00Z", // newer than artifact
      },
      artifact: {
        session_id: "s1",
        transcript_path: "/t.json",
        audio_path: "/audio.mp3",
        provider: "cloud",
        created_at: "2024-01-03T00:00:00Z",
      },
    });
    expect(derive(p, { check: cleanCheck, isDirty: false })).toBe("script_changed_after_audio");
  });

  it("returns script_ready_needs_review when no script exists", () => {
    const p = makeProject({
      session: { ...makeProject().session, state: "script_generated" },
      script: null,
    });
    expect(derive(p, { check: emptyCheck })).toBe("script_ready_needs_review");
  });
});
