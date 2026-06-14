import { useState } from "react";
import { Check, ChevronDown, Clock3, Cloud, Cpu, Download, FileAudio, FolderOpen, History, Mic, Pause, Play, Settings2, Share2, Trash2, Wand2 } from "lucide-react";
import { cn } from "../../lib/utils";
import { filterActiveVoiceProfiles, resolveProjectVoiceSettings, selectedVoiceProfileLabel } from "../../lib/voiceSettings";
import { ProgressBar } from "../../components/ProgressBar";
import { isActiveRequestState } from "../../lib/requestState";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";
import { AudioPlayer } from "../../components/AudioPlayer";

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
    !workbench.scriptCheck.canRender ||
    needsVoiceProfile ||
    (workbench.selectedEngine === "local_mlx" ? workbench.localEngineDisabled : workbench.cloudEngineDisabled);
  const scriptVoiceStudioPath = workbench.project?.script
    ? `/voice-studio/${workbench.project.session.session_id}/${workbench.project.script.script_id}`
    : "/voice-studio";

  return (
    <section className="mx-auto grid w-full max-w-[960px] gap-4 lg:grid-cols-2 lg:items-start">
      <div className="rounded-[32px] border border-outline theme-panel-elevated backdrop-blur-md p-5 shadow-[0_20px_50px_rgba(0,0,0,0.4)] overflow-hidden">
        <div className="mb-4 flex items-center justify-between gap-3 border-b border-outline pb-4">
          <div>
            <p className="text-sm font-bold text-primary font-display tracking-tight">Voice Workspace</p>
            <p className="mt-1 text-[11px] text-secondary/80">Persona, engine, live stats, and output actions.</p>
          </div>
          <Mic className="h-4.5 w-4.5 text-accent-amber" />
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-outline bg-surface-container p-4">
            <div className="mb-2.5 flex items-center justify-between gap-3">
              <p className="text-[10px] font-bold uppercase tracking-wider text-secondary/80">Selected Voice</p>
              <button
                type="button"
                onClick={() => workbench.navigate(scriptVoiceStudioPath)}
                className="inline-flex items-center gap-1 text-[11px] font-bold text-accent-amber transition-colors hover:text-primary cursor-pointer"
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
              className="flex w-full items-center justify-between gap-3 rounded-xl border border-outline bg-surface-container-high/60 px-4 py-3 text-left transition-all hover:border-accent-amber/30 hover:bg-surface-container-high active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-accent-amber/30 bg-accent-amber/10 shrink-0">
                  <Mic className="h-5 w-5 text-accent-amber" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-primary truncate">
                    {selectedProfileLabel || "未选择音色"}
                  </p>
                  <p className="mt-1 text-xs text-secondary/70 truncate">
                    {selectedProfileLabel
                      ? `${profileSourceLabel ? `${profileSourceLabel} · ` : ""}${voiceSettings.language || "zh"} · ${workbench.selectedEngine === "local_mlx" ? "Local MLX" : workbench.cloudProvider}`
                      : "选择音色以生成完整音频"}
                  </p>
                </div>
              </div>
              <ChevronDown className={cn("h-4 w-4 text-secondary/60 transition-transform shrink-0", voiceMenuOpen && "rotate-180")} />
            </button>
            {voiceMenuOpen ? (
              <div className="mt-3 max-h-[260px] overflow-y-auto rounded-2xl border border-outline bg-surface-container-highest backdrop-blur-xl p-2 shadow-lg">
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
                            selected ? "bg-accent-amber/10 text-primary font-semibold" : "text-secondary hover:bg-surface-container-high/60 hover:text-primary",
                          )}
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm">{profile.name}</span>
                            <span className="mt-1 block truncate text-[11px] text-secondary/60">
                              {sourceLabel} · {profile.language || "zh"} · {profile.provider === "local_mlx" ? "Local MLX" : profile.provider}
                            </span>
                          </span>
                          {selected ? <Check className="h-4 w-4 shrink-0 text-accent-amber" /> : null}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="px-3 py-4 text-xs text-secondary/60 text-center">暂无可用音色，请先在 Voice Studio 创建音色。</div>
                )}
              </div>
            ) : null}
          </div>

          <div className="rounded-2xl border border-outline bg-surface-container p-4">
            <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-secondary/80">Rendering Engine</p>
            <div className="grid gap-2.5">
              <button
                type="button"
                onClick={() => workbench.setSelectedEngine("local_mlx")}
                disabled={workbench.localEngineDisabled}
                className={cn(
                  "rounded-2xl border p-4 text-left transition-all cursor-pointer relative overflow-hidden",
                  workbench.selectedEngine === "local_mlx"
                    ? "border-accent-amber/30 bg-accent-amber/10 shadow-[0_0_16px_rgba(242,191,87,0.06)]"
                    : "border-outline bg-surface-container-high/60 hover:bg-surface-container-high hover:border-outline",
                  workbench.localEngineDisabled && "cursor-not-allowed opacity-40",
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={cn("flex h-9 w-9 items-center justify-center rounded-xl border shrink-0", 
                    workbench.selectedEngine === "local_mlx" ? "border-accent-amber/30 bg-accent-amber/10" : "border-outline bg-surface-container-high/60"
                  )}>
                    <Cpu className={cn("h-4 w-4", workbench.selectedEngine === "local_mlx" ? "text-accent-amber" : "text-secondary")} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-primary">Local MLX</p>
                    <p className="mt-1 text-xs text-secondary/70 truncate">
                      {workbench.capability?.available ? "Apple Silicon 专属优化" : "当前设备不可用"}
                    </p>
                  </div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => workbench.setSelectedEngine("cloud")}
                disabled={workbench.cloudEngineDisabled}
                className={cn(
                  "rounded-2xl border p-4 text-left transition-all cursor-pointer relative overflow-hidden",
                  workbench.selectedEngine === "cloud"
                    ? "border-accent-amber/30 bg-accent-amber/10 shadow-[0_0_16px_rgba(242,191,87,0.06)]"
                    : "border-outline bg-surface-container-high/60 hover:bg-surface-container-high hover:border-outline",
                  workbench.cloudEngineDisabled && "cursor-not-allowed opacity-40",
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={cn("flex h-9 w-9 items-center justify-center rounded-xl border shrink-0", 
                    workbench.selectedEngine === "cloud" ? "border-accent-amber/30 bg-accent-amber/10" : "border-outline bg-surface-container-high/60"
                  )}>
                    <Cloud className={cn("h-4 w-4", workbench.selectedEngine === "cloud" ? "text-accent-amber" : "text-secondary")} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-primary">Cloud Synthesis</p>
                    <p className="mt-1 text-xs text-secondary/70 truncate">厂商: {workbench.cloudProvider}</p>
                  </div>
                </div>
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-outline bg-surface-container p-4">
            <button
              type="button"
              onClick={workbench.handleGenerateAudio}
              disabled={generationDisabled}
              title={needsVoiceProfile ? "Choose a voice before generating local MLX audio." : undefined}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-accent-amber hover:bg-accent-amber/95 active:scale-[0.98] transition-all px-5 text-sm font-bold text-on-primary disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-[0_4px_16px_rgba(242,191,87,0.2)]"
            >
              {workbench.generating ? (
                <span className="inline-flex h-4 w-4 rounded-full border-2 border-black/20 border-t-black animate-spin" />
              ) : (
                <Wand2 className="h-4 w-4" />
              )}
              {workbench.generating ? "Generating..." : "Generate final audio"}
            </button>
            {workbench.scriptCheck.blockingSummary ? (
              <p className="mt-2 text-xs leading-5 text-red-200/90 font-medium pl-1">{workbench.scriptCheck.blockingSummary}</p>
            ) : null}
            {needsVoiceProfile ? (
              <p className="mt-2 text-xs leading-5 text-amber-200/80 font-medium pl-1">请先在上方为 Local MLX 选择一个音色。</p>
            ) : null}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-outline bg-surface-container p-4">
              <div className="flex items-center gap-2 text-secondary/80">
                <Clock3 className="h-3.5 w-3.5 text-accent-amber" />
                <span className="text-[10px] font-bold uppercase tracking-wider">Est. Length</span>
              </div>
              <p className="mt-2 text-[26px] font-display font-bold text-primary">{workbench.estMinutes}</p>
            </div>
            <div className="rounded-2xl border border-outline bg-surface-container p-4">
              <div className="flex items-center gap-2 text-secondary/80">
                <History className="h-3.5 w-3.5 text-accent-amber" />
                <span className="text-[10px] font-bold uppercase tracking-wider">Word Count</span>
              </div>
              <p className="mt-2 text-[26px] font-display font-bold text-primary">{workbench.wordCount}</p>
            </div>
          </div>

          {workbench.audioError ? (
            <div className="rounded-2xl border border-red-500/10 bg-red-500/5 px-3.5 py-3 text-xs text-red-300">
              {workbench.audioError}
            </div>
          ) : null}
          {workbench.editorError ? (
            <div className="rounded-2xl border border-red-500/10 bg-red-500/5 px-3.5 py-3 text-xs text-red-300">
              {workbench.editorError}
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
          {!workbench.audioError && activeAudioRequestState ? (
            <div className="rounded-2xl border border-outline bg-surface-container p-4 text-xs text-secondary">
              <div className="flex items-center justify-between gap-3 mb-2.5">
                <span className="font-semibold text-primary">{`${Math.round(activeAudioRequestState.progress_percent)}% · ${activeAudioRequestState.message}`}</span>
                {workbench.generating && activeAudioRequestState.phase === "running" ? (
                  <button
                    type="button"
                    onClick={() => void workbench.handleCancelAudio()}
                    className="rounded-lg border border-outline bg-surface-container-high/60 px-2.5 py-1 text-[10px] font-bold text-primary hover:bg-surface-container-high hover:border-outline transition-all cursor-pointer"
                  >
                    Cancel
                  </button>
                ) : null}
              </div>
              <ProgressBar value={activeAudioRequestState.progress_percent} />
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col rounded-[32px] border border-outline theme-panel-elevated backdrop-blur-md p-5 shadow-[0_20px_50px_rgba(0,0,0,0.4)] overflow-hidden">
        <div className="mb-4 flex items-center justify-between gap-3 border-b border-outline pb-4">
          <div>
            <p className="text-sm font-bold text-primary font-display tracking-tight">Generated Audio</p>
            <p className="mt-1 text-[11px] text-secondary/80">Play, delete, download, or reveal the final render.</p>
          </div>
          <FileAudio className="h-4.5 w-4.5 text-accent-amber" />
        </div>

        {workbench.audioSrc ? (
          <div className="flex flex-col gap-4">
            <div className="rounded-2xl border border-outline bg-surface-container-high p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-primary">{workbench.outputFilename}</p>
                  <p className="mt-1 text-xs text-secondary/70">
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
                  className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-outline bg-surface-container-high/60 text-secondary hover:text-primary hover:bg-surface-container-high hover:border-outline active:scale-[0.95] transition-all cursor-pointer"
                  title="Reveal in Finder"
                >
                  <FolderOpen className="h-4 w-4" />
                </button>
              </div>

              <div className="mt-4">
                <AudioPlayer
                  ref={workbench.audioRef}
                  src={workbench.audioSrc}
                  onError={workbench.handleAudioLoadError}
                />
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-4">
              <button
                type="button"
                onClick={() => void workbench.handlePreviewAudio()}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container-high/60 text-xs font-bold text-primary hover:bg-surface-container-high hover:border-outline active:scale-[0.98] transition-all cursor-pointer"
              >
                {workbench.isAudioPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                Preview
              </button>
              <button
                type="button"
                onClick={workbench.handleDownloadAudio}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container-high/60 text-xs font-bold text-primary hover:bg-surface-container-high hover:border-outline active:scale-[0.98] transition-all cursor-pointer"
              >
                <Download className="h-4 w-4" />
                Download
              </button>
              <button
                type="button"
                onClick={() => void workbench.handleShareAudio()}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container-high/60 text-xs font-bold text-primary hover:bg-surface-container-high hover:border-outline active:scale-[0.98] transition-all cursor-pointer"
              >
                <Share2 className="h-4 w-4" />
                Share
              </button>
              <button
                type="button"
                onClick={() => void workbench.handleDeleteAudio()}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 text-xs font-bold text-red-300 hover:bg-red-500/20 active:scale-[0.98] transition-all cursor-pointer"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            </div>
          </div>
        ) : (
          <div className="flex min-h-[280px] flex-col items-center justify-center rounded-[24px] border border-dashed border-outline bg-surface-container px-5 text-center">
            <Wand2 className="mb-3 h-8 w-8 text-accent-amber animate-pulse" />
            <p className="text-sm font-semibold text-primary">No audio file yet</p>
            <p className="mt-2 max-w-[280px] text-xs leading-relaxed text-secondary/60">
              Choose a voice profile, save your latest edits, then generate the final audio from this Script page.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
