import { Bold, Italic, Link2, List, Quote, RefreshCw, Sparkles, Trash2, Heading1, Heading2, Heading3 } from "lucide-react";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";
import { prefixLines, wrapSelection } from "./workbenchUtils";

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
    </section>
  );
}
