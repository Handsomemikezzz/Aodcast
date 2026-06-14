import { useState } from "react";
import { ChevronDown, RefreshCw, Sparkles, Trash2, Wand2 } from "lucide-react";
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

export function ScriptEditorPane({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  const [editorMode, setEditorMode] = useState<EditorDisplayMode>("script");
  const [issuesExpanded, setIssuesExpanded] = useState(false);

  const visibleIssues = workbench.scriptCheck.issues.filter((issue) => issue.level !== "info");
  const infoIssues = workbench.scriptCheck.issues.filter((issue) => issue.level === "info");
  const showIssuePanel = issuesExpanded && workbench.scriptCheck.issues.length > 0;

  return (
    <section className="flex min-w-0 min-h-0 flex-col gap-5 overflow-hidden">
      <div className="rounded-[32px] border border-white/5 bg-[rgba(27,27,30,0.65)] backdrop-blur-md shadow-[0_20px_50px_rgba(0,0,0,0.4)] overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.04] px-5 py-4">
          <div className="inline-flex rounded-2xl border border-white/5 bg-[rgba(15,15,17,0.55)] p-1">
            <button
              type="button"
              onClick={() => setEditorMode("script")}
              className={cn(
                "rounded-xl px-4 py-2 text-xs font-bold transition-all cursor-pointer",
                editorMode === "script"
                  ? "bg-accent-amber/15 text-accent-amber shadow-[0_0_16px_rgba(242,191,87,0.08)]"
                  : "text-secondary hover:text-primary",
              )}
            >
              Script
            </button>
            <button
              type="button"
              onClick={() => setEditorMode("plain")}
              className={cn(
                "rounded-xl px-4 py-2 text-xs font-bold transition-all cursor-pointer",
                editorMode === "plain"
                  ? "bg-white/10 text-primary"
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

        <div className="px-5 pb-5 pt-4">
          <textarea
            ref={workbench.textareaRef}
            value={workbench.script}
            onChange={(event) => workbench.setScript(event.target.value)}
            disabled={workbench.isScriptDeleted || workbench.isSessionDeleted}
            spellCheck={false}
            placeholder="Write the exact narration you want spoken in the final audio."
            className={cn(
              "min-h-[520px] w-full resize-none rounded-[24px] border border-white/5 bg-[rgba(15,15,17,0.6)] px-6 py-6 text-primary outline-none transition-all placeholder:text-secondary/30 focus:border-accent-amber/30 focus:bg-background focus:shadow-[0_0_24px_rgba(242,191,87,0.03)] disabled:opacity-40",
              editorMode === "script"
                ? "text-[17px] leading-[2.15rem] tracking-[0.01em]"
                : "text-[15px] leading-[2rem] font-mono",
            )}
          />
        </div>

        <div className="border-t border-white/[0.04] px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-secondary/80 font-medium">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => setIssuesExpanded((expanded) => !expanded)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 font-bold transition-all cursor-pointer",
                  workbench.scriptCheck.blockingCount > 0
                    ? "border-red-500/20 bg-red-500/10 text-red-200 hover:bg-red-500/15"
                    : workbench.scriptCheck.warningCount > 0
                      ? "border-amber-500/20 bg-amber-500/10 text-amber-100 hover:bg-amber-500/15"
                      : "border-emerald-500/20 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/15",
                )}
              >
                <span className={statusTone(workbench)}>{workbench.scriptCheck.statusLabel}</span>
                <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", issuesExpanded && "rotate-180")} />
              </button>
              <span>{workbench.wordCount} words</span>
              <span className="text-white/10">•</span>
              <span>{workbench.estMinutes} spoken runtime</span>
              {workbench.isDirty ? (
                <>
                  <span className="text-white/10">•</span>
                  <span className="font-semibold text-accent-amber">Unsaved edits</span>
                </>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              {workbench.scriptCheck.hasCleanableIssues ? (
                <button
                  type="button"
                  onClick={workbench.handleOpenCleanupPreview}
                  disabled={workbench.isScriptDeleted || workbench.isSessionDeleted}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-accent-amber/20 bg-accent-amber/10 px-3 py-1.5 text-[11px] font-bold text-accent-amber hover:bg-accent-amber/15 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  Clean all
                </button>
              ) : null}
              {workbench.editorRequestState?.phase === "running" ? (
                <span className="mr-2 text-secondary/60 animate-pulse">{workbench.editorRequestState.message}</span>
              ) : null}
              <button
                type="button"
                onClick={() =>
                  workbench.runWithUnsavedCheck(async () => {
                    await workbench.reload();
                  })
                }
                className="inline-flex items-center gap-1.5 rounded-xl border border-white/5 bg-white/5 px-3 py-1.5 text-[11px] font-bold text-secondary hover:text-primary hover:bg-white/10 hover:border-white/10 active:scale-[0.98] transition-all cursor-pointer"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh
              </button>
              <button
                type="button"
                onClick={() => workbench.setDialogState({ kind: "delete-script" })}
                disabled={workbench.isScriptDeleted || workbench.isSessionDeleted || workbench.busyAction === "delete-script"}
                className="inline-flex items-center gap-1.5 rounded-xl border border-red-500/10 bg-red-500/5 px-3 py-1.5 text-[11px] font-bold text-red-300 hover:text-red-200 hover:bg-red-500/10 hover:border-red-500/20 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Trash
              </button>
            </div>
          </div>

          {showIssuePanel ? (
            <div className="mt-4 space-y-3 rounded-2xl border border-white/5 bg-[rgba(15,15,17,0.45)] p-4">
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
                <div className="border-t border-white/5 pt-3">
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
