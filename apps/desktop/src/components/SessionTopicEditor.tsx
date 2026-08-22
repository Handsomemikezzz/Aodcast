import { useEffect, useRef, useState } from "react";
import { Loader2, PencilLine } from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { cn } from "../lib/utils";
import type { SessionProject } from "../types";

type SessionTopicEditorProps = {
  sessionId: string;
  topic: string;
  onRenamed: (project: SessionProject) => void | Promise<void>;
  disabled?: boolean;
  /** Visual density for list rows vs headers */
  density?: "list" | "header" | "app";
  className?: string;
};

/**
 * Inline rename for session.topic via renameSession.
 * Enter commits, Escape cancels; empty input cancels without calling the API.
 */
export function SessionTopicEditor({
  sessionId,
  topic,
  onRenamed,
  disabled = false,
  density = "list",
  className,
}: SessionTopicEditorProps) {
  const bridge = useBridge();
  const inputRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(topic);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) setDraft(topic);
  }, [topic, editing]);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const startEditing = () => {
    if (disabled || saving) return;
    setError(null);
    setDraft(topic);
    setEditing(true);
  };

  const cancelEditing = () => {
    if (saving) return;
    setEditing(false);
    setDraft(topic);
    setError(null);
  };

  const commit = async () => {
    const next = draft.trim();
    if (!next || next === topic.trim()) {
      cancelEditing();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await bridge.renameSession(sessionId, next);
      await onRenamed(updated);
      setEditing(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to rename.");
    } finally {
      setSaving(false);
    }
  };

  const titleClass =
    density === "app"
      ? "font-headline font-semibold text-[15px] tracking-wide text-primary truncate"
      : density === "header"
        ? "truncate text-[13px] font-semibold text-primary leading-tight"
        : "font-medium text-[14px] text-primary truncate";

  const inputClass =
    density === "app"
      ? "min-w-0 flex-1 max-w-[280px] bg-background font-headline font-semibold text-[15px] tracking-wide text-primary border border-accent-amber/40 rounded-lg px-2 py-1 outline-none focus:border-accent-amber/70"
      : density === "header"
        ? "min-w-0 w-full max-w-[220px] bg-background text-[13px] font-semibold text-primary border border-accent-amber/40 rounded-lg px-2 py-1 outline-none focus:border-accent-amber/70"
        : "min-w-0 flex-1 bg-background text-[14px] font-medium text-primary border border-accent-amber/40 rounded-lg px-2 py-1.5 outline-none focus:border-accent-amber/70";

  if (editing) {
    return (
      <div className={cn("min-w-0", className)}>
        <div className="flex items-center gap-1.5 min-w-0">
          <input
            ref={inputRef}
            value={draft}
            disabled={saving}
            aria-label="Episode name"
            onChange={(event) => setDraft(event.target.value.slice(0, 200))}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void commit();
              } else if (event.key === "Escape") {
                event.preventDefault();
                cancelEditing();
              }
            }}
            onBlur={() => {
              if (!saving) void commit();
            }}
            className={inputClass}
          />
          {saving ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent-amber" /> : null}
        </div>
        {error ? <p className="mt-1 text-[11px] text-red-300">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className={cn("group/topic flex items-center gap-1 min-w-0", className)}>
      {density === "list" ? (
        <p className={cn(titleClass, "min-w-0 flex-1")}>{topic || "Untitled Episode"}</p>
      ) : (
        <button
          type="button"
          onClick={startEditing}
          disabled={disabled}
          title="Rename"
          className={cn(titleClass, "text-left disabled:opacity-50 no-drag")}
        >
          {topic || "Untitled Episode"}
        </button>
      )}
      <button
        type="button"
        onClick={startEditing}
        disabled={disabled}
        aria-label={`Rename "${topic || "Untitled Episode"}"`}
        className={cn(
          "no-drag inline-flex shrink-0 items-center justify-center rounded-md text-secondary transition-colors hover:bg-surface-container-high hover:text-primary disabled:opacity-50",
          density === "list" ? "h-8 w-8" : "h-7 w-7 opacity-0 group-hover/topic:opacity-100 focus-visible:opacity-100",
        )}
      >
        <PencilLine className={density === "list" ? "h-3.5 w-3.5" : "h-3 w-3"} />
      </button>
    </div>
  );
}
