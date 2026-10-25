import type { ChatAttachment } from "../types";

// Mirrors the runtime limits in services/python-core/app/domain/attachment.py;
// the runtime stays authoritative and these only give early feedback.
export const MAX_ATTACHMENTS_PER_TURN = 8;
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".gif"];
const DOCUMENT_EXTENSIONS = [".txt", ".md", ".markdown", ".csv", ".json", ".pdf"];
const IMAGE_MIME_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

export const ATTACHMENT_ACCEPT = [...IMAGE_EXTENSIONS, ...DOCUMENT_EXTENSIONS].join(",");

export type PendingAttachment = {
  localId: string;
  file: Blob;
  name: string;
  kind: ChatAttachment["kind"];
  /** Object URL for image thumbnails. */
  previewUrl?: string;
};

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export function attachmentKindForFile(name: string, type: string): ChatAttachment["kind"] | null {
  const extension = extensionOf(name);
  if (IMAGE_EXTENSIONS.includes(extension)) return "image";
  if (DOCUMENT_EXTENSIONS.includes(extension)) return "document";
  // Pasted screenshots may arrive without a usable file name.
  if (IMAGE_MIME_TYPES.includes(type)) return "image";
  return null;
}

let localCounter = 0;

/** Turn picked, pasted, or dropped files into pending attachments, reporting what was rejected. */
export function toPendingAttachments(
  files: File[],
  existingCount: number,
): { accepted: PendingAttachment[]; error: string | null } {
  const accepted: PendingAttachment[] = [];
  const problems: string[] = [];
  for (const file of files) {
    const name = file.name || `pasted-image${file.type === "image/jpeg" ? ".jpg" : ".png"}`;
    const kind = attachmentKindForFile(name, file.type);
    if (!kind) {
      problems.push(`Unsupported file type: ${name}`);
      continue;
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      problems.push(`Larger than 10 MB: ${name}`);
      continue;
    }
    if (existingCount + accepted.length >= MAX_ATTACHMENTS_PER_TURN) {
      problems.push(`Up to ${MAX_ATTACHMENTS_PER_TURN} attachments per message`);
      break;
    }
    localCounter += 1;
    accepted.push({
      localId: `local_${Date.now()}_${localCounter}`,
      file,
      name,
      kind,
      previewUrl: kind === "image" ? URL.createObjectURL(file) : undefined,
    });
  }
  return { accepted, error: problems.length ? problems.join("；") : null };
}

// Image object URLs keyed by attachment id (or a pending local id), shared by
// the composer, optimistic bubbles, and saved transcript turns.
const previewUrls = new Map<string, string>();

export function rememberAttachmentPreview(id: string, url: string): void {
  previewUrls.set(id, url);
}

export function attachmentPreview(id: string): string | undefined {
  return previewUrls.get(id);
}

/** Display-only stand-in for an attachment that has not been uploaded yet. */
export function pendingAsChatAttachment(item: PendingAttachment): ChatAttachment {
  if (item.previewUrl) rememberAttachmentPreview(item.localId, item.previewUrl);
  return {
    attachment_id: item.localId,
    session_id: "",
    kind: item.kind,
    mime_type: item.file.type,
    name: item.name,
    size_bytes: item.file.size,
    sha256: "",
    created_at: new Date().toISOString(),
  };
}

export function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
