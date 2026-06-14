import {
  AlertTriangle,
  Cloud,
  Cpu,
  Download,
  ExternalLink,
  FileAudio,
  FolderOpen,
  Mic,
  Pause,
  Play,
  RefreshCw,
  Settings2,
  Share2,
  Trash2,
} from "lucide-react";
import {
  resolveProjectVoiceSettings,
  selectedVoiceProfileLabel,
} from "../../lib/voiceSettings";
import { ProgressBar } from "../../components/ProgressBar";
import { AudioPlayer } from "../../components/AudioPlayer";
import { isActiveRequestState } from "../../lib/requestState";
import type { UseScriptWorkbenchResult } from "../script-workbench/useScriptWorkbench";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <p className="voice-panel-section-title">{children}</p>;
}

export function VoiceAudioPanel({
  workbench,
  audioOutOfDate,
  audioOutOfDateReason,
  audioSectionRef,
}: {
  workbench: UseScriptWorkbenchResult;
  audioOutOfDate: boolean;
  audioOutOfDateReason?: string;
  audioSectionRef?: React.RefObject<HTMLDivElement>;
}) {
  const voiceSettings = resolveProjectVoiceSettings(workbench.project);
  const selectedProfileLabel = selectedVoiceProfileLabel(workbench.project);
  const selectedProfileId = workbench.project?.artifact?.voice_reference?.voice_profile_id || "";
  const activeAudioRequestState = isActiveRequestState(workbench.audioRequestState)
    ? workbench.audioRequestState
    : null;

  const needsVoiceProfile =
    workbench.selectedEngine === "local_mlx" &&
    (!selectedProfileId ||
      workbench.project?.artifact?.voice_reference?.source !== "voice_profile");

  const studioReturnPath = workbench.project?.script
    ? `/studio/${workbench.project.session.session_id}/${workbench.project.script.script_id}`
    : "";
  const voiceLibraryPath = workbench.project?.script
    ? `/voice-studio/${workbench.project.session.session_id}/${workbench.project.script.script_id}?returnTo=${encodeURIComponent(studioReturnPath)}`
    : "/voice-studio";

  const hasAudio = Boolean(workbench.audioSrc);

  return (
    <div className="flex flex-col h-full w-full overflow-y-auto mac-scrollbar">

      {/* ── Voice Section ─────────────────────────────────── */}
      <div className="voice-panel-section">
        <SectionTitle>Voice</SectionTitle>

        {/* Voice summary card */}
        <div className="rounded-xl border border-outline bg-surface-container-low p-3 mb-2.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent-amber/30 bg-accent-amber/10 shrink-0">
              {workbench.selectedEngine === "local_mlx" ? (
                <Cpu className="h-4 w-4 text-accent-amber" />
              ) : (
                <Cloud className="h-4 w-4 text-accent-amber" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-semibold text-primary truncate">
                {selectedProfileLabel || "No voice selected"}
              </p>
              <p className="text-[11px] text-secondary/70 truncate mt-0.5">
                {workbench.selectedEngine === "local_mlx"
                  ? `Local MLX${voiceSettings.language ? ` · ${voiceSettings.language}` : ""}${voiceSettings.speed ? ` · ${voiceSettings.speed}x` : ""}`
                  : workbench.cloudProvider}
              </p>
            </div>
            <button
              type="button"
              onClick={() => workbench.navigate(voiceLibraryPath)}
              className="inline-flex items-center gap-1 text-[11px] font-bold text-accent-amber hover:text-primary transition-colors cursor-pointer shrink-0"
              title="Configure voice in Voice Studio"
            >
              <Settings2 className="h-3.5 w-3.5" />
              Configure
            </button>
          </div>

          {needsVoiceProfile && (
            <p className="mt-2 text-[10px] text-amber-600/80 dark:text-amber-400/80 font-medium">
              Select a voice profile for Local MLX rendering.
            </p>
          )}
        </div>

        {workbench.voiceSelectionError && (
          <p className="mt-2 text-[10px] text-red-400 font-medium">{workbench.voiceSelectionError}</p>
        )}
      </div>

      {/* Voice preview handoff */}
      <div className="voice-panel-section">
        <SectionTitle>Preview</SectionTitle>
        <p className="text-[11px] leading-relaxed text-secondary/70">
          Open Voice Studio to render a short preview for the current voice settings.
        </p>
        <button
          type="button"
          onClick={() => workbench.navigate(voiceLibraryPath)}
          className="mt-2 inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-lg border border-outline bg-surface-container-low text-[11px] font-bold text-primary hover:bg-primary/8 transition-all cursor-pointer"
        >
          <Mic className="h-3 w-3" />
          Preview in Voice Studio
        </button>
      </div>

      {/* ── Generated Audio Section ────────────────────────── */}
      <div className="voice-panel-section" ref={audioSectionRef}>
        <div className="flex items-center justify-between mb-2.5">
          <SectionTitle>Generated Audio</SectionTitle>
          {hasAudio && audioOutOfDate && (
            <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wide text-amber-600 dark:text-amber-400 border border-amber-500/25 bg-amber-500/8 rounded-full px-2 py-0.5">
              <AlertTriangle className="w-2.5 h-2.5" />
              Out of date
            </span>
          )}
        </div>

        {/* Render progress */}
        {!workbench.audioError && activeAudioRequestState && (
          <div className="mb-3 rounded-xl border border-outline bg-surface/30 p-3 text-xs space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-primary truncate">
                {`${Math.round(activeAudioRequestState.progress_percent)}% · ${activeAudioRequestState.message}`}
              </span>
              {workbench.generating && activeAudioRequestState.phase === "running" && (
                <button
                  type="button"
                  onClick={() => void workbench.handleCancelAudio()}
                  className="rounded-lg border border-outline bg-surface-container-low px-2 py-0.5 text-[10px] font-bold text-primary hover:bg-primary/5 transition-all cursor-pointer shrink-0"
                >
                  Cancel
                </button>
              )}
            </div>
            <ProgressBar value={activeAudioRequestState.progress_percent} />
          </div>
        )}

        {/* Out-of-date notice */}
        {hasAudio && audioOutOfDate && (
          <div className="mb-3 rounded-xl border border-amber-500/20 bg-amber-500/6 px-3 py-2.5 text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
            {audioOutOfDateReason || "This audio was generated before the latest script or voice changes."}
          </div>
        )}

        {/* Audio error */}
        {workbench.audioError && (
          <div className="mb-3 rounded-xl border border-red-500/20 bg-red-500/6 px-3 py-2.5 text-xs text-red-400 leading-relaxed">
            {workbench.audioError}
          </div>
        )}

        {workbench.pollWarning && (
          <div className="mb-3 rounded-xl border border-accent-amber/20 bg-accent-amber/5 px-3 py-2 text-xs text-accent-amber">
            {workbench.pollWarning}
          </div>
        )}

        {hasAudio ? (
          <div className="flex flex-col gap-2.5">
            {/* Player */}
            <div className="rounded-xl border border-outline bg-surface/10 p-3">
              <div className="flex items-center justify-between gap-2 mb-2">
                <p className="truncate text-[11px] font-semibold text-primary">{workbench.outputFilename}</p>
                <button
                  type="button"
                  onClick={() => void workbench.handleRevealInFinder()}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-outline bg-surface-container-low text-secondary hover:text-primary hover:bg-primary/8 transition-all shrink-0 cursor-pointer"
                  title="Reveal in Finder"
                >
                  <FolderOpen className="h-3 w-3" />
                </button>
              </div>
              <AudioPlayer
                ref={workbench.audioRef}
                src={workbench.audioSrc}
                onError={workbench.handleAudioLoadError}
              />
            </div>

            {/* Audio actions */}
            <div className="grid grid-cols-2 gap-1.5">
              <button
                type="button"
                onClick={() => void workbench.handlePreviewAudio()}
                className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-outline bg-surface-container-low text-[11px] font-bold text-primary hover:bg-primary/8 transition-all cursor-pointer"
              >
                {workbench.isAudioPlaying ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                {workbench.isAudioPlaying ? "Pause" : "Play"}
              </button>
              <button
                type="button"
                onClick={workbench.handleDownloadAudio}
                className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-outline bg-surface-container-low text-[11px] font-bold text-primary hover:bg-primary/8 transition-all cursor-pointer"
              >
                <Download className="h-3 w-3" />
                Download
              </button>
              <button
                type="button"
                onClick={() => void workbench.handleShareAudio()}
                className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-outline bg-surface-container-low text-[11px] font-bold text-primary hover:bg-primary/8 transition-all cursor-pointer"
              >
                <Share2 className="h-3 w-3" />
                Share
              </button>
              <button
                type="button"
                onClick={() => void workbench.handleDeleteAudio()}
                className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-red-500/20 bg-red-500/8 text-[11px] font-bold text-red-400 hover:bg-red-500/15 transition-all cursor-pointer"
              >
                <Trash2 className="h-3 w-3" />
                Delete
              </button>
            </div>

            {/* Regenerate secondary action */}
            {audioOutOfDate && (
              <button
                type="button"
                onClick={workbench.handleGenerateAudio}
                disabled={workbench.generating || !workbench.scriptCheck.canRender}
                className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-lg border border-accent-amber/25 bg-accent-amber/8 text-[11px] font-bold text-accent-amber hover:bg-accent-amber/15 transition-all cursor-pointer disabled:opacity-40"
              >
                <RefreshCw className="h-3 w-3" />
                Update Audio
              </button>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-outline bg-surface/10 py-7 px-4 text-center">
            {workbench.generating ? (
              <>
                <span className="mb-2 inline-block h-6 w-6 rounded-full border-2 border-accent-amber/20 border-t-accent-amber animate-spin" />
                <p className="text-xs font-semibold text-primary">Generating…</p>
                <p className="mt-1 text-[10px] text-secondary/60">
                  {activeAudioRequestState?.message || "Processing…"}
                </p>
              </>
            ) : (
              <>
                <FileAudio className="mb-2 h-6 w-6 text-accent-amber/50" />
                <p className="text-xs font-semibold text-primary">No audio yet</p>
                <p className="mt-1 text-[10px] leading-relaxed text-secondary/60">
                  Use "Generate Audio" to create the final podcast.
                </p>
              </>
            )}
          </div>
        )}

        {workbench.audioMessage && (
          <p className="mt-2 text-[10px] text-accent-amber leading-relaxed">{workbench.audioMessage}</p>
        )}
      </div>

      {/* ── Export Section ─────────────────────────────────── */}
      <div className="voice-panel-section">
        <SectionTitle>Export</SectionTitle>

        {hasAudio ? (
          <div className="space-y-2">
            {audioOutOfDate && (
              <p className="text-[10px] text-amber-600 dark:text-amber-400 leading-relaxed">
                Audio is out of date. You can still export the current version.
              </p>
            )}
            <button
              type="button"
              onClick={workbench.handleDownloadAudio}
              className="inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-lg border border-outline bg-surface-container-low text-[11px] font-bold text-primary hover:bg-primary/8 transition-all cursor-pointer"
            >
              <Download className="h-3 w-3" />
              Export Audio File
            </button>
          </div>
        ) : (
          <p className="text-[11px] text-secondary/50">Generate audio to enable export.</p>
        )}
      </div>

      {/* ── Manage voices link ──────────────────────────────── */}
      <div className="voice-panel-section">
        <button
          type="button"
          onClick={() => workbench.navigate("/voice-studio")}
          className="flex w-full items-center justify-between gap-2 rounded-lg border border-outline px-3 py-2.5 text-xs font-medium text-secondary hover:text-primary hover:bg-primary/5 transition-colors cursor-pointer"
        >
          <span className="flex items-center gap-2">
            <Mic className="h-3.5 w-3.5 text-accent-amber" />
            Manage Voice Studio
          </span>
          <ExternalLink className="h-3 w-3 text-secondary/40" />
        </button>
      </div>
    </div>
  );
}
