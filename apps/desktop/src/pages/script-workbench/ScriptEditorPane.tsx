import { useState } from "react";
import { CheckCircle2, ChevronDown, Loader2, RefreshCw, Sparkles, Trash2, Wand2, AlertCircle } from "lucide-react";
import { cn } from "../../lib/utils";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";
import type { EditorDisplayMode, ScriptIssue } from "./spokenScriptTypes";

function issueTone(level: ScriptIssue["level"]): string {
  if (level === "blocking") return "text-red-300";
  if (level === "warning") return "text-amber-200";
  return "text-secondary/80";
}

function statusTone(workbench: UseScriptWorkbenchResult): string {
  if (workbench.scriptCheck.blockingCount > 0) return "text-red-300";
  if (workbench.scriptCheck.warningCount > 0) return "text-amber-200";
  return "text-emerald-300";
}

function AutosaveChip({
  saving,
  isDirty,
  editorError,
  onRetry,
}: {
  saving: boolean;
  isDirty: boolean;
  editorError: string | null;
  onRetry: () => void;
}) {
  if (editorError) {
    return (
      <span className="autosave-chip autosave-chip-error flex items-center gap-1">
        <AlertCircle className="w-3 h-3" />
        Save failed
        <button
          type="button"
          onClick={onRetry}
          className="ml-1 underline underline-offset-2 cursor-pointer hover:no-underline"
        >
          Retry
        </button>
      </span>
    );
  }
  if (saving) {
    return (
      <span className="autosave-chip autosave-chip-saving flex items-center gap-1">
        <Loader2 className="w-3 h-3 animate-spin" />
        Saving...
      </span>
    );
  }
  if (isDirty) {
    return (
      <span className="autosave-chip autosave-chip-dirty flex items-center gap-1">
        Unsaved changes
      </span>
    );
  }
  return (
    <span className="autosave-chip autosave-chip-saved flex items-center gap-1">
      <CheckCircle2 className="w-3 h-3" />
      Saved
    </span>
  );
}

