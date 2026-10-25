import { describe, expect, it } from "vitest";
import { modelMode, readyModelForMode, readySpeechModel, referenceDurationIssue } from "./voiceSettings";
import type { ModelStatus } from "../types";

const qwen: ModelStatus = { model_name: "qwen", display_name: "Qwen", hf_repo_id: "service/qwen", available: true, active: true, ready: false };
const kokoro: ModelStatus = { model_name: "kokoro", display_name: "Kokoro", hf_repo_id: "service/kokoro", available: true, active: false, ready: true };

describe("speech service model selection", () => {
  it("uses the actual service model after its configuration changes", () => {
    expect(readySpeechModel([qwen, kokoro], "service/qwen", "qwen")).toEqual(kokoro);
  });
  it("does not enable synthesis based only on the saved active model", () => {
    expect(readySpeechModel([qwen], "service/qwen")).toBeUndefined();
  });
  it("does not choose a model when the service is unavailable", () => {
    expect(readySpeechModel([{ ...kokoro, available: false }])).toBeUndefined();
  });
});

describe("local voice modes", () => {
  const cloning = (level: "native" | "unsupported") =>
    ({ capabilities: { speaker_cloning: level } }) as unknown as ModelStatus["capabilities"];
  const preset: ModelStatus = { model_name: "custom", display_name: "CustomVoice", hf_repo_id: "service/custom", ready: true, capabilities: cloning("unsupported"), default_for_mode: true };
  const small: ModelStatus = { model_name: "small", display_name: "0.6B Base", hf_repo_id: "service/base-0.6b", ready: true, capabilities: cloning("native"), default_for_mode: true };
  const large: ModelStatus = { model_name: "large", display_name: "1.7B Base", hf_repo_id: "service/base-1.7b", ready: true, capabilities: cloning("native") };

  it("defaults cloning to the small Base model and keeps an explicit 1.7B choice", () => {
    expect(readyModelForMode([preset, large, small], "clone")).toEqual(small);
    expect(readyModelForMode([preset, large, small], "clone", "service/base-1.7b")).toEqual(large);
  });
  it("never answers a clone request with a preset model, or the reverse", () => {
    expect(readyModelForMode([preset], "clone", "service/custom")).toBeUndefined();
    expect(readyModelForMode([small, large], "preset", "service/base-0.6b")).toBeUndefined();
  });
  it("reads the voice mode from the declared cloning capability", () => {
    expect(modelMode(small)).toBe("clone");
    expect(modelMode(preset)).toBe("preset");
    expect(modelMode({ model_name: "x", display_name: "x" })).toBe("preset");
  });
  it("explains references outside the service's cloning window", () => {
    const limits = { min: 3000, max: 30000 };
    expect(referenceDurationIssue(12000, limits)).toBe("");
    expect(referenceDurationIssue(45000, limits)).toContain("at most 30 s");
    expect(referenceDurationIssue(2000, limits)).toContain("at least 3 s");
    expect(referenceDurationIssue(600000, {})).toBe("");
  });
});
