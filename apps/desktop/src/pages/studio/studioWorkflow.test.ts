import { describe, expect, it } from "vitest";
import { deriveAudioFreshness, resolveGlobalCtaKind } from "./studioWorkflow";

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
});
