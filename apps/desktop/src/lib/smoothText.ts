/**
 * Paces bursty LLM stream deltas into a steady character-by-character reveal.
 * Reveal speed scales with the backlog, so the display never trails the
 * network by much more than TARGET_LAG_SECONDS no matter how large a burst is.
 */
const MIN_CHARS_PER_SECOND = 40;
const TARGET_LAG_SECONDS = 0.4;
const MAX_FRAME_SECONDS = 0.1;

export interface FrameScheduler {
  request(callback: (nowMs: number) => void): number;
  cancel(id: number): void;
}

export interface SmoothTextBuffer {
  push(delta: string): void;
  /** Resolves once every pushed character is visible (immediately when the page is hidden). */
  drain(): Promise<void>;
  /** Stops revealing and releases any pending drain. */
  cancel(): void;
}

const browserScheduler: FrameScheduler = {
  request: (callback) => requestAnimationFrame(callback),
  cancel: (id) => cancelAnimationFrame(id),
};

function isPageHidden(): boolean {
  return typeof document !== "undefined" && document.hidden;
}

export function createSmoothTextBuffer(
  onUpdate: (text: string) => void,
  scheduler: FrameScheduler = browserScheduler,
): SmoothTextBuffer {
  // Code points, so surrogate pairs (emoji) are never split mid-character.
  const chars: string[] = [];
  let shown = 0;
  let text = "";
  let budget = 0;
  let lastFrameMs: number | null = null;
  let frameId: number | null = null;
  let drainWaiters: Array<() => void> = [];

  const settle = () => {
    lastFrameMs = null;
    budget = 0;
    const waiters = drainWaiters;
    drainWaiters = [];
    waiters.forEach((resolve) => resolve());
  };

  const reveal = (count: number) => {
    text += chars.slice(shown, shown + count).join("");
    shown += count;
    onUpdate(text);
  };

  const tick = (nowMs: number) => {
    frameId = null;
    const elapsed = lastFrameMs === null ? 1 / 60 : Math.min((nowMs - lastFrameMs) / 1000, MAX_FRAME_SECONDS);
    lastFrameMs = nowMs;
    const backlog = chars.length - shown;
    budget += Math.max(MIN_CHARS_PER_SECOND, backlog / TARGET_LAG_SECONDS) * elapsed;
    const step = Math.min(backlog, Math.floor(budget));
    if (step > 0) {
      budget -= step;
      reveal(step);
    }
    if (shown < chars.length) {
      frameId = scheduler.request(tick);
    } else {
      settle();
    }
  };

  return {
    push(delta) {
      if (!delta) return;
      chars.push(...Array.from(delta));
      if (frameId === null) frameId = scheduler.request(tick);
    },
    drain() {
      if (shown < chars.length && isPageHidden()) {
        // Animation frames are paused in background tabs; show everything now.
        if (frameId !== null) scheduler.cancel(frameId);
        frameId = null;
        reveal(chars.length - shown);
      }
      if (shown >= chars.length) {
        settle();
        return Promise.resolve();
      }
      return new Promise((resolve) => drainWaiters.push(resolve));
    },
    cancel() {
      if (frameId !== null) scheduler.cancel(frameId);
      frameId = null;
      settle();
    },
  };
}
