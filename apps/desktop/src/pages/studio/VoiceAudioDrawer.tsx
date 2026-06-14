import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Cloud,
  Cpu,
  Download,
  ExternalLink,
  FileAudio,
  FolderOpen,
  History,
  Mic,
  Pause,
  Play,
  Settings2,
  Share2,
  Trash2,
  Wand2,
} from "lucide-react";
import { cn } from "../../lib/utils";
import {
  filterActiveVoiceProfiles,
  resolveProjectVoiceSettings,
  selectedVoiceProfileLabel,
} from "../../lib/voiceSettings";
import { ProgressBar } from "../../components/ProgressBar";
import { AudioPlayer } from "../../components/AudioPlayer";
import { isActiveRequestState } from "../../lib/requestState";
import type { UseScriptWorkbenchResult } from "../script-workbench/useScriptWorkbench";

export function VoiceAudioDrawer({
  workbench,
  onClose,
  isFocused = true,
  onFocus,
}: {
  workbench: UseScriptWorkbenchResult;
  onClose: () => void;
  isFocused?: boolean;
  onFocus?: () => void;
}) {
  const navigate = useNavigate();
  const [voiceMenuOpen, setVoiceMenuOpen] = useState(false);

  const voiceSettings = resolveProjectVoiceSettings(workbench.project);
  const selectedProfileLabel = selectedVoiceProfileLabel(workbench.project);
  const selectedProfileId = workbench.project?.artifact?.voice_reference?.voice_profile_id || "";
  const profileSource = workbench.project?.artifact?.voice_reference?.profile_source;
  const profileSourceLabel =
    profileSource === "built_in" ? "默认音色" : profileSource === "user_saved" ? "我的音色" : "";
  const activeVoiceProfiles = filterActiveVoiceProfiles(workbench.voiceProfiles);
  const activeAudioRequestState = isActiveRequestState(workbench.audioRequestState)
    ? workbench.audioRequestState
    : null;
  const needsVoiceProfile =
    workbench.selectedEngine === "local_mlx" &&
    (!selectedProfileId ||
      workbench.project?.artifact?.voice_reference?.source !== "voice_profile");
  const generationDisabled =
    workbench.generating ||
    !workbench.scriptCheck.canRender ||
    needsVoiceProfile ||
    (workbench.selectedEngine === "local_mlx"
      ? workbench.localEngineDisabled
      : workbench.cloudEngineDisabled);

  const voiceLibraryPath = workbench.project?.script
    ? `/voice-studio/${workbench.project.session.session_id}/${workbench.project.script.script_id}`
    : "/voice-studio";

  // Preview Mode when not focused
  if (!isFocused) {
    return (
      <div
        onClick={onFocus}
        className="flex flex-col h-full w-full select-none cursor-pointer p-4 justify-between"
      >
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-secondary">
              <Mic className="w-3.5 h-3.5 text-accent-amber" />
              <span>Voice &amp; Audio</span>
            </div>
            {activeAudioRequestState ? (
              <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-accent-amber/10 border border-accent-amber/20 text-accent-amber animate-pulse">
                {Math.round(activeAudioRequestState.progress_percent)}%
              </span>
            ) : workbench.audioSrc ? (
              <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-emerald-500/10 border border-emerald-500/20 text-emerald-300">
                Ready
              </span>
            ) : (
              <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-surface-container-high/60 border border-outline text-secondary">
                Empty
              </span>
            )}
          </div>

          {/* Glimpse Content */}
          <div className="space-y-3 opacity-60">
            {/* Selected Voice Info */}
            <div className="rounded-xl border border-outline bg-surface-container-low p-2.5 flex items-center gap-2.5">
              <Mic className="h-3.5 w-3.5 text-accent-amber shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-primary truncate">
                  {selectedProfileLabel || "未选择音色"}
                </p>
                <p className="text-[10px] text-secondary/70 truncate">
                  {workbench.selectedEngine === "local_mlx" ? "Local MLX" : workbench.cloudProvider}
                </p>
              </div>
            </div>

            {/* Render Progress Events */}
            {activeAudioRequestState && (
              <div className="text-[11px] text-accent-amber">
                <span className="block truncate font-semibold text-[10px]">{activeAudioRequestState.message}</span>
                <div className="mt-1 h-1 w-full bg-surface-container-high rounded-full overflow-hidden">
                  <div
                    className="h-full bg-accent-amber transition-all duration-300"
                    style={{ width: `${activeAudioRequestState.progress_percent}%` }}
                  />
                </div>
              </div>
            )}

            {/* Generated Audio Mini-player */}
            {workbench.audioSrc && (
              <div
                className="rounded-xl border border-outline bg-surface-container-low p-2 flex items-center justify-between gap-2"
                onClick={(e) => e.stopPropagation()}
              >
                <span className="text-[11px] text-secondary truncate flex-1 font-mono">{workbench.outputFilename}</span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    void workbench.handlePreviewAudio();
                  }}
                  className="inline-flex h-7 px-2.5 items-center gap-1 rounded-lg border border-accent-amber/25 bg-accent-amber/10 text-[10px] font-bold text-accent-amber hover:bg-accent-amber/20 active:scale-95 transition-all cursor-pointer"
                >
                  {workbench.isAudioPlaying ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                  {workbench.isAudioPlaying ? "Pause" : "Play"}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Focus Hint */}
        <div className="text-[10px] font-medium text-center text-accent-amber/50 animate-pulse pt-2 border-t border-outline shrink-0">
          Click to configure voice
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full">
      {/* Drawer header */}
      <div className="h-9 shrink-0 flex items-center justify-between px-3 border-b border-outline">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-secondary/70">
          <Mic className="w-3.5 h-3.5" />
          Voice &amp; Audio
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-md text-secondary hover:text-primary hover:bg-primary/5 transition-colors cursor-pointer"
          aria-label="Close voice & audio panel"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 mac-scrollbar">
        {/* Voice selection */}
        <div className="rounded-2xl border border-outline bg-surface/30 p-4">
          <div className="mb-2.5 flex items-center justify-between gap-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-secondary/80">Selected Voice</p>
            <button
              type="button"
              onClick={() => workbench.navigate(voiceLibraryPath)}
              className="inline-flex items-center gap-1 text-[11px] font-bold text-accent-amber hover:text-primary transition-colors cursor-pointer"
            >
              <Settings2 className="h-3.5 w-3.5" />
              Manage
            </button>
          </div>
          <button
            type="button"
            onClick={() => setVoiceMenuOpen((open) => !open)}
            disabled={workbench.isScriptDeleted || workbench.isSessionDeleted}
            aria-expanded={voiceMenuOpen}
            className="flex w-full items-center justify-between gap-3 rounded-xl border border-outline bg-surface-container-low px-4 py-3 text-left transition-all hover:border-accent-amber/30 hover:bg-primary/5 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-accent-amber/30 bg-accent-amber/10 shrink-0">
                <Mic className="h-4.5 w-4.5 text-accent-amber" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-primary truncate">
                  {selectedProfileLabel || "未选择音色"}
                </p>
                <p className="mt-0.5 text-xs text-secondary/70 truncate">
                  {selectedProfileLabel
                    ? `${profileSourceLabel ? `${profileSourceLabel} · ` : ""}${voiceSettings.language || "zh"} · ${workbench.selectedEngine === "local_mlx" ? "Local MLX" : workbench.cloudProvider}`
                    : "选择音色以生成完整音频"}
                </p>
              </div>
            </div>
            <ChevronDown
              className={cn(
                "h-4 w-4 text-secondary/60 transition-transform shrink-0",
                voiceMenuOpen && "rotate-180",
              )}
            />
          </button>
          {voiceMenuOpen ? (
            <div className="mt-3 max-h-[220px] overflow-y-auto rounded-2xl border border-outline bg-surface-container-highest backdrop-blur-xl p-2 shadow-[0_12px_36px_rgba(0,0,0,0.06)]">
              {activeVoiceProfiles.length ? (
                <div className="space-y-1">
                  {activeVoiceProfiles.map((profile) => {
                    const selected = profile.voice_profile_id === selectedProfileId;
                    const sourceLabel = profile.source === "built_in" ? "默认音色" : "我的音色";
                    return (
                      <button
                        key={profile.voice_profile_id}
                        type="button"
                        onClick={() => {
                          setVoiceMenuOpen(false);
                          void workbench.handleSelectVoiceProfile(profile.voice_profile_id);
                        }}
                        className={cn(
                          "flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition-colors cursor-pointer",
                          selected
                            ? "bg-accent-amber/10 text-primary font-semibold"
                            : "text-secondary hover:bg-primary/5 hover:text-primary",
                        )}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm">{profile.name}</span>
                          <span className="mt-0.5 block truncate text-[11px] text-secondary/60">
                            {sourceLabel} · {profile.language || "zh"} ·{" "}
                            {profile.provider === "local_mlx" ? "Local MLX" : profile.provider}
                          </span>
                        </span>
                        {selected ? <Check className="h-4 w-4 shrink-0 text-accent-amber" /> : null}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="px-3 py-4 text-xs text-secondary/60 text-center">
                  暂无可用音色。
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* Rendering engine */}
        <div className="rounded-2xl border border-outline bg-surface/30 p-4">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-secondary/80">
            Rendering Engine
          </p>
          <div className="grid gap-2">
            <button
              type="button"
              onClick={() => workbench.setSelectedEngine("local_mlx")}
              disabled={workbench.localEngineDisabled}
              className={cn(
                "rounded-xl border p-3 text-left transition-all cursor-pointer",
                workbench.selectedEngine === "local_mlx"
                  ? "border-accent-amber/30 bg-accent-amber/10"
                  : "border-outline bg-surface-container-low hover:bg-primary/5 hover:border-outline",
                workbench.localEngineDisabled && "cursor-not-allowed opacity-40",
              )}
            >
              <div className="flex items-center gap-2.5">
                <Cpu
                  className={cn(
                    "h-4 w-4 shrink-0",
                    workbench.selectedEngine === "local_mlx" ? "text-accent-amber" : "text-secondary",
                  )}
                />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-primary">Local MLX</p>
                  <p className="text-xs text-secondary/70">
                    {workbench.capability?.available ? "Apple Silicon" : "Not available"}
                  </p>
                </div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => workbench.setSelectedEngine("cloud")}
              disabled={workbench.cloudEngineDisabled}
              className={cn(
                "rounded-xl border p-3 text-left transition-all cursor-pointer",
                workbench.selectedEngine === "cloud"
                  ? "border-accent-amber/30 bg-accent-amber/10"
                  : "border-outline bg-surface-container-low hover:bg-primary/5 hover:border-outline",
                workbench.cloudEngineDisabled && "cursor-not-allowed opacity-40",
              )}
            >
              <div className="flex items-center gap-2.5">
                <Cloud
                  className={cn(
                    "h-4 w-4 shrink-0",
                    workbench.selectedEngine === "cloud" ? "text-accent-amber" : "text-secondary",
                  )}
                />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-primary">Cloud Synthesis</p>
                  <p className="text-xs text-secondary/70">{workbench.cloudProvider}</p>
                </div>
              </div>
            </button>
          </div>
        </div>

        {/* Generate audio */}
        <div className="rounded-2xl border border-outline bg-surface/30 p-4 space-y-3">
          <button
            type="button"
            onClick={workbench.handleGenerateAudio}
            disabled={generationDisabled}
            title={needsVoiceProfile ? "Choose a voice before generating local MLX audio." : undefined}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-accent-amber hover:bg-accent-amber/95 active:scale-[0.98] transition-all px-5 text-sm font-bold text-on-primary disabled:opacity-40 disabled:cursor-not-allowed shadow-[0_4px_16px_rgba(242,191,87,0.2)] cursor-pointer"
          >
            {workbench.generating ? (
              <span className="inline-flex h-4 w-4 rounded-full border-2 border-black/20 border-t-black animate-spin" />
            ) : (
              <Wand2 className="h-4 w-4" />
            )}
            {workbench.generating ? "Generating..." : "Generate final audio"}
          </button>
          {workbench.scriptCheck.blockingSummary ? (
            <p className="text-xs text-red-200/90 font-medium">{workbench.scriptCheck.blockingSummary}</p>
          ) : null}
          {needsVoiceProfile ? (
            <p className="text-xs text-amber-200/80 font-medium">请先选择一个 Local MLX 音色。</p>
          ) : null}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-outline bg-surface-container-low p-3">
            <div className="flex items-center gap-1.5 text-secondary/80">
              <Clock3 className="h-3 w-3 text-accent-amber" />
              <span className="text-[9px] font-bold uppercase tracking-wider">Est. Length</span>
            </div>
            <p className="mt-1.5 text-[22px] font-display font-bold text-primary">
              {workbench.estMinutes}
            </p>
          </div>
          <div className="rounded-2xl border border-outline bg-surface-container-low p-3">
            <div className="flex items-center gap-1.5 text-secondary/80">
              <History className="h-3 w-3 text-accent-amber" />
              <span className="text-[9px] font-bold uppercase tracking-wider">Word Count</span>
            </div>
            <p className="mt-1.5 text-[22px] font-display font-bold text-primary">
              {workbench.wordCount}
            </p>
          </div>
        </div>

        {/* Errors and warnings */}
        {workbench.audioError ? (
          <div className="rounded-2xl border border-red-500/10 bg-red-500/5 px-3.5 py-3 text-xs text-red-300">
            {workbench.audioError}
          </div>
        ) : null}
        {workbench.voiceSelectionError ? (
          <div className="rounded-2xl border border-red-500/10 bg-red-500/5 px-3.5 py-3 text-xs text-red-300">
            {workbench.voiceSelectionError}
          </div>
        ) : null}
        {workbench.pollWarning ? (
          <div className="rounded-2xl border border-accent-amber/20 bg-accent-amber/5 px-3.5 py-3 text-xs text-accent-amber">
            {workbench.pollWarning}
          </div>
        ) : null}
        {workbench.audioMessage ? (
          <div className="rounded-2xl border border-accent-amber/20 bg-accent-amber/5 px-3.5 py-3 text-xs text-accent-amber">
            {workbench.audioMessage}
          </div>
        ) : null}

        {/* Render progress */}
        {!workbench.audioError && activeAudioRequestState ? (
          <div className="rounded-2xl border border-outline bg-surface/30 p-4 text-xs text-secondary space-y-2.5">
            <div className="flex items-center justify-between gap-3">
              <span className="font-semibold text-primary">{`${Math.round(activeAudioRequestState.progress_percent)}% · ${activeAudioRequestState.message}`}</span>
              {workbench.generating && activeAudioRequestState.phase === "running" ? (
                <button
                  type="button"
                  onClick={() => void workbench.handleCancelAudio()}
                  className="rounded-lg border border-outline bg-surface-container-low px-2.5 py-1 text-[10px] font-bold text-primary hover:bg-primary/5 transition-all cursor-pointer"
                >
                  Cancel
                </button>
              ) : null}
            </div>
            <ProgressBar value={activeAudioRequestState.progress_percent} />
          </div>
        ) : null}

        {/* Generated audio */}
        <div className="rounded-2xl border border-outline bg-surface/30 p-4">
          <div className="mb-3 flex items-center gap-2">
            <FileAudio className="h-3.5 w-3.5 text-accent-amber" />
            <p className="text-[10px] font-bold uppercase tracking-wider text-secondary/80">Generated Audio</p>
          </div>

          {workbench.audioSrc ? (
            <div className="flex flex-col gap-3">
              <div className="rounded-xl border border-outline bg-surface/10 p-3">
                <div className="flex items-start justify-between gap-2 mb-3">
                  <p className="truncate text-xs font-semibold text-primary">{workbench.outputFilename}</p>
                  <button
                    type="button"
                    onClick={() => void workbench.handleRevealInFinder()}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-outline bg-surface-container-low text-secondary hover:text-primary hover:bg-primary/8 transition-all shrink-0 cursor-pointer"
                    title="Reveal in Finder"
                  >
                    <FolderOpen className="h-3.5 w-3.5" />
                  </button>
                </div>
                <AudioPlayer
                  ref={workbench.audioRef}
                  src={workbench.audioSrc}
                  onError={workbench.handleAudioLoadError}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => void workbench.handlePreviewAudio()}
                  className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl border border-outline bg-surface-container-low text-xs font-bold text-primary hover:bg-primary/8 transition-all cursor-pointer"
                >
                  {workbench.isAudioPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                  Preview
                </button>
                <button
                  type="button"
                  onClick={workbench.handleDownloadAudio}
                  className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl border border-outline bg-surface-container-low text-xs font-bold text-primary hover:bg-primary/8 transition-all cursor-pointer"
                >
                  <Download className="h-3.5 w-3.5" />
                  Download
                </button>
                <button
                  type="button"
                  onClick={() => void workbench.handleShareAudio()}
                  className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl border border-outline bg-surface-container-low text-xs font-bold text-primary hover:bg-primary/8 transition-all cursor-pointer"
                >
                  <Share2 className="h-3.5 w-3.5" />
                  Share
                </button>
                <button
                  type="button"
                  onClick={() => void workbench.handleDeleteAudio()}
                  className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl border border-red-500/20 bg-red-500/10 text-xs font-bold text-red-300 hover:bg-red-500/20 transition-all cursor-pointer"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-outline bg-surface/10 py-8 px-4 text-center">
              <Wand2 className="mb-2 h-7 w-7 text-accent-amber animate-pulse" />
              <p className="text-sm font-semibold text-primary">No audio yet</p>
              <p className="mt-1.5 text-xs leading-relaxed text-secondary/60">
                Choose a voice and generate the final audio above.
              </p>
            </div>
          )}
        </div>

        {/* Manage voices link */}
        <button
          type="button"
          onClick={() => navigate("/voice-studio")}
          className="flex w-full items-center justify-between gap-2 rounded-xl border border-outline px-4 py-3 text-sm font-medium text-secondary hover:text-primary hover:bg-primary/5 transition-colors cursor-pointer"
        >
          <span className="flex items-center gap-2">
            <Mic className="h-4 w-4 text-accent-amber" />
            Manage voices
          </span>
          <ExternalLink className="h-3.5 w-3.5 text-secondary/40" />
        </button>
      </div>
    </div>
  );
}
