import { useEffect, useState } from "react";
import { Download, FileText, FolderOpen, Loader2, Play, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { AudioPlayer } from "../../components/AudioPlayer";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { OverflowMenu } from "../../components/OverflowMenu";
import { ProgressBar } from "../../components/ProgressBar";
import { cn } from "../../lib/utils";
import { episodeStatusTone, type EpisodeProductStatus } from "../../lib/episodeStatus";
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

  const statusDetail = workbench.generating
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
            : `Preview plays the ${previewLabel.toLowerCase()} with the selected voice.`;
  const secondaryButtonClass =
    "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-primary transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 disabled:cursor-not-allowed disabled:opacity-40";
  const primaryButtonClass =
    "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-primary px-3.5 text-[13px] font-semibold text-background transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/60 disabled:cursor-not-allowed disabled:opacity-35";

  return (
    <>
    <footer className="shrink-0 border-t border-outline bg-surface-container-low px-4 py-2.5">
      <div className="flex flex-col gap-2.5 xl:flex-row xl:items-center">
        <div className={cn("min-w-0", hasAudio || hasPreview ? "xl:w-[220px]" : "xl:max-w-[50%]")} aria-live="polite">
          <p className={cn("flex items-center gap-1.5 text-[13px] font-semibold", episodeStatusTone(status.kind))}>
            {workbench.generating || workbench.previewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {isCancelling ? "Cancelling render" : workbench.previewing ? "Rendering preview" : status.label}
          </p>
          <p className="mt-0.5 truncate text-[12px] text-secondary" title={statusDetail}>{statusDetail}</p>
        </div>

        <div className="min-w-0 flex-1">
          {(hasAudio || hasPreview) ? (
            <div className="flex min-w-0 items-center gap-2">
              {hasAudio && hasPreview ? (
                <div className="flex shrink-0 rounded-lg border border-outline p-0.5" role="group" aria-label="Track">
                  {(["episode", "preview"] as const).map((track) => (
                    <button
                      key={track}
                      type="button"
                      onClick={() => setActiveTrack(track)}
                      aria-pressed={activeTrack === track}
                      className={cn(
                        "h-7 rounded-md px-2.5 text-[12px] font-medium transition-colors",
                        activeTrack === track ? "bg-primary/[0.07] text-primary" : "text-secondary hover:text-primary",
                      )}
                    >
                      {track === "episode" ? "Episode" : "Preview"}
                    </button>
                  ))}
                </div>
              ) : null}
              <div className="min-w-0 flex-1">
                {activeTrack === "preview" && hasPreview ? (
                  <AudioPlayer ref={workbench.previewAudioRef} src={workbench.previewSrc} />
                ) : hasAudio ? (
                  <AudioPlayer
                    ref={workbench.audioRef}
                    src={workbench.audioSrc}
                    onError={workbench.handleAudioLoadError}
                   
                  />
                ) : null}
              </div>
            </div>
          ) : null}
          {activeRequest && (workbench.generating || workbench.previewing) ? (
            <div className="mt-2"><ProgressBar value={activeRequest.progress_percent} /></div>
          ) : null}
          {workbench.previewError || (workbench.audioError && !generationFailed) ? (
            <p className="mt-1 text-[12px] text-red-700 dark:text-red-300" role="alert">
              {workbench.previewError || workbench.audioError}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
          <button
            type="button"
            onClick={workbench.previewing ? () => void workbench.handleCancelPreview() : onPreview}
            disabled={!workbench.previewing && !canPreview}
            title={!canPreview ? "Fix the items under “Before generating” first." : `Preview the ${previewLabel.toLowerCase()}`}
            className={secondaryButtonClass}
          >
            {workbench.previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {workbench.previewing ? "Cancel preview" : "Preview"}
          </button>

          {hasAudio ? (
            <button
              type="button"
              disabled={workbench.exportingMp3}
              onClick={() => void workbench.handleExportMp3()}
              title="Export MP3"
              className={secondaryButtonClass}
            >
              {workbench.exportingMp3 ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Export
            </button>
          ) : null}

          {workbench.generating ? (
            <button
              type="button"
              onClick={() => void workbench.handleCancelAudio()}
              disabled={isCancelling}
              className={cn(secondaryButtonClass, "border border-outline")}
            >
              {isCancelling ? "Cancelling…" : "Cancel render"}
            </button>
          ) : sourceOutOfDate ? (
            <button type="button" onClick={onReviewSource} className={primaryButtonClass}>
              <FileText className="h-4 w-4" />
              Review source
            </button>
          ) : showGenerate ? (
            <button
              type="button"
              onClick={workbench.handleGenerateAudio}
              disabled={!readiness.ready || workbench.previewing}
              title={!readiness.ready ? "Fix the items under “Before generating” first." : undefined}
              className={primaryButtonClass}
            >
              {audioOutOfDate ? <RefreshCw className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
              {audioOutOfDate ? "Update audio" : "Generate audio"}
            </button>
          ) : null}

          {hasAudio ? (
            <OverflowMenu
              label="More audio actions"
              placement="above"
              items={[
                { label: "Reveal in Finder", icon: FolderOpen, onSelect: () => void workbench.handleRevealInFinder() },
                { label: "Delete audio", icon: Trash2, danger: true, onSelect: () => setDeleteConfirmOpen(true) },
              ]}
            />
          ) : null}
        </div>
      </div>
      {workbench.audioMessage ? <p className="mt-1.5 text-[12px] text-secondary">{workbench.audioMessage}</p> : null}
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
