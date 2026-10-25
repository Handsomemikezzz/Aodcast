import { useEffect, useState } from "react";
import { FileText, ImageOff, X } from "lucide-react";

import { useBridge } from "../lib/BridgeContext";
import {
  attachmentPreview,
  formatAttachmentSize,
  rememberAttachmentPreview,
  type PendingAttachment,
} from "../lib/chatAttachments";
import { cn } from "../lib/utils";
import type { ChatAttachment } from "../types";

/** Thumbnails and chips for attachments queued in a composer. */
export function PendingAttachmentTray({
  items,
  onRemove,
  disabled = false,
}: {
  items: PendingAttachment[];
  onRemove: (localId: string) => void;
  disabled?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 px-1 pt-1">
      {items.map((item) => (
        <div
          key={item.localId}
          className="group relative flex items-center gap-2 rounded-xl border border-outline bg-surface-container-low/70 overflow-hidden"
        >
          {item.previewUrl ? (
            <img src={item.previewUrl} alt={item.name} className="h-14 w-14 object-cover" />
          ) : (
            <div className="flex items-center gap-2 pl-3 pr-7 py-2 max-w-[220px]">
              <FileText className="w-4 h-4 text-accent-amber shrink-0" />
              <div className="min-w-0">
                <p className="truncate text-[12px] text-primary">{item.name}</p>
                <p className="text-[10px] text-secondary">{formatAttachmentSize(item.file.size)}</p>
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={() => onRemove(item.localId)}
            disabled={disabled}
            aria-label={`Remove ${item.name}`}
            className="absolute top-1 right-1 rounded-full bg-background/85 p-0.5 text-secondary hover:text-primary shadow-sm disabled:opacity-40"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      ))}
    </div>
  );
}

function AttachmentImage({ sessionId, attachment }: { sessionId: string; attachment: ChatAttachment }) {
  const bridge = useBridge();
  const [url, setUrl] = useState(() => attachmentPreview(attachment.attachment_id));
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const cached = attachmentPreview(attachment.attachment_id);
    if (cached) {
      setUrl(cached);
      return;
    }
    if (!sessionId || !attachment.session_id) return;
    let active = true;
    bridge
      .readAttachment(sessionId, attachment.attachment_id)
      .then((blob) => {
        // Cached for the page lifetime: the same turn re-renders on every transcript update.
        const objectUrl = URL.createObjectURL(blob);
        rememberAttachmentPreview(attachment.attachment_id, objectUrl);
        if (active) setUrl(objectUrl);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [bridge, sessionId, attachment.attachment_id, attachment.session_id]);

  if (failed) {
    return (
      <div className="flex h-24 w-24 flex-col items-center justify-center gap-1 rounded-lg border border-outline text-[10px] text-secondary">
        <ImageOff className="w-4 h-4" />
        <span className="max-w-[88px] truncate px-1">{attachment.name}</span>
      </div>
    );
  }
  return url ? (
    <a href={url} target="_blank" rel="noreferrer" title={attachment.name}>
      <img
        src={url}
        alt={attachment.name}
        className="max-h-48 max-w-[240px] rounded-lg border border-outline object-cover"
      />
    </a>
  ) : (
    <div className="h-24 w-24 animate-pulse rounded-lg border border-outline bg-surface-container-low" />
  );
}

/** Attachments shown inside a sent user bubble. */
export function TurnAttachments({
  sessionId,
  attachments,
  compact = false,
}: {
  sessionId: string;
  attachments?: ChatAttachment[];
  compact?: boolean;
}) {
  if (!attachments?.length) return null;
  const images = attachments.filter((item) => item.kind === "image");
  const documents = attachments.filter((item) => item.kind === "document");
  return (
    <div className={cn("flex flex-col items-end gap-2", compact && "gap-1")}>
      {images.length > 0 ? (
        <div className="flex flex-wrap justify-end gap-2">
          {images.map((item) => (
            <AttachmentImage key={item.attachment_id} sessionId={sessionId} attachment={item} />
          ))}
        </div>
      ) : null}
      {documents.map((item) => (
        <div
          key={item.attachment_id}
          className="flex max-w-[260px] items-center gap-2 rounded-lg border border-outline bg-surface-container-low/70 px-2.5 py-1.5"
        >
          <FileText className="w-3.5 h-3.5 text-accent-amber shrink-0" />
          <span className="truncate text-[12px] text-primary">{item.name}</span>
          <span className="shrink-0 text-[10px] text-secondary">{formatAttachmentSize(item.size_bytes)}</span>
        </div>
      ))}
    </div>
  );
}

/** Files carried by a paste or drop event, if any. */
export function filesFromDataTransfer(data: DataTransfer | null): File[] {
  if (!data) return [];
  return Array.from(data.files);
}
