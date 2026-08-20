import { describe, expect, it } from "vitest";
import { keepCancellationProgress } from "./requestState";
import type { RequestState } from "../types";

function state(phase: RequestState["phase"], runToken: string): RequestState {
  return {
    operation: "render_audio",
    phase,
    progress_percent: phase === "succeeded" ? 100 : 40,
    message: phase,
    run_token: runToken,
  };
}

describe("keepCancellationProgress", () => {
  it("does not regress cancellation for the same task run", () => {
    const cancelling = state("cancelling", "run-a");
    expect(keepCancellationProgress(cancelling, state("running", "run-a"))).toBe(cancelling);
  });

  it("accepts a running state from a newer run token", () => {
    const running = state("running", "run-b");
    expect(keepCancellationProgress(state("cancelling", "run-a"), running)).toBe(running);
  });
});
