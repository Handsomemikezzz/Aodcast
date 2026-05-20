import { Bold, Italic, Link2, List, Quote, RefreshCw, Sparkles, Trash2, Heading1, Heading2, Heading3 } from "lucide-react";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";
import { prefixLines, wrapSelection } from "./workbenchUtils";

export function ScriptEditorPane({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  const pillClass = "rounded-xl border border-white/5 bg-white/5 p-2 text-secondary hover:text-primary hover:bg-white/10 hover:border-white/10 active:scale-[0.95] transition-all cursor-pointer";

  return (
    <section className="flex min-w-0 min-h-0 flex-col gap-5 overflow-hidden">
      <div className="rounded-[32px] border border-white/5 bg-[rgba(27,27,30,0.65)] backdrop-blur-md shadow-[0_20px_50px_rgba(0,0,0,0.4)] overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.04] px-5 py-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "# ", "Heading 1"))}
              className={pillClass}
              title="Heading 1"
            >
              <Heading1 className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "## ", "Heading 2"))}
              className={pillClass}
              title="Heading 2"
            >
              <Heading2 className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "### ", "Heading 3"))}
              className={pillClass}
              title="Heading 3"
            >
              <Heading3 className="h-4 w-4" />
            </button>
            <div className="mx-1.5 hidden h-5 w-px bg-white/10 lg:block" />
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => wrapSelection(value, start, end, "**", "**", "bold text"))}
              className={pillClass}
              title="Bold"
            >
              <Bold className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => wrapSelection(value, start, end, "*", "*", "italic text"))}
              className={pillClass}
              title="Italic"
            >
              <Italic className="h-4 w-4" />
            </button>
            <div className="mx-1.5 hidden h-5 w-px bg-white/10 lg:block" />
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "- ", "List item"))}
              className={pillClass}
              title="Bullet List"
            >
              <List className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => prefixLines(value, start, end, "> ", "Quote"))}
              className={pillClass}
              title="Quote"
            >
              <Quote className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => workbench.applyToolbarAction((value, start, end) => wrapSelection(value, start, end, "[", "](https://)", "link text"))}
              className={pillClass}
              title="Insert Link"
            >
              <Link2 className="h-4 w-4" />
            </button>
          </div>
          <div className="flex items-center gap-2 text-xs text-secondary/80 font-medium select-none">
            <Sparkles className="h-3.5 w-3.5 text-accent-amber" />
            Basic markdown formatting
          </div>
        </div>

        <div className="px-5 pb-5 pt-4">
          <textarea
            ref={workbench.textareaRef}
            value={workbench.script}
            onChange={(event) => workbench.setScript(event.target.value)}
            disabled={workbench.isScriptDeleted || workbench.isSessionDeleted}
            spellCheck={false}
            placeholder="Write or refine your podcast script here."
            className="min-h-[520px] w-full resize-none rounded-[24px] border border-white/5 bg-[rgba(15,15,17,0.6)] px-6 py-6 text-[15px] leading-[2rem] text-primary outline-none transition-all placeholder:text-secondary/30 focus:border-accent-amber/30 focus:bg-background focus:shadow-[0_0_24px_rgba(242,191,87,0.03)] disabled:opacity-40"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.04] px-5 py-4 text-xs text-secondary/80 font-medium">
          <div className="flex flex-wrap items-center gap-3">
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
            {workbench.editorRequestState?.phase === "running" ? <span className="mr-2 text-secondary/60 animate-pulse">{workbench.editorRequestState.message}</span> : null}
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
      </div>
    </section>
  );
}
