import { describe, expect, it } from "vitest";
import {
  deriveEpisodeProductStatus,
  formatEpisodeDuration,
  formatRelativeEpisodeTime,
  isProjectAudioOutOfDate,
} from "./episodeStatus";
import type { SessionProject } from "../types";

function makeProject(overrides: Partial<SessionProject> = {}): SessionProject {
  return {
    session: {
      session_id: "session-1",
      topic: "Test episode",
      creation_intent: "",
      creation_mode: "interview",
      state: "script_generated",
      llm_provider: "mock",
      tts_provider: "mock",
      last_error: "",
      created_at: "2026-08-20T10:00:00Z",
      updated_at: "2026-08-20T10:00:00Z",
    },
    source: null,
    transcript: null,
    script: {
      session_id: "session-1",
      script_id: "script-1",
      name: "Draft",
      draft: "Hello",
      final: "Hello",
      created_at: "2026-08-20T10:00:00Z",
      updated_at: "2026-08-20T10:00:00Z",
    },
    artifact: null,
    speech_plan: null,
    render_manifest: null,
    ...overrides,
  };
}

describe("episode product status", () => {
  it("uses Draft before a script exists", () => {
    const project = makeProject({
      session: { ...makeProject().session, state: "interview_in_progress" },
      script: null,
    });
    expect(deriveEpisodeProductStatus({ project }).kind).toBe("draft");
  });

  it("uses Ready to generate for a script without audio", () => {
    expect(deriveEpisodeProductStatus({ project: makeProject() }).kind).toBe("ready_to_generate");
  });

  it("derives product status from lightweight list summaries without exposing the raw state", () => {
    const summary = makeProject({
      session: { ...makeProject().session, state: "completed" },
      script: null,
      artifact: null,
      render_manifest: null,
    });
    expect(deriveEpisodeProductStatus({ project: summary })).toEqual({
      kind: "audio_ready",
      label: "Audio ready",
    });
  });

  it("keeps old audio and marks it as needing an update after an edit", () => {
    const project = makeProject({
      session: { ...makeProject().session, state: "script_edited" },
      artifact: {
        session_id: "session-1",
        transcript_path: "",
        audio_path: "/podcast.wav",
        provider: "mock",
        created_at: "2026-08-20T10:00:00Z",
      },
    });
    expect(isProjectAudioOutOfDate(project, "script-1")).toBe(true);
    expect(deriveEpisodeProductStatus({ project, scriptId: "script-1" }).kind).toBe("audio_needs_update");
  });

  it("formats final audio duration and relative update time", () => {
    const project = makeProject({
      render_manifest: {
        schema_version: 1,
        render_id: "render-1",
        session_id: "session-1",
        script_id: "script-1",
        script_hash: "hash",
        speech_plan: { plan_id: "plan-1", version: 1, plan_hash: "plan-hash" },
        speaker_reference: null,
        pipeline: [],
        pipeline_hash: "pipeline-hash",
        parent_render_id: null,
        regeneration: null,
        segments: [],
        assembly: {
          audio_format: "wav",
          sample_rate_hz: 48_000,
          channels: 1,
          sample_width_bits: 16,
          target_rms_dbfs: -18,
          peak_ceiling_dbfs: -1,
          edge_fade_ms: 8,
        },
        output: {
          audio_path: "/podcast.wav",
          audio_hash: "audio-hash",
          transcript_path: "/podcast.txt",
          duration_ms: 751_000,
        },
        created_at: "2026-08-20T10:00:00Z",
      },
    });
    expect(formatEpisodeDuration(project)).toBe("12:31");
    expect(formatRelativeEpisodeTime("2026-08-21T10:00:00Z", Date.parse("2026-08-22T10:00:00Z"))).toBe("Yesterday");
  });
});
