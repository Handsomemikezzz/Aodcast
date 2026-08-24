import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Download,
  Ellipsis,
  FileAudio,
  FileText,
  FolderOpen,
  Loader2,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { AudioPlayer } from "../../components/AudioPlayer";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ProgressBar } from "../../components/ProgressBar";
import { cn } from "../../lib/utils";
import type { EpisodeProductStatus } from "../../lib/episodeStatus";
import type { UseScriptWorkbenchResult } from "../script-workbench/useScriptWorkbench";
import type { EpisodeRenderReadiness } from "./studioWorkflow";

type ActiveTrack = "episode" | "preview";

export function EpisodeAudioDock({
  workbench,
  status,
  readiness,
  audioOutOfDate,
  audioOutOfDateReason,
  sourceOutOfDate,
  previewLabel,
  onPreview,
  onReviewSource,
}: {
  workbench: UseScriptWorkbenchResult;
  status: EpisodeProductStatus;
  readiness: EpisodeRenderReadiness;
  audioOutOfDate: boolean;
  audioOutOfDateReason?: string;
  sourceOutOfDate: boolean;
  previewLabel: string;
  onPreview: () => void;
  onReviewSource: () => void;
}) {
  const [activeTrack, setActiveTrack] = useState<ActiveTrack>(workbench.audioSrc ? "episode" : "preview");
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const hasAudio = Boolean(workbench.audioSrc);
  const hasPreview = Boolean(workbench.previewSrc);

  useEffect(() => {
    if (hasPreview) setActiveTrack("preview");
  }, [hasPreview, workbench.previewSrc]);

  useEffect(() => {
    if (!hasPreview && activeTrack === "preview" && hasAudio) setActiveTrack("episode");
  }, [activeTrack, hasAudio, hasPreview]);

  const activeRequest = workbench.generating
    ? workbench.audioRequestState
    : workbench.previewing
      ? workbench.previewRequestState
      : null;
  const isCancelling = workbench.generating && workbench.audioRequestState?.phase === "cancelling";
  const canPreview = readiness.scriptReady
    && readiness.voiceReady
    && readiness.ttsReady
    && !sourceOutOfDate
    && !workbench.generating;
  const showGenerate = !hasAudio || audioOutOfDate;
  const generationFailed = workbench.audioRequestState?.phase === "failed" || Boolean(workbench.audioError);

  return (
    <>
    <footer className="shrink-0 border-t border-outline bg-surface-container-low/95 px-4 py-3 shadow-[0_-10px_30px_rgba(0,0,0,0.06)] backdrop-blur-xl">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
        <div className="flex min-w-[180px] items-center gap-3 xl:w-[210px]">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface-container-high text-accent-amber">
            {workbench.generating || workbench.previewing
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : generationFailed
                ? <AlertTriangle className="h-4 w-4 text-red-500" />
              : audioOutOfDate
                ? <AlertTriangle className="h-4 w-4" />
                : <FileAudio className="h-4 w-4" />}
          </span>
          <div className="min-w-0">
            <p className="text-xs font-bold text-primary">
              {isCancelling ? "Cancelling render" : status.label}
            </p>
            <p className="mt-0.5 truncate text-[10px] text-secondary">
              {workbench.generating
                ? isCancelling
                  ? "Stopping the current render…"
                  : workbench.audioRequestState?.message || "Rendering episode audio…"
                : workbench.previewing
                  ? workbench.previewRequestState?.message || "Rendering preview…"
                  : generationFailed
                    ? workbench.audioError || workbench.audioRequestState?.message || "Generation failed."
                  : audioOutOfDate
                    ? audioOutOfDateReason || "The current audio is from an earlier version."
                    : hasAudio
                      ? workbench.outputFilename
                      : "Preview a passage or generate the full episode."}
            </p>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          {(hasAudio || hasPreview) ? (
            <div className="flex min-w-0 items-center gap-2">
              {hasAudio && hasPreview ? (
                <div className="flex shrink-0 rounded-lg border border-outline bg-background/45 p-0.5">
                  <button
                    type="button"
                    onClick={() => setActiveTrack("episode")}
                    className={cn(
                      "min-h-10 rounded-md px-2.5 text-[10px] font-bold transition-colors",
                      activeTrack === "episode" ? "bg-surface-container-high text-primary" : "text-secondary",
                    )}
                  >
                    Episode
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTrack("preview")}
                    className={cn(
                      "min-h-10 rounded-md px-2.5 text-[10px] font-bold transition-colors",
                      activeTrack === "preview" ? "bg-surface-container-high text-primary" : "text-secondary",
                    )}
                  >
                    Preview
                  </button>
                </div>
              ) : null}
              <div className="min-w-0 flex-1">
                {activeTrack === "preview" && hasPreview ? (
                  <AudioPlayer ref={workbench.previewAudioRef} src={workbench.previewSrc} variant="minimal" />
                ) : hasAudio ? (
                  <AudioPlayer
                    ref={workbench.audioRef}
                    src={workbench.audioSrc}
                    onError={workbench.handleAudioLoadError}
                    variant="minimal"
                  />
                ) : null}
              </div>
            </div>
          ) : (
            <div className="flex min-h-12 items-center rounded-xl border border-dashed border-outline px-4 text-xs text-secondary">
              {previewLabel} will be used for a quick voice check.
            </div>
          )}
          {activeRequest && (workbench.generating || workbench.previewing) ? (
            <div className="mt-2"><ProgressBar value={activeRequest.progress_percent} /></div>
          ) : null}
          {workbench.audioError || workbench.previewError ? (
            <p className="mt-1 text-[10px] text-red-700 dark:text-red-300" role="alert">
              {workbench.previewError || workbench.audioError}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={workbench.previewing ? () => void workbench.handleCancelPreview() : onPreview}
            disabled={!workbench.previewing && !canPreview}
            title={!canPreview ? "Finish the checklist in Voice & Delivery before previewing." : `Preview ${previewLabel.toLowerCase()}`}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container px-4 text-xs font-semibold text-primary transition-colors hover:bg-surface-container-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {workbench.previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {workbench.previewing ? "Cancel preview" : "Preview"}
          </button>

          {workbench.generating ? (
            <button
              type="button"
              onClick={() => void workbench.handleCancelAudio()}
              disabled={isCancelling}
              className="inline-flex h-11 items-center justify-center rounded-xl border border-outline px-4 text-xs font-semibold text-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isCancelling ? "Cancelling…" : "Cancel render"}
            </button>
          ) : sourceOutOfDate ? (
            <button
              type="button"
              onClick={onReviewSource}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-accent-amber px-4 text-xs font-bold text-on-primary shadow-[0_6px_18px_rgba(161,123,67,0.2)] transition-all hover:bg-accent-amber/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/60"
            >
              <FileText className="h-4 w-4" />
              Review Source
            </button>
          ) : showGenerate ? (
            <button
              type="button"
              onClick={workbench.handleGenerateAudio}
              disabled={!readiness.ready || workbench.previewing}
              title={!readiness.ready ? "Finish the checklist in Voice & Delivery before generating." : undefined}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-accent-amber px-4 text-xs font-bold text-on-primary shadow-[0_6px_18px_rgba(161,123,67,0.2)] transition-all hover:bg-accent-amber/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/60 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {audioOutOfDate ? <RefreshCw className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
              {audioOutOfDate ? "Update Audio" : "Generate Audio"}
            </button>
          ) : null}

          {hasAudio ? (
            <button
              type="button"
              disabled={workbench.exportingMp3}
              onClick={() => void workbench.handleExportMp3()}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/5 disabled:opacity-45"
            >
              {workbench.exportingMp3 ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Export
            </button>
          ) : null}

          {hasAudio ? (
            <details className="group relative">
              <summary
                aria-label="More audio actions"
                className="flex h-11 w-11 cursor-pointer list-none items-center justify-center rounded-xl border border-outline text-secondary transition-colors hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 [&::-webkit-details-marker]:hidden"
              >
                <Ellipsis className="h-4 w-4" />
              </summary>
              <div className="absolute bottom-12 right-0 z-40 w-48 rounded-xl border border-outline bg-modal p-1.5 shadow-xl backdrop-blur-xl">
                <button
                  type="button"
                  onClick={() => void workbench.handleRevealInFinder()}
                  className="flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-xs font-medium text-primary hover:bg-primary/5"
                >
                  <FolderOpen className="h-4 w-4" /> Reveal in Finder
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteConfirmOpen(true)}
                  className="flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-xs font-medium text-red-700 hover:bg-red-500/10 dark:text-red-300"
                >
                  <Trash2 className="h-4 w-4" /> Delete audio
                </button>
              </div>
            </details>
          ) : null}
        </div>
      </div>
      {workbench.audioMessage ? <p className="mt-2 text-[10px] text-secondary">{workbench.audioMessage}</p> : null}
    </footer>
    <ConfirmDialog
      open={deleteConfirmOpen}
      title="Delete generated audio?"
      message="The script and voice settings will be kept. You can generate the episode again later."
      onClose={() => setDeleteConfirmOpen(false)}
      actions={[
        { label: "Cancel", onClick: () => setDeleteConfirmOpen(false) },
        {
          label: "Delete audio",
          variant: "danger",
          onClick: () => {
            setDeleteConfirmOpen(false);
            void workbench.handleDeleteAudio();
          },
        },
      ]}
    />
    </>
  );
}
