import { describe, expect, it } from "vitest";
import type { SessionProject } from "../../types";
import {
  buildPreviewExcerpt,
  buildVoiceFreshnessKey,
  deriveAudioFreshness,
  deriveEpisodeRenderReadiness,
  resolveGlobalCtaKind,
  savedVoiceFreshnessKey,
} from "./studioWorkflow";

describe("studio workflow helpers", () => {
  it("compares existing audio against the voice settings saved with its script", () => {
    const saved = {
      voice_id: "casual_chat",
      voice_name: "轻松聊天",
      style_id: "natural",
      style_name: "Natural",
      speed: 1,
      language: "zh",
      audio_format: "wav",
    };
    const project = {
      artifact: { script_artifacts: { "script-1": { voice_settings: saved } } },
    } as unknown as SessionProject;

    const sameSelection = buildVoiceFreshnessKey(project, "script-1", { ...saved });
    expect(savedVoiceFreshnessKey(project, "script-1", "transient-default")).toBe(sameSelection);
    expect(savedVoiceFreshnessKey(project, "script-1", "transient-default")).not.toBe(
      buildVoiceFreshnessKey(project, "script-1", { ...saved, voice_id: "warm_narrator" }),
    );
  });

  it("ignores display-name changes when comparing voice settings", () => {
    const settings = { voice_id: "casual_chat", voice_name: "轻松聊天", style_id: "natural", style_name: "自然讲述", speed: 1, language: "zh", audio_format: "wav" };
    expect(buildVoiceFreshnessKey(null, undefined, settings)).toBe(
      buildVoiceFreshnessKey(null, undefined, { ...settings, voice_name: "Casual chat", style_name: "Natural" }),
    );
  });

  it("falls back to the current voice key when nothing was saved", () => {
    expect(savedVoiceFreshnessKey({ artifact: {} } as unknown as SessionProject, "script-1", "current")).toBe("current");
  });

  it("marks audio out of date when the current script has unsaved edits", () => {
    expect(
      deriveAudioFreshness({
        hasAudio: true,
        generating: false,
        isDirty: true,
        serverScript: "saved script",
        currentScript: "edited script",
        previousServerScript: "saved script",
        voiceKey: "voice-a",
        previousVoiceKey: "voice-a",
      }),
    ).toEqual({
      outOfDate: true,
      reason: "Script was edited after audio was generated.",
    });
  });

  it("marks audio out of date when saved script changes after audio exists", () => {
    expect(
      deriveAudioFreshness({
        hasAudio: true,
        generating: false,
        isDirty: false,
        serverScript: "new saved script",
        currentScript: "new saved script",
        previousServerScript: "old saved script",
        voiceKey: "voice-a",
        previousVoiceKey: "voice-a",
      }),
    ).toEqual({
      outOfDate: true,
      reason: "Script was edited after audio was generated.",
    });
  });

  it("marks audio out of date when voice settings change after audio exists", () => {
    expect(
      deriveAudioFreshness({
        hasAudio: true,
        generating: false,
        isDirty: false,
        serverScript: "script",
        currentScript: "script",
        previousServerScript: "script",
        voiceKey: "voice-b",
        previousVoiceKey: "voice-a",
      }),
    ).toEqual({
      outOfDate: true,
      reason: "Voice or model changed.",
    });
  });

  it("does not mark audio stale while a replacement render is generating", () => {
    expect(
      deriveAudioFreshness({
        hasAudio: true,
        generating: true,
        isDirty: true,
        serverScript: "saved script",
        currentScript: "edited script",
        previousServerScript: "saved script",
        voiceKey: "voice-b",
        previousVoiceKey: "voice-a",
      }),
    ).toEqual({ outOfDate: false });
  });

  it("uses ready as the global CTA when current audio exists", () => {
    expect(
      resolveGlobalCtaKind({
        generating: false,
        hasScript: true,
        hasAudio: true,
        audioOutOfDate: false,
        audioError: false,
      }),
    ).toBe("ready");
  });

  it("uses update-audio as the global CTA for stale audio", () => {
    expect(
      resolveGlobalCtaKind({
        generating: false,
        hasScript: true,
        hasAudio: true,
        audioOutOfDate: true,
        audioError: false,
      }),
    ).toBe("update-audio");
  });

  it("previews selected text before falling back to the current paragraph", () => {
    const script = "Opening paragraph.\n\nThis is the paragraph under the cursor.\n\nClosing.";
    expect(buildPreviewExcerpt(script, 20, 24)).toMatchObject({
      text: "This",
      source: "selection",
      label: "Selected text",
    });
    expect(buildPreviewExcerpt(script, 28, 28)).toMatchObject({
      text: "This is the paragraph under the cursor.",
      source: "paragraph",
      label: "Current paragraph",
    });
  });
});


describe("HTTP speech readiness", () => {
  it("uses the service preset without requiring a speaker reference", () => {
    expect(deriveEpisodeRenderReadiness({
      scriptReady: true,
      hasSelectedVoice: false,
      selectedEngine: "local_http",
      localVoiceMode: "preset",
      selectedModelId: "qwen-customvoice",
      capability: { provider: "local_http", runtime: "http", available: true, reasons: [], current_model: "qwen-customvoice", model_source: "http_service" },
      ttsConfig: null,
    })).toEqual({ scriptReady: true, voiceReady: true, ttsReady: true, ready: true });
  });
  it("blocks synthesis when the local speech service is unavailable", () => {
    expect(deriveEpisodeRenderReadiness({
      scriptReady: true, hasSelectedVoice: false, selectedEngine: "local_http", localVoiceMode: "preset",
      selectedModelId: "qwen-customvoice", capability: null, ttsConfig: null,
    }).ready).toBe(false);
  });
  it("requires a speaker reference before local cloning", () => {
    const capability = { provider: "local_http", runtime: "http", available: true, reasons: [], current_model: "qwen-customvoice", model_source: "http_service" };
    const base = { scriptReady: true, selectedEngine: "local_http" as const, localVoiceMode: "clone" as const, selectedModelId: "qwen-base-0.6b", capability, ttsConfig: null };
    expect(deriveEpisodeRenderReadiness({ ...base, hasSelectedVoice: false })).toEqual({
      scriptReady: true, voiceReady: false, ttsReady: true, ready: false,
    });
    expect(deriveEpisodeRenderReadiness({ ...base, hasSelectedVoice: true }).ready).toBe(true);
    expect(deriveEpisodeRenderReadiness({ ...base, hasSelectedVoice: true, selectedModelId: "" }).ttsReady).toBe(false);
  });
});

describe("model freshness", () => {
  const settings = { voice_id: "warm_narrator", voice_name: "", style_id: "natural", style_name: "", speed: 1, language: "zh", audio_format: "wav" };
  const project = {
    artifact: { script_artifacts: { "script-1": { voice_settings: settings } } },
    render_manifest: { pipeline: [{ stage: "speech_synthesis", provider: "local_http", model: "base-0.6b", adapter_version: "v1" }] },
  } as unknown as SessionProject;

  it("treats switching the clone model as a voice change", () => {
    const saved = savedVoiceFreshnessKey(project, "script-1", "unused");
    expect(buildVoiceFreshnessKey(project, "script-1", settings, "base-0.6b")).toBe(saved);
    expect(buildVoiceFreshnessKey(project, "script-1", settings, "base-1.7b")).not.toBe(saved);
  });

  it("does not flag audio while the model list is still loading", () => {
    expect(buildVoiceFreshnessKey(project, "script-1", settings, "")).toBe(savedVoiceFreshnessKey(project, "script-1", "unused"));
  });
});
