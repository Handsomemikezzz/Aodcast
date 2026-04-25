import { ChevronDown, Clock3, Cloud, Cpu, Download, FileAudio, FolderOpen, History, Mic, Pause, Play, Settings2, Share2, Wand2 } from "lucide-react";
import { cn } from "../../lib/utils";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";

export function ScriptAudioSidebar({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  return (
    <aside className="flex min-h-0 flex-col gap-4 self-start">
      <div className="rounded-[28px] border border-outline bg-[linear-gradient(180deg,rgba(35,31,24,0.96),rgba(24,24,27,0.96))] p-4 shadow-[0_22px_60px_rgba(0,0,0,0.34)] overflow-hidden">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-primary">Voice Workspace</p>
            <p className="mt-1 text-xs text-secondary">Persona, engine, live stats, and output actions.</p>
          </div>
          <Mic className="h-5 w-5 text-accent-amber" />
        </div>

        <div className="space-y-4">
          <div className="rounded-[22px] border border-outline bg-[rgba(22,22,24,0.88)] p-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Voice Persona</p>
              <button
                type="button"
                onClick={() => workbench.navigate("/settings")}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-accent-amber transition-colors hover:text-primary"
              >
                <Settings2 className="h-3.5 w-3.5" />
                Manage
              </button>
            </div>
            <button
              type="button"
              onClick={() => workbench.navigate("/settings")}
              className="flex w-full items-center justify-between gap-3 rounded-[18px] border border-outline bg-surface-container-low px-3 py-3 text-left transition-colors hover:border-accent-amber/30"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-accent-amber/30 bg-accent-amber/10">
                  <Mic className="h-5 w-5 text-accent-amber" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary">{workbench.ttsConfig?.voice?.trim() || "System Default"}</p>
                  <p className="mt-1 text-xs text-secondary">
                    {workbench.selectedEngine === "local_mlx"
                      ? "Natural local MLX rendering"
                      : `Configured for ${workbench.cloudProvider}`}
                  </p>
                </div>
              </div>
              <ChevronDown className="h-4 w-4 text-secondary" />
            </button>
          </div>

          <div className="rounded-[22px] border border-outline bg-[rgba(22,22,24,0.88)] p-3">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Rendering Engine</p>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
              <button
                type="button"
                onClick={() => workbench.setSelectedEngine("local_mlx")}
                disabled={workbench.localEngineDisabled}
                className={cn(
                  "rounded-[20px] border px-4 py-4 text-left transition-colors",
                  workbench.selectedEngine === "local_mlx"
                    ? "border-accent-amber bg-accent-amber/12 shadow-[0_12px_28px_rgba(215,155,47,0.18)]"
                    : "border-outline bg-surface-container-low hover:border-accent-amber/25",
                  workbench.localEngineDisabled && "cursor-not-allowed opacity-55",
                )}
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-accent-amber/25 bg-accent-amber/10">
                    <Cpu className="h-4 w-4 text-accent-amber" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-primary">Local MLX</p>
                    <p className="mt-1 text-xs text-secondary">
                      {workbench.capability?.available ? "Apple Silicon optimized" : "Unavailable on this machine"}
                    </p>
                  </div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => workbench.setSelectedEngine("cloud")}
                disabled={workbench.cloudEngineDisabled}
                className={cn(
                  "rounded-[20px] border px-4 py-4 text-left transition-colors",
                  workbench.selectedEngine === "cloud"
                    ? "border-accent-amber/40 bg-accent-amber/8 shadow-[0_12px_28px_rgba(215,155,47,0.14)]"
                    : "border-outline bg-surface-container-low hover:border-accent-amber/25",
                  workbench.cloudEngineDisabled && "cursor-not-allowed opacity-55",
                )}
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-outline bg-background">
                    <Cloud className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-primary">Cloud Synthesis</p>
                    <p className="mt-1 text-xs text-secondary">Provider: {workbench.cloudProvider}</p>
                  </div>
                </div>
              </button>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-[22px] border border-outline bg-[rgba(22,22,24,0.88)] p-4">
              <div className="flex items-center gap-2 text-secondary">
                <Clock3 className="h-4 w-4 text-accent-amber" />
                <span className="text-xs uppercase tracking-[0.18em]">Estimated Length</span>
              </div>
              <p className="mt-3 text-[30px] font-headline font-semibold text-primary">{workbench.estMinutes}</p>
            </div>
            <div className="rounded-[22px] border border-outline bg-[rgba(22,22,24,0.88)] p-4">
              <div className="flex items-center gap-2 text-secondary">
                <History className="h-4 w-4 text-accent-amber" />
                <span className="text-xs uppercase tracking-[0.18em]">Word Count</span>
              </div>
              <p className="mt-3 text-[30px] font-headline font-semibold text-primary">{workbench.wordCount}</p>
            </div>
          </div>

          {workbench.audioError ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-3 py-3 text-sm text-red-200">
              {workbench.audioError}
            </div>
          ) : null}
          {workbench.editorError ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-3 py-3 text-sm text-red-200">
              {workbench.editorError}
            </div>
          ) : null}
          {workbench.pollWarning ? (
            <div className="rounded-2xl border border-accent-amber/20 bg-accent-amber/10 px-3 py-3 text-sm text-accent-amber">
              {workbench.pollWarning}
            </div>
          ) : null}
          {workbench.audioMessage ? (
            <div className="rounded-2xl border border-accent-amber/20 bg-accent-amber/10 px-3 py-3 text-sm text-accent-amber">
              {workbench.audioMessage}
            </div>
          ) : null}
          {!workbench.audioError && workbench.audioRequestState && workbench.audioRequestState.phase !== "succeeded" && workbench.audioRequestState.phase !== "failed" ? (
            <div className="rounded-2xl border border-outline bg-background/80 px-3 py-3 text-sm text-secondary">
              <div className="flex items-center justify-between gap-3">
                <span>{`${Math.round(workbench.audioRequestState.progress_percent)}% · ${workbench.audioRequestState.message}`}</span>
                {workbench.generating && workbench.audioRequestState.phase === "running" ? (
                  <button
                    type="button"
                    onClick={() => void workbench.handleCancelAudio()}
                    className="rounded-full border border-outline px-3 py-1 text-[12px] font-medium text-primary transition-colors hover:bg-surface-container"
                  >
                    Cancel
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-4 shadow-[0_22px_60px_rgba(0,0,0,0.3)] overflow-hidden">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-primary">Generated Audio</p>
            <p className="mt-1 text-xs text-secondary">Preview, export, or share the latest render.</p>
          </div>
          <FileAudio className="h-5 w-5 text-accent-amber" />
        </div>

        {workbench.audioSrc ? (
          <div className="flex min-h-0 flex-1 flex-col gap-4">
            <div className="rounded-[22px] border border-outline bg-[radial-gradient(circle_at_center,rgba(227,171,73,0.18),transparent_60%),rgba(17,17,20,0.95)] p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-primary">{workbench.outputFilename}</p>
                  <p className="mt-1 text-xs text-secondary">
                    {workbench.selectedEngine === "local_mlx" ? "Local MLX render" : `Cloud render via ${workbench.cloudProvider}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void workbench.handleRevealInFinder()}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-outline bg-surface-container-low text-secondary transition-colors hover:border-accent-amber/30 hover:text-primary"
                >
                  <FolderOpen className="h-4 w-4" />
                </button>
              </div>

              <div className="mt-4 h-16 rounded-[18px] border border-accent-amber/20 bg-[linear-gradient(90deg,rgba(242,191,87,0.08)_0%,rgba(242,191,87,0.85)_10%,rgba(242,191,87,0.12)_20%,rgba(242,191,87,0.95)_34%,rgba(242,191,87,0.15)_50%,rgba(242,191,87,0.9)_64%,rgba(242,191,87,0.12)_80%,rgba(242,191,87,0.75)_100%)] opacity-80" />

              <audio
                ref={workbench.audioRef}
                controls
                src={workbench.audioSrc}
                className="mt-4 w-full [&::-webkit-media-controls-panel]:bg-background [&::-webkit-media-controls-panel]:border [&::-webkit-media-controls-panel]:border-outline"
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <button
                type="button"
                onClick={() => void workbench.handlePreviewAudio()}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-outline bg-surface-container-low text-sm font-medium text-primary transition-colors hover:border-accent-amber/30 hover:bg-surface-container"
              >
                {workbench.isAudioPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                Preview
              </button>
              <button
                type="button"
                onClick={workbench.handleDownloadAudio}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-outline bg-surface-container-low text-sm font-medium text-primary transition-colors hover:border-accent-amber/30 hover:bg-surface-container"
              >
                <Download className="h-4 w-4" />
                Download
              </button>
              <button
                type="button"
                onClick={() => void workbench.handleShareAudio()}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-outline bg-surface-container-low text-sm font-medium text-primary transition-colors hover:border-accent-amber/30 hover:bg-surface-container"
              >
                <Share2 className="h-4 w-4" />
                Share
              </button>
            </div>
          </div>
        ) : (
          <div className="flex min-h-[280px] flex-1 flex-col items-center justify-center rounded-[22px] border border-dashed border-accent-amber/30 bg-accent-amber/6 px-5 text-center">
            <Wand2 className="mb-3 h-8 w-8 text-accent-amber" />
            <p className="text-sm font-medium text-primary">No audio file yet</p>
            <p className="mt-2 max-w-[280px] text-xs leading-6 text-secondary">
              Select a rendering engine, save your latest edits, and generate audio to unlock preview, download, and sharing actions here.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
