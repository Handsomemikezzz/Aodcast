import { describe, expect, it } from "vitest";
import { readySpeechModel } from "./voiceSettings";
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
