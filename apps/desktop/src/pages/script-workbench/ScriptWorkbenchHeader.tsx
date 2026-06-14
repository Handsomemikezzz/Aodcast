import { ArrowLeft, Save } from "lucide-react";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";
import { QuickSettingsPopover } from "../../components/QuickSettingsPopover";

export function ScriptWorkbenchHeader({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  return (
    <section className="rounded-[28px] border border-outline theme-panel-elevated px-5 py-5 shadow-2xl backdrop-blur-xl lg:px-6">
      <button
        type="button"
        onClick={() => workbench.navigate("/script")}
        className="mb-4 inline-flex items-center gap-2 rounded-full border border-outline bg-surface-container-low px-3 py-2 text-xs font-medium text-secondary transition-colors hover:border-accent-amber/30 hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        返回脚本列表
      </button>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="truncate text-[28px] font-headline font-semibold tracking-tight text-primary">
              {workbench.scriptName}
            </h1>
            <span className="rounded-full border border-accent-amber/30 bg-accent-amber/12 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-accent-amber">
              {workbench.sessionStateLabel}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-[13px] text-secondary">
            <span>Updated {workbench.updatedAt ? new Date(workbench.updatedAt).toLocaleString() : "just now"}</span>
            <span className="hidden text-outline lg:inline">•</span>
            <span>{workbench.wordCount} words</span>
            <span className="hidden text-outline lg:inline">•</span>
            <span>{workbench.estMinutes} runtime</span>
          </div>
          {workbench.topic && workbench.scriptName !== workbench.topic ? (
            <p className="mt-2 text-[12px] uppercase tracking-[0.2em] text-secondary">{workbench.topic}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3 lg:justify-end">
          <QuickSettingsPopover onConfigChange={workbench.refreshWorkspace} />
          <button
            type="button"
            onClick={() => void workbench.handleSave()}
            disabled={workbench.saving || !workbench.isDirty || workbench.isScriptDeleted || workbench.isSessionDeleted}
            className="inline-flex h-12 items-center gap-2 rounded-2xl border border-outline bg-surface-container-low px-4 text-sm font-medium text-primary transition-colors hover:border-accent-amber/30 hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {workbench.saving ? "Saving..." : workbench.isDirty ? "Save" : "Saved"}
          </button>
        </div>
      </div>
    </section>
  );
}
