import { afterEach, describe, expect, it, vi } from "vitest";

import type { InterviewTurnResult } from "../types";
import { createHttpBridge } from "./httpBridge";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HTTP reply streaming", () => {
  it("resolves on the final SSE event without waiting for reader cancellation", async () => {
    const encoder = new TextEncoder();
    const finalResult = { next_question: "Done" } as unknown as InterviewTurnResult;
    const body = [
      'event: chunk\ndata: {"ok":true,"type":"chunk","delta":"Hello"}\n\n',
      `event: final\ndata: ${JSON.stringify({ ok: true, data: finalResult })}\n\n`,
    ].join("");
    let cancelStarted = false;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(body));
      },
      cancel() {
        cancelStarted = true;
        return new Promise<void>(() => undefined);
      },
    });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(stream, { status: 200 })));

    const deltas: string[] = [];
    const bridge = createHttpBridge({ baseUrl: "http://127.0.0.1:8765" });
    let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
    const outcome = await Promise.race([
      bridge.submitReplyStream("session-1", "Hi", (delta) => deltas.push(delta)),
      new Promise<"timeout">((resolve) => {
        timeoutHandle = setTimeout(() => resolve("timeout"), 250);
      }),
    ]);
    clearTimeout(timeoutHandle);

    expect(outcome).toEqual(finalResult);
    expect(deltas).toEqual(["Hello"]);
    expect(cancelStarted).toBe(true);
  });
});