export function ScriptEditorPane({
  workbench,
  textareaRef: externalRef,
}: {
  workbench: UseScriptWorkbenchResult;
  /** Optional external ref to focus the textarea programmatically */
  textareaRef?: React.RefObject<HTMLTextAreaElement>;
}) {
  const [editorMode, setEditorMode] = useState<EditorDisplayMode>("script");
  const [issuesExpanded, setIssuesExpanded] = useState(false);

  const visibleIssues = workbench.scriptCheck.issues.filter((issue) => issue.level !== "info");
  const infoIssues = workbench.scriptCheck.issues.filter((issue) => issue.level === "info");
  const showIssuePanel = issuesExpanded && workbench.scriptCheck.issues.length > 0;

  // Use external ref if provided, otherwise fall back to workbench ref
  const ref = externalRef ?? workbench.textareaRef;

  return (
    <section className="flex min-w-0 min-h-0 flex-col gap-5 overflow-hidden h-full">
      <div className="rounded-[28px] border border-outline bg-surface-container backdrop-blur-md shadow-[0_12px_32px_rgba(0,0,0,0.04)] overflow-hidden flex flex-col h-full">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline px-5 py-3 shrink-0">
          <div className="inline-flex rounded-xl border border-outline bg-surface-container-low p-0.5">
            <button
              type="button"
              onClick={() => setEditorMode("script")}
              className={cn(
                "rounded-[10px] px-3.5 py-1.5 text-xs font-bold transition-all cursor-pointer",
                editorMode === "script"
                  ? "bg-accent-amber/15 text-accent-amber shadow-[0_0_12px_rgba(161,123,67,0.08)]"
                  : "text-secondary hover:text-primary",
              )}
            >
              Script
            </button>
            <button
              type="button"
              onClick={() => setEditorMode("plain")}
              className={cn(
                "rounded-[10px] px-3.5 py-1.5 text-xs font-bold transition-all cursor-pointer",
                editorMode === "plain"
                  ? "bg-primary/8 text-primary"
                  : "text-secondary hover:text-primary",
              )}
            >
              Plain text
            </button>
          </div>
          <div className="flex items-center gap-2 text-xs text-secondary/80 font-medium select-none">
            <Sparkles className="h-3.5 w-3.5 text-accent-amber" />
            Every visible character will be spoken by TTS
          </div>
        </div>

        {/* Textarea */}
        <div className="flex-1 overflow-y-auto px-5 pb-5 pt-4 mac-scrollbar">
          <textarea
            ref={ref}
            value={workbench.script}
            onChange={(event) => workbench.setScript(event.target.value)}
            disabled={workbench.isScriptDeleted || workbench.isSessionDeleted}
            spellCheck={false}
            placeholder="Write the exact narration you want spoken in the final audio."
            className={cn(
              "min-h-[480px] w-full resize-none rounded-[20px] border border-outline bg-surface-container-low px-6 py-6 text-primary outline-none transition-all placeholder:text-secondary/30 focus:border-accent-amber/30 focus:bg-background focus:shadow-[0_0_24px_rgba(242,191,87,0.03)] disabled:opacity-40",
              editorMode === "script"
                ? "text-[16px] leading-[2.1rem] tracking-[0.01em]"
                : "text-[14px] leading-[2rem] font-mono",
            )}
          />
        </div>

        {/* Status bar */}
        <div className="border-t border-outline px-5 py-3 shrink-0">
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-secondary/80 font-medium">
            {/* Left: checks + stats + autosave */}
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={() => setIssuesExpanded((expanded) => !expanded)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1 font-bold transition-all cursor-pointer text-[11px]",
                  workbench.scriptCheck.blockingCount > 0
                    ? "border-red-500/20 bg-red-500/10 text-red-200 hover:bg-red-500/15"
                    : workbench.scriptCheck.warningCount > 0
                      ? "border-amber-500/20 bg-amber-500/10 text-amber-100 hover:bg-amber-500/15"
                      : "border-emerald-500/20 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/15",
                )}
              >
                <span className={statusTone(workbench)}>{workbench.scriptCheck.statusLabel}</span>
                <ChevronDown className={cn("h-3 w-3 transition-transform", issuesExpanded && "rotate-180")} />
              </button>
              <span className="text-[11px]">{workbench.wordCount} words</span>
              <span className="text-primary/10">/</span>
              <span className="text-[11px]">{workbench.estMinutes} spoken</span>
              <span className="text-primary/10">/</span>
              <AutosaveChip
                saving={workbench.saving}
                isDirty={workbench.isDirty}
                editorError={workbench.editorError}
                onRetry={() => void workbench.handleSave()}
              />
            </div>

            {/* Right: actions */}
            <div className="flex items-center gap-2">
              {workbench.scriptCheck.hasCleanableIssues ? (
                <button
                  type="button"
                  onClick={workbench.handleOpenCleanupPreview}
                  disabled={workbench.isScriptDeleted || workbench.isSessionDeleted}
                  className="inline-flex items-center gap-1 rounded-xl border border-accent-amber/20 bg-accent-amber/10 px-2.5 py-1 text-[11px] font-bold text-accent-amber hover:bg-accent-amber/15 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <Wand2 className="h-3 w-3" />
                  Clean all
                </button>
              ) : null}
              {workbench.editorRequestState?.phase === "running" ? (
                <span className="mr-1 text-secondary/60 animate-pulse text-[11px]">
                  {workbench.editorRequestState.message}
                </span>
              ) : null}
              <button
                type="button"
                onClick={() =>
                  workbench.runWithUnsavedCheck(async () => {
                    await workbench.reload();
                  })
                }
                className="inline-flex items-center gap-1 rounded-xl border border-outline bg-surface-container-low px-2.5 py-1 text-[11px] font-bold text-secondary hover:text-primary hover:bg-primary/8 hover:border-accent-amber/20 active:scale-[0.98] transition-all cursor-pointer"
              >
                <RefreshCw className="h-3 w-3" />
                Refresh
              </button>
              <button
                type="button"
                onClick={() => workbench.setDialogState({ kind: "delete-script" })}
                disabled={
                  workbench.isScriptDeleted ||
                  workbench.isSessionDeleted ||
                  workbench.busyAction === "delete-script"
                }
                className="inline-flex items-center gap-1 rounded-xl border border-red-500/10 bg-red-500/5 px-2.5 py-1 text-[11px] font-bold text-red-300 hover:text-red-200 hover:bg-red-500/10 hover:border-red-500/20 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <Trash2 className="h-3 w-3" />
                Trash
              </button>
            </div>
          </div>

          {showIssuePanel ? (
            <div className="mt-3 space-y-3 rounded-2xl border border-outline bg-surface-container-low p-3.5">
              {visibleIssues.length ? (
                <ul className="space-y-2">
                  {visibleIssues.map((issue) => (
                    <li key={issue.id} className={cn("text-sm leading-relaxed", issueTone(issue.level))}>
                      {issue.line ? `Line ${issue.line}: ` : ""}
                      {issue.message}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-emerald-200">Ready for TTS. No blocking issues or cleanup suggestions.</p>
              )}
              {infoIssues.length ? (
                <div className="border-t border-outline pt-3">
                  {infoIssues.map((issue) => (
                    <p key={issue.id} className="text-xs text-secondary/70">
                      {issue.message}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
