import { afterEach, describe, expect, it, vi } from "vitest";

import { attachmentKindForFile, MAX_ATTACHMENTS_PER_TURN, toPendingAttachments } from "./chatAttachments";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("chat attachments", () => {
  it("classifies by extension first and falls back to image MIME for pasted screenshots", () => {
    expect(attachmentKindForFile("notes.md", "")).toBe("document");
    expect(attachmentKindForFile("scan.PDF", "application/pdf")).toBe("document");
    expect(attachmentKindForFile("photo.jpeg", "image/jpeg")).toBe("image");
    expect(attachmentKindForFile("", "image/png")).toBe("image");
    expect(attachmentKindForFile("tool.exe", "application/octet-stream")).toBeNull();
  });

  it("accepts supported files, previews images, and reports rejections", () => {
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:preview" });
    const files = [
      new File(["png"], "cat.png", { type: "image/png" }),
      new File(["# hi"], "notes.md"),
      new File(["MZ"], "tool.exe"),
    ];

    const { accepted, error } = toPendingAttachments(files, 0);

    expect(accepted.map((item) => [item.name, item.kind, item.previewUrl])).toEqual([
      ["cat.png", "image", "blob:preview"],
      ["notes.md", "document", undefined],
    ]);
    expect(error).toContain("tool.exe");
  });

  it("names pasted images and enforces the per-message limit", () => {
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:preview" });
    const pasted = new File(["png"], "", { type: "image/png" });

    const { accepted, error } = toPendingAttachments([pasted, pasted], MAX_ATTACHMENTS_PER_TURN - 1);

    expect(accepted).toHaveLength(1);
    expect(accepted[0].name).toBe("pasted-image.png");
    expect(error).toContain(String(MAX_ATTACHMENTS_PER_TURN));
  });
});
