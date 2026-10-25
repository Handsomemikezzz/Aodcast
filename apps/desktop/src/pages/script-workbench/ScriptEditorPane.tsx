import { useState } from "react";
import { AlertCircle, ChevronDown, Loader2, Wand2 } from "lucide-react";
import { cn } from "../../lib/utils";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";
import type { ScriptIssue } from "./spokenScriptTypes";

function issueTone(level: ScriptIssue["level"]): string {
  if (level === "blocking") return "text-red-700 dark:text-red-300";
  if (level === "warning") return "text-amber-700 dark:text-amber-200";
  return "text-secondary";
}

function statusTone(workbench: UseScriptWorkbenchResult): string {
  if (workbench.scriptCheck.blockingCount > 0) return "text-red-700 dark:text-red-300";
  if (workbench.scriptCheck.warningCount > 0) return "text-amber-700 dark:text-amber-200";
  return "text-emerald-700 dark:text-emerald-300";
}

function SaveState({
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
      <span className="inline-flex items-center gap-1 text-red-700 dark:text-red-300">
        <AlertCircle className="h-3 w-3" />
        Save failed
        <button type="button" onClick={onRetry} className="underline underline-offset-2 hover:no-underline">
          Retry
        </button>
      </span>
    );
  }
  if (saving) {
    return (
      <span className="inline-flex items-center gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        Saving…
      </span>
    );
  }
  return <span>{isDirty ? "Unsaved changes" : "Saved"}</span>;
}

export function ScriptEditorPane({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  const [issuesExpanded, setIssuesExpanded] = useState(false);

  const visibleIssues = workbench.scriptCheck.issues.filter((issue) => issue.level !== "info");
  const infoIssues = workbench.scriptCheck.issues.filter((issue) => issue.level === "info");
  const showIssuePanel = issuesExpanded && workbench.scriptCheck.issues.length > 0;
  const locked = workbench.isScriptDeleted || workbench.isSessionDeleted;

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col">
      <textarea
        ref={workbench.textareaRef}
        value={workbench.script}
        onChange={(event) => workbench.setScript(event.target.value)}
        disabled={locked}
        spellCheck={false}
        placeholder="Write the narration for this episode."
        aria-label="Episode script"
        className="min-h-0 flex-1 w-full resize-none bg-transparent px-[max(1.5rem,calc((100%-44rem)/2))] py-8 text-[16px] leading-[2rem] text-primary outline-none placeholder:text-secondary/50 disabled:opacity-40 mac-scrollbar"
      />

      {showIssuePanel ? (
        <div className="mx-4 mb-2 max-h-48 shrink-0 space-y-2 overflow-y-auto rounded-xl border border-outline bg-surface-container-low p-3 mac-scrollbar">
          {visibleIssues.length ? (
            <ul className="space-y-1.5">
              {visibleIssues.map((issue) => (
                <li key={issue.id} className={cn("text-[13px] leading-relaxed", issueTone(issue.level))}>
                  {issue.line ? `Line ${issue.line}: ` : ""}
                  {issue.message}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-emerald-700 dark:text-emerald-300">Ready for speech. Nothing to fix.</p>
          )}
          {infoIssues.length ? (
            <div className="border-t border-outline pt-2">
              {infoIssues.map((issue) => (
                <p key={issue.id} className="text-xs text-secondary">
                  {issue.message}
                </p>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="flex h-10 shrink-0 items-center gap-3 border-t border-outline px-4 text-[12px] text-secondary">
        <button
          type="button"
          onClick={() => setIssuesExpanded((expanded) => !expanded)}
          aria-expanded={issuesExpanded}
          className={cn(
            "inline-flex items-center gap-1 rounded-md font-medium hover:underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50",
            statusTone(workbench),
          )}
        >
          {workbench.scriptCheck.statusLabel}
          <ChevronDown className={cn("h-3 w-3 transition-transform", issuesExpanded && "rotate-180")} />
        </button>
        <span className="tabular-nums">
          {workbench.wordCount} words · {workbench.estMinutes} spoken
        </span>
        <SaveState
          saving={workbench.saving}
          isDirty={workbench.isDirty}
          editorError={workbench.editorError}
          onRetry={() => void workbench.handleSave()}
        />
        <div className="flex-1" />
        {workbench.editorRequestState?.phase === "running" ? (
          <span className="animate-pulse">{workbench.editorRequestState.message}</span>
        ) : null}
        {workbench.scriptCheck.hasCleanableIssues ? (
          <button
            type="button"
            onClick={workbench.handleOpenCleanupPreview}
            disabled={locked}
            className="inline-flex h-7 items-center gap-1 rounded-md px-2 font-medium text-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <Wand2 className="h-3.5 w-3.5" />
            Clean up
          </button>
        ) : null}
      </div>
    </section>
  );
}
