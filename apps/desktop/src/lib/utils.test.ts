import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("keeps custom font-size and color together", () => {
    expect(cn("px-3 text-body text-primary", "font-mono")).toBe("px-3 text-body text-primary font-mono");
  });
  it("lets a later size override an earlier size", () => {
    expect(cn("text-body", "text-meta")).toBe("text-meta");
  });
  it("lets a later color override an earlier color", () => {
    expect(cn("text-secondary", "text-primary")).toBe("text-primary");
  });
  it("treats status tokens as colors", () => {
    expect(cn("text-meta text-danger", "text-success bg-danger-container", "bg-warning-container")).toBe(
      "text-meta text-success bg-warning-container",
    );
  });
});
