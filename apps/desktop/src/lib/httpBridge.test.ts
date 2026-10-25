import { afterEach, describe, expect, it, vi } from "vitest";

import type { InterviewTurnResult } from "../types";
import { createHttpBridge } from "./httpBridge";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HTTP reply streaming", () => {
  it("stops a suspended read without waiting for stream cancellation", async () => {
    const encoder = new TextEncoder();
    const abort = new AbortController();
    let cancelStarted = false;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: chunk\ndata: {"ok":true,"type":"chunk","delta":"Hello"}\n\n'));
      },
      cancel() {
        cancelStarted = true;
        return new Promise<void>(() => undefined);
      },
    });
    // Simulate a WebView that does not propagate fetch abort to reader.read().
    vi.stubGlobal("fetch", vi.fn(async () => new Response(stream)));
    const bridge = createHttpBridge({ baseUrl: "http://127.0.0.1:8765" });
    let receivedChunk: () => void = () => undefined;
    const chunkReceived = new Promise<void>((resolve) => { receivedChunk = resolve; });
    const reply = bridge.submitReplyStream("session-1", "Hi", receivedChunk, { signal: abort.signal });
    const rejected = expect(reply).rejects.toMatchObject({ name: "AbortError" });
    await chunkReceived;
    abort.abort();

    await rejected;
    expect(cancelStarted).toBe(true);
  });

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

describe("HTTP chat attachments", () => {
  it("uploads multipart files and sends attachment ids with the reply", async () => {
    const attachment = {
      attachment_id: "att_0123456789abcdef0123456789abcdef", session_id: "session-1", kind: "image",
      mime_type: "image/png", name: "cat.png", size_bytes: 3, sha256: "a".repeat(64), created_at: "2026-10-25T00:00:00Z",
    };
    const encoder = new TextEncoder();
    const fetchMock = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      if (String(url).endsWith("/attachments")) {
        expect(init?.method).toBe("POST");
        const body = init?.body as FormData;
        expect((body.get("file") as File).name).toBe("cat.png");
        return new Response(JSON.stringify({ ok: true, data: { attachment } }));
      }
      expect(String(url)).toContain("/interview:reply-stream");
      expect(JSON.parse(String(init?.body))).toEqual({
        message: "",
        user_requested_finish: false,
        attachment_ids: [attachment.attachment_id],
      });
      const final = `event: final\ndata: ${JSON.stringify({ ok: true, data: { next_question: "A cat." } })}\n\n`;
      return new Response(new ReadableStream({ start(c) { c.enqueue(encoder.encode(final)); } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const bridge = createHttpBridge({ baseUrl: "http://127.0.0.1:8765" });

    const uploaded = await bridge.uploadAttachment("session-1", new Blob(["png"]), "cat.png");
    const result = await bridge.submitReplyStream("session-1", "", () => undefined, {
      attachmentIds: [uploaded.attachment_id],
    });

    expect(uploaded).toEqual(attachment);
    expect(result.next_question).toBe("A cat.");
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
