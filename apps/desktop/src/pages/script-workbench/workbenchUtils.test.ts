import { describe, expect, it } from "vitest";
import { contextWindowSegmentIds } from "./workbenchUtils";

const segments = ["A", "B", "C", "D", "E"].map((segment_id) => ({ segment_id }));

describe("contextWindowSegmentIds", () => {
  it("expands an interior target to its B-C-D context window", () => {
    expect(contextWindowSegmentIds(segments, "C")).toEqual(["B", "C", "D"]);
  });

  it("clips the context window at the first and last segment", () => {
    expect(contextWindowSegmentIds(segments, "A")).toEqual(["A", "B"]);
    expect(contextWindowSegmentIds(segments, "E")).toEqual(["D", "E"]);
  });

  it("returns no window for a stale segment id", () => {
    expect(contextWindowSegmentIds(segments, "missing")).toEqual([]);
  });
});
