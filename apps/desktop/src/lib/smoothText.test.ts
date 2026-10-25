import { describe, expect, it } from "vitest";
import { createSmoothTextBuffer, type FrameScheduler } from "./smoothText";

function manualScheduler() {
  let pending: ((nowMs: number) => void) | null = null;
  let nowMs = 0;
  const scheduler: FrameScheduler = {
    request(callback) {
      pending = callback;
      return 1;
    },
    cancel() {
      pending = null;
    },
  };
  const frame = (ms = 1000 / 60) => {
    const callback = pending;
    pending = null;
    nowMs += ms;
    callback?.(nowMs);
  };
  return { scheduler, frame, hasPending: () => pending !== null };
}

describe("createSmoothTextBuffer", () => {
  it("reveals a burst gradually instead of all at once", () => {
    const { scheduler, frame } = manualScheduler();
    const updates: string[] = [];
    const buffer = createSmoothTextBuffer((text) => updates.push(text), scheduler);

    buffer.push("我完全可以正常交流。看起来你刚才先用测试来试探一下这里的反应。");
    frame();
    frame();

    expect(updates.length).toBeGreaterThan(0);
    expect(updates[updates.length - 1].length).toBeLessThan(10);
  });

  it("reveals every pushed character and never splits emoji", () => {
    const { scheduler, frame, hasPending } = manualScheduler();
    const updates: string[] = [];
    const buffer = createSmoothTextBuffer((text) => updates.push(text), scheduler);

    buffer.push("你好😀");
    buffer.push("世界");
    while (hasPending()) frame();

    expect(updates[updates.length - 1]).toBe("你好😀世界");
    expect(updates.every((text) => !/[\uD800-\uDBFF]$/.test(text))).toBe(true);
  });

  it("finishes immediately when animation frames are suspended", () => {
    const { scheduler, hasPending } = manualScheduler();
    const updates: string[] = [];
    const buffer = createSmoothTextBuffer((text) => updates.push(text), scheduler);

    buffer.push("还没显示完的内容");
    buffer.finish();
    buffer.push("迟到的内容");

    expect(updates).toEqual(["还没显示完的内容"]);
    expect(hasPending()).toBe(false);
  });

  it("cancel discards queued and late deltas", () => {
    const { scheduler, frame, hasPending } = manualScheduler();
    const updates: string[] = [];
    const buffer = createSmoothTextBuffer((text) => updates.push(text), scheduler);

    buffer.push("还没显示完的内容");
    buffer.cancel();
    buffer.push("迟到的内容");
    buffer.finish();
    frame();

    expect(updates).toEqual([]);
    expect(hasPending()).toBe(false);
  });
});
