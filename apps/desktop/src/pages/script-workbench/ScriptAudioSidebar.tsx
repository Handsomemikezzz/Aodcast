import { useState } from "react";
import { Check, ChevronDown, Clock3, Cloud, Cpu, Download, FileAudio, FolderOpen, History, Mic, Pause, Play, Settings2, Share2, Trash2, Wand2 } from "lucide-react";
import { cn } from "../../lib/utils";
import { filterActiveVoiceProfiles, resolveProjectVoiceSettings, selectedVoiceProfileLabel } from "../../lib/voiceSettings";
import { ProgressBar } from "../../components/ProgressBar";
import { isActiveRequestState } from "../../lib/requestState";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";

export function ScriptAudioSidebar({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  const [voiceMenuOpen, setVoiceMenuOpen] = useState(false);
  const voiceSettings = resolveProjectVoiceSettings(workbench.project);
  const selectedProfileLabel = selectedVoiceProfileLabel(workbench.project);
  const selectedProfileId = workbench.project?.artifact?.voice_reference?.voice_profile_id || "";
  const profileSource = workbench.project?.artifact?.voice_reference?.profile_source;
  const profileSourceLabel = profileSource === "built_in" ? "默认音色" : profileSource === "user_saved" ? "我的音色" : "";
  const activeVoiceProfiles = filterActiveVoiceProfiles(workbench.voiceProfiles);
  const activeAudioRequestState = isActiveRequestState(workbench.audioRequestState) ? workbench.audioRequestState : null;
  const needsVoiceProfile = workbench.selectedEngine === "local_mlx" && (!selectedProfileId || workbench.project?.artifact?.voice_reference?.source !== "voice_profile");
  const generationDisabled =
    workbench.generating ||
    workbench.script.trim().length === 0 ||
    needsVoiceProfile ||
    (workbench.selectedEngine === "local_mlx" ? workbench.localEngineDisabled : workbench.cloudEngineDisabled);
  const scriptVoiceStudioPath = workbench.project?.script
    ? `/voice-studio/${workbench.project.session.session_id}/${workbench.project.script.script_id}`
    : "/voice-studio";

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
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Selected Voice</p>
              <button
                type="button"
                onClick={() => workbench.navigate(scriptVoiceStudioPath)}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-accent-amber transition-colors hover:text-primary"
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
              className="flex w-full items-center justify-between gap-3 rounded-[18px] border border-outline bg-surface-container-low px-3 py-3 text-left transition-colors hover:border-accent-amber/30 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-accent-amber/30 bg-accent-amber/10">
                  <Mic className="h-5 w-5 text-accent-amber" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary">
                    {selectedProfileLabel || "未选择音色"}
                  </p>
                  <p className="mt-1 text-xs text-secondary">
                    {selectedProfileLabel
                      ? `${profileSourceLabel ? `${profileSourceLabel} · ` : ""}${voiceSettings.language || "zh"} · ${workbench.selectedEngine === "local_mlx" ? "Local MLX" : workbench.cloudProvider}`
                      : "选择音色后，Script 页会用它生成完整音频。"}
                  </p>
                </div>
              </div>
              <ChevronDown className={cn("h-4 w-4 text-secondary transition-transform", voiceMenuOpen && "rotate-180")} />
            </button>
            {voiceMenuOpen ? (
              <div className="mt-3 max-h-[260px] overflow-y-auto rounded-[18px] border border-outline bg-background/95 p-2 shadow-[0_18px_40px_rgba(0,0,0,0.28)]">
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
                            "flex w-full items-center justify-between gap-3 rounded-2xl px-3 py-2 text-left transition-colors",
                            selected ? "bg-accent-amber/12 text-primary" : "text-secondary hover:bg-surface-container-low hover:text-primary",
                          )}
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium">{profile.name}</span>
                            <span className="mt-1 block truncate text-xs">
                              {sourceLabel} · {profile.language || "zh"} · {profile.provider === "local_mlx" ? "Local MLX" : profile.provider}
                            </span>
                          </span>
                          {selected ? <Check className="h-4 w-4 shrink-0 text-accent-amber" /> : null}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="px-3 py-4 text-sm text-secondary">暂无可用音色，请先在 Voice Studio 创建或保存音色。</div>
                )}
              </div>
            ) : null}
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

          <div className="rounded-[22px] border border-outline bg-[rgba(22,22,24,0.88)] p-3">
            <button
              type="button"
              onClick={workbench.handleGenerateAudio}
              disabled={generationDisabled}
              title={needsVoiceProfile ? "Choose a voice before generating local MLX audio." : undefined}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl border border-accent-amber/60 bg-[linear-gradient(180deg,#f2bf57,#d79b2f)] px-5 text-sm font-semibold text-[#231402] shadow-[0_16px_36px_rgba(215,155,47,0.28)] transition-transform hover:-translate-y-0.5 hover:shadow-[0_20px_40px_rgba(215,155,47,0.34)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {workbench.generating ? (
                <span className="inline-flex h-4 w-4 rounded-full border-2 border-black/20 border-t-black animate-spin" />
              ) : (
                <Wand2 className="h-4 w-4" />
              )}
              {workbench.generating ? "Generating..." : "Generate final audio"}
            </button>
            {needsVoiceProfile ? (
              <p className="mt-2 text-xs leading-5 text-secondary">Choose a voice profile before generating local MLX audio.</p>
            ) : null}
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
          {workbench.voiceSelectionError ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-3 py-3 text-sm text-red-200">
              {workbench.voiceSelectionError}
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
          {!workbench.audioError && activeAudioRequestState ? (
            <div className="rounded-2xl border border-outline bg-background/80 px-3 py-3 text-sm text-secondary">
              <div className="flex items-center justify-between gap-3">
                <span>{`${Math.round(activeAudioRequestState.progress_percent)}% · ${activeAudioRequestState.message}`}</span>
                {workbench.generating && activeAudioRequestState.phase === "running" ? (
                  <button
                    type="button"
                    onClick={() => void workbench.handleCancelAudio()}
                    className="rounded-full border border-outline px-3 py-1 text-[12px] font-medium text-primary transition-colors hover:bg-surface-container"
                  >
                    Cancel
                  </button>
                ) : null}
              </div>
              <ProgressBar value={activeAudioRequestState.progress_percent} className="mt-3" />
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-4 shadow-[0_22px_60px_rgba(0,0,0,0.3)] overflow-hidden">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-primary">Generated Audio</p>
            <p className="mt-1 text-xs text-secondary">Play, delete, download, or reveal the final render for this script.</p>
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
                    {workbench.project?.artifact?.final_take_id && workbench.project.artifact.takes?.length
                      ? (() => {
                          const take = workbench.project?.artifact?.takes?.find((item) => item.take_id === workbench.project?.artifact?.final_take_id);
                          return take ? `${take.voice_name} / ${take.style_name} / ${take.speed.toFixed(1)}x` : "Final Voice Studio take";
                        })()
                      : workbench.selectedEngine === "local_mlx" ? "Local MLX render" : `Cloud render via ${workbench.cloudProvider}`}
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
                onError={workbench.handleAudioLoadError}
                className="mt-4 w-full [&::-webkit-media-controls-panel]:bg-background [&::-webkit-media-controls-panel]:border [&::-webkit-media-controls-panel]:border-outline"
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-4">
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
              <button
                type="button"
                onClick={() => void workbench.handleDeleteAudio()}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-red-500/25 bg-red-500/8 text-sm font-medium text-red-200 transition-colors hover:bg-red-500/12"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            </div>
          </div>
        ) : (
          <div className="flex min-h-[280px] flex-1 flex-col items-center justify-center rounded-[22px] border border-dashed border-accent-amber/30 bg-accent-amber/6 px-5 text-center">
            <Wand2 className="mb-3 h-8 w-8 text-accent-amber" />
            <p className="text-sm font-medium text-primary">No audio file yet</p>
            <p className="mt-2 max-w-[280px] text-xs leading-6 text-secondary">
              Choose a voice profile, save your latest edits, then generate the final audio from this Script page.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
