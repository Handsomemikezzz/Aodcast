import { describe, expect, it } from "vitest";
import { buildPreviewExcerpt, deriveAudioFreshness, resolveGlobalCtaKind } from "./studioWorkflow";

describe("studio workflow helpers", () => {
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
      reason: "Voice settings changed.",
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
