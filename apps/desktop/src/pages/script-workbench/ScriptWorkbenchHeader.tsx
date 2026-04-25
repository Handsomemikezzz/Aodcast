import { Pause, Play, Save, Wand2 } from "lucide-react";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";

export function ScriptWorkbenchHeader({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  return (
    <section className="rounded-[28px] border border-outline bg-[linear-gradient(180deg,rgba(33,33,37,0.96),rgba(25,25,28,0.94))] px-5 py-5 shadow-[0_24px_80px_rgba(0,0,0,0.38)] backdrop-blur-xl lg:px-6">
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
          <button
            type="button"
            onClick={() => void workbench.handlePreviewAudio()}
            disabled={!workbench.audioSrc}
            className="inline-flex h-12 items-center gap-2 rounded-2xl border border-outline bg-surface-container-low px-4 text-sm font-medium text-primary transition-colors hover:border-accent-amber/30 hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-50"
          >
            {workbench.isAudioPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {workbench.isAudioPlaying ? "Pause" : "Preview"}
          </button>
          <button
            type="button"
            onClick={() => void workbench.handleSave()}
            disabled={workbench.saving || !workbench.isDirty || workbench.isScriptDeleted || workbench.isSessionDeleted}
            className="inline-flex h-12 items-center gap-2 rounded-2xl border border-outline bg-surface-container-low px-4 text-sm font-medium text-primary transition-colors hover:border-accent-amber/30 hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {workbench.saving ? "Saving..." : workbench.isDirty ? "Save" : "Saved"}
          </button>
          <button
            type="button"
            onClick={workbench.handleGenerateAudio}
            disabled={
              workbench.generating ||
              workbench.script.trim().length === 0 ||
              (workbench.selectedEngine === "local_mlx" ? workbench.localEngineDisabled : workbench.cloudEngineDisabled)
            }
            className="inline-flex h-12 items-center gap-2 rounded-2xl border border-accent-amber/60 bg-[linear-gradient(180deg,#f2bf57,#d79b2f)] px-5 text-sm font-semibold text-[#231402] shadow-[0_16px_36px_rgba(215,155,47,0.32)] transition-transform hover:-translate-y-0.5 hover:shadow-[0_20px_40px_rgba(215,155,47,0.38)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {workbench.generating ? (
              <span className="inline-flex h-4 w-4 rounded-full border-2 border-black/20 border-t-black animate-spin" />
            ) : (
              <Wand2 className="h-4 w-4" />
            )}
            {workbench.generating ? "Generating..." : "Generate Audio"}
          </button>
        </div>
      </div>
    </section>
  );
}
