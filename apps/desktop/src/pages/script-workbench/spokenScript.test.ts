import { describe, expect, it } from "vitest";
import { analyzeSpokenScript, findStageDirectionSpans } from "./spokenScriptChecks";
import { buildScriptCleanupPreview } from "./spokenScriptCleanup";

describe("analyzeSpokenScript", () => {
  it("blocks empty scripts", () => {
    const result = analyzeSpokenScript("   \n  ");
    expect(result.canRender).toBe(false);
    expect(result.blockingCount).toBeGreaterThan(0);
  });

  it("blocks speaker labels with indentation", () => {
    const result = analyzeSpokenScript("  Host: hello there");
    expect(result.canRender).toBe(false);
    expect(result.issues.some((issue) => issue.level === "blocking" && issue.cleanable)).toBe(true);
  });

  it("blocks keyword stage directions anywhere in a line", () => {
    const result = analyzeSpokenScript("今天开始。[停顿] 接着说下去。");
    expect(result.canRender).toBe(false);
    expect(findStageDirectionSpans("今天开始。[停顿] 接着说下去。").map((item) => item.match)).toContain("[停顿]");
  });

  it("does not block spoken asides without stage-direction keywords", () => {
    const result = analyzeSpokenScript("（这是我当时最真实的想法）");
    expect(result.canRender).toBe(true);
    expect(result.blockingCount).toBe(0);
  });

  it("blocks keyword-only bracketed production notes", () => {
    const result = analyzeSpokenScript("[music]");
    expect(result.canRender).toBe(false);
  });
});

describe("buildScriptCleanupPreview", () => {
  it("removes indented speaker labels", () => {
    const preview = buildScriptCleanupPreview("  Host: hello there");
    expect(preview.hasChanges).toBe(true);
    expect(preview.cleaned).toBe("  hello there");
  });

  it("removes inline keyword stage directions", () => {
    const preview = buildScriptCleanupPreview("今天开始。[停顿] 接着说下去。");
    expect(preview.hasChanges).toBe(true);
    expect(preview.cleaned).toBe("今天开始。 接着说下去。");
  });

  it("leaves spoken asides without stage-direction keywords untouched", () => {
    const preview = buildScriptCleanupPreview("（这是我当时最真实的想法）");
    expect(preview.hasChanges).toBe(false);
    expect(preview.cleaned).toBe("（这是我当时最真实的想法）");
  });
});

describe("render guard inputs", () => {
  it("treats persisted blocked script as non-renderable even when local edits are clean", () => {
    const persisted = analyzeSpokenScript("Host: blocked narration");
    const localDraft = analyzeSpokenScript("This clean narration can render.");
    expect(localDraft.canRender).toBe(true);
    expect(persisted.canRender).toBe(false);
  });
});
