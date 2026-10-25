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

  it("drains every pushed character and never splits emoji", async () => {
    const { scheduler, frame, hasPending } = manualScheduler();
    const updates: string[] = [];
    const buffer = createSmoothTextBuffer((text) => updates.push(text), scheduler);

    buffer.push("你好😀");
    buffer.push("世界");
    const drained = buffer.drain();
    while (hasPending()) frame();
    await drained;

    expect(updates[updates.length - 1]).toBe("你好😀世界");
    expect(updates.every((text) => !/[\uD800-\uDBFF]$/.test(text))).toBe(true);
  });

  it("cancel releases a pending drain", async () => {
    const { scheduler } = manualScheduler();
    const buffer = createSmoothTextBuffer(() => {}, scheduler);

    buffer.push("还没显示完的内容");
    const drained = buffer.drain();
    buffer.cancel();

    await expect(drained).resolves.toBeUndefined();
  });
});
