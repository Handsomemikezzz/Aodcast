import { Bold, Italic, Link2, List, Quote, RefreshCw, RotateCcw, Sparkles, Trash2, Heading1, Heading2, Heading3 } from "lucide-react";
import { cn } from "../../lib/utils";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";
import { prefixLines, wrapSelection } from "./workbenchUtils";

function ScriptSnapshotCards({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  return (
    <div className="rounded-[24px] border border-outline bg-[rgba(27,27,30,0.88)] p-4 shadow-[0_18px_44px_rgba(0,0,0,0.24)]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-primary">Script Snapshots</p>
          <p className="mt-1 text-xs text-secondary">Switch between generated snapshots for this interview.</p>
        </div>
        <span className="rounded-full border border-outline bg-surface-container-low px-2.5 py-1 text-[11px] text-secondary">
          {workbench.scriptSnapshots.length}
        </span>
      </div>
      <div className="space-y-2">
        {workbench.scriptSnapshots.map((snapshot) => {
          const active = snapshot.script_id === workbench.project?.script?.script_id;
          return (
            <button
              key={snapshot.script_id}
              type="button"
            onClick={() =>
              workbench.runWithUnsavedCheck(async () => {
                if (active || !workbench.project?.session.session_id) return;
                workbench.navigate(`/script/${workbench.project.session.session_id}/${snapshot.script_id}`);
              })
            }
              disabled={active}
              className={cn(
                "flex w-full items-start justify-between gap-3 rounded-2xl border px-3 py-3 text-left transition-colors",
                active
                  ? "border-accent-amber/40 bg-accent-amber/10"
                  : "border-outline bg-surface-container-low hover:border-accent-amber/25 hover:bg-surface-container",
              )}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-primary">{snapshot.name || "Untitled snapshot"}</p>
                <p className="mt-1 text-xs text-secondary">{new Date(snapshot.updated_at).toLocaleString()}</p>
              </div>
              {active ? (
                <span className="rounded-full bg-accent-amber/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-amber">
                  Current
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ScriptRevisionCards({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  return (
    <div className="rounded-[24px] border border-outline bg-[rgba(27,27,30,0.88)] p-4 shadow-[0_18px_44px_rgba(0,0,0,0.24)]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-primary">Revision History</p>
          <p className="mt-1 text-xs text-secondary">Restore a saved point inside this snapshot.</p>
        </div>
        <span className="rounded-full border border-outline bg-surface-container-low px-2.5 py-1 text-[11px] text-secondary">
          {workbench.revisions.length}
        </span>
      </div>
      <div className="max-h-[320px] space-y-2 overflow-y-auto pr-1">
        {workbench.revisions.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-outline bg-surface-container-low px-4 py-6 text-center text-xs text-secondary">
            No revisions yet.
          </div>
        ) : (
          workbench.revisions
            .slice()
            .sort((left, right) => right.created_at.localeCompare(left.created_at))
            .map((revision) => {
              const isBusy = workbench.busyAction === revision.revision_id;
              return (
                <div key={revision.revision_id} className="rounded-2xl border border-outline bg-surface-container-low px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-primary">{revision.label || revision.kind || "Revision"}</p>
                      <p className="mt-1 text-xs text-secondary">{new Date(revision.created_at).toLocaleString()}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        workbench.runWithUnsavedCheck(async () => {
                          workbench.setDialogState({ kind: "rollback", revisionId: revision.revision_id });
                        })
                      }
                      disabled={isBusy || workbench.isScriptDeleted || workbench.isSessionDeleted}
                      className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-[12px] font-medium text-secondary transition-colors hover:bg-surface-container-high hover:text-primary disabled:opacity-50"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      Roll back
                    </button>
                  </div>
                  <p className="mt-2 line-clamp-3 whitespace-pre-wrap break-words text-xs leading-6 text-secondary">
                    {revision.content || " "}
                  </p>
                </div>
              );
            })
        )}
      </div>
    </div>
  );
}

export function ScriptEditorPane({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  return (
    <section className="flex min-w-0 min-h-0 flex-col gap-5 overflow-hidden">
      <div className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] shadow-[0_22px_60px_rgba(0,0,0,0.3)] overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline px-4 py-3 lg:px-5">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
            onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "# ", "Heading 1"))}
            className={workbench.toolbarButtonClass}
          >
            <Heading1 className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "## ", "Heading 2"))}
            className={workbench.toolbarButtonClass}
          >
            <Heading2 className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "### ", "Heading 3"))}
            className={workbench.toolbarButtonClass}
          >
            <Heading3 className="h-4 w-4" />
          </button>
            <div className="mx-1 hidden h-6 w-px bg-outline lg:block" />
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => wrapSelection(value, start, end, "**", "**", "bold text"))}
              className={workbench.toolbarButtonClass}
            >
              <Bold className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => wrapSelection(value, start, end, "*", "*", "italic text"))}
              className={workbench.toolbarButtonClass}
            >
              <Italic className="h-4 w-4" />
            </button>
            <div className="mx-1 hidden h-6 w-px bg-outline lg:block" />
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "- ", "List item"))}
              className={workbench.toolbarButtonClass}
            >
              <List className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "> ", "Quote"))}
              className={workbench.toolbarButtonClass}
            >
              <Quote className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => wrapSelection(value, start, end, "[", "](https://)", "link text"))}
              className={workbench.toolbarButtonClass}
            >
              <Link2 className="h-4 w-4" />
            </button>
          </div>
          <div className="flex items-center gap-2 text-[12px] text-secondary">
            <Sparkles className="h-4 w-4 text-accent-amber" />
            Basic markdown formatting
          </div>
        </div>

        <div className="px-4 pb-4 pt-3 lg:px-5 lg:pb-5">
          <textarea
            ref={workbench.textareaRef}
            value={workbench.script}
            onChange={(event) => workbench.setScript(event.target.value)}
            disabled={workbench.isScriptDeleted || workbench.isSessionDeleted}
            spellCheck={false}
            placeholder="Write or refine your podcast script here."
            className="min-h-[520px] w-full resize-none rounded-[22px] border border-outline bg-[radial-gradient(circle_at_top,rgba(227,171,73,0.06),transparent_28%),rgba(17,17,20,0.92)] px-5 py-5 text-[15px] leading-8 text-primary outline-none transition-colors placeholder:text-outline/60 focus:border-accent-amber/30 disabled:opacity-55"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-outline px-4 py-3 text-[12px] text-secondary lg:px-5">
          <div className="flex flex-wrap items-center gap-3">
            <span>{workbench.wordCount} words</span>
            <span>{workbench.estMinutes} spoken runtime</span>
            {workbench.isDirty ? <span className="font-medium text-accent-amber">Unsaved edits</span> : null}
          </div>
          <div className="flex items-center gap-2">
            {workbench.editorRequestState?.phase === "running" ? <span>{workbench.editorRequestState.message}</span> : null}
            <button
              type="button"
              onClick={() =>
                workbench.runWithUnsavedCheck(async () => {
                  await workbench.reload();
                })
              }
              className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-[12px] font-medium text-secondary transition-colors hover:bg-surface-container hover:text-primary"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => workbench.setDialogState({ kind: "delete-script" })}
              disabled={workbench.isScriptDeleted || workbench.isSessionDeleted || workbench.busyAction === "delete-script"}
              className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-[12px] font-medium text-secondary transition-colors hover:bg-surface-container hover:text-primary disabled:opacity-50"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Trash
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <ScriptSnapshotCards workbench={workbench} />
        <ScriptRevisionCards workbench={workbench} />
      </div>
    </section>
  );
}
