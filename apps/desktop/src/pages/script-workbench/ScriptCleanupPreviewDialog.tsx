import { X } from "lucide-react";
import type { CleanupPreview } from "./spokenScriptTypes";

type ScriptCleanupPreviewDialogProps = {
  open: boolean;
  preview: CleanupPreview | null;
  onClose: () => void;
  onApply: () => void;
};

export function ScriptCleanupPreviewDialog({
  open,
  preview,
  onClose,
  onApply,
}: ScriptCleanupPreviewDialogProps) {
  if (!open || !preview) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-outline bg-surface shadow-2xl shadow-black/30">
        <div className="flex items-start justify-between gap-3 border-b border-outline px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-primary">Preview cleanup changes</h2>
            <p className="mt-1 text-sm leading-relaxed text-secondary">
              Review the proposed edits before applying them to the current script. Changes are not saved until you click Save.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-secondary transition-colors hover:bg-surface-container-high hover:text-primary"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {preview.changes.length ? (
            <ul className="space-y-3">
              {preview.changes.map((change, index) => (
                <li
                  key={`${change.description}-${index}`}
                  className="rounded-xl border border-outline bg-surface-container-low px-4 py-3 text-sm"
                >
                  <p className="font-medium text-primary">{change.description}</p>
                  <div className="mt-2 grid gap-2 text-xs">
                    <div>
                      <span className="font-semibold uppercase tracking-wide text-secondary/70">Before</span>
                      <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-black/20 px-3 py-2 text-secondary">
                        {change.before || "(empty)"}
                      </pre>
                    </div>
                    <div>
                      <span className="font-semibold uppercase tracking-wide text-secondary/70">After</span>
                      <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-black/20 px-3 py-2 text-primary">
                        {change.after || "(removed)"}
                      </pre>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-secondary">No cleanup changes were detected.</p>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-2 border-t border-outline px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-outline bg-surface-container px-3 py-2 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onApply}
            disabled={!preview.hasChanges}
            className="rounded-md border border-primary/20 bg-primary/12 px-3 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/18 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Apply cleanup
          </button>
        </div>
      </div>
    </div>
  );
}
