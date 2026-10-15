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

describe("HTTP speech provider configuration", () => {
  it("sends only the external service contract", async () => {
    const config = {
      provider: "local_http", model: "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit",
      base_url: "http://127.0.0.1:8090/v1", api_key: "", voice: "默认中文音色", audio_format: "wav",
    };
    const fetchMock = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      if (String(url).endsWith("/runtime/bootstrap")) {
        return new Response(JSON.stringify({ ok: true, data: { token: "test-token" } }));
      }
      expect(String(url)).toBe("http://127.0.0.1:8765/api/v1/config/tts");
      expect(init?.method).toBe("PUT");
      expect(JSON.parse(String(init?.body))).toEqual(config);
      return new Response(JSON.stringify({ ok: true, data: { tts_config: config } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await createHttpBridge({ baseUrl: "http://127.0.0.1:8765" }).configureTTSProvider(config);
    expect(result).toEqual(config);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
