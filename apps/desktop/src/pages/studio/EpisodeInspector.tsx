import { useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  Cloud,
  Cpu,
  ExternalLink,
  Mic2,
  Pause,
  Play,
  Settings2,
} from "lucide-react";
import { resolveAudioFileUrl } from "../../lib/audioFile";
import { cn } from "../../lib/utils";
import {
  filterActiveSpeakerReferences,
  selectedSpeakerReferenceLabel,
} from "../../lib/voiceSettings";
import type { SpeakerReference } from "../../types";
import type { UseScriptWorkbenchResult } from "../script-workbench/useScriptWorkbench";
import type { EpisodeRenderReadiness } from "./studioWorkflow";

function InspectorTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-bold uppercase tracking-[0.12em] text-secondary/75">
      {children}
    </h2>
  );
}

function byRecentUse(a: SpeakerReference, b: SpeakerReference): number {
  const aTime = Date.parse(a.last_used_at || a.updated_at || a.created_at) || 0;
  const bTime = Date.parse(b.last_used_at || b.updated_at || b.created_at) || 0;
  return bTime - aTime;
}

export function EpisodeInspector({
  workbench,
  scriptId,
  readiness,
}: {
  workbench: UseScriptWorkbenchResult;
  scriptId: string;
  readiness: EpisodeRenderReadiness;
}) {
  const [voicePickerOpen, setVoicePickerOpen] = useState(false);
  const [playingReferenceId, setPlayingReferenceId] = useState("");
  const sampleAudioRef = useRef<HTMLAudioElement>(null);

  const references = useMemo(
    () => filterActiveSpeakerReferences(workbench.speakerReferences).sort(byRecentUse),
    [workbench.speakerReferences],
  );
  const recentReferences = references.filter((reference) => reference.last_used_at).slice(0, 3);
  const recentIds = new Set(recentReferences.map((reference) => reference.speaker_reference_id));
  const yourReferences = references.filter(
    (reference) => reference.source === "user_saved" && !recentIds.has(reference.speaker_reference_id),
  );
  const builtInReferences = references.filter(
    (reference) => reference.source === "built_in" && !recentIds.has(reference.speaker_reference_id),
  );
  const scriptArtifact = workbench.project?.artifact?.script_artifacts?.[scriptId];
  const selectedReferenceId = scriptArtifact?.speaker_reference?.speaker_reference_id
    || workbench.project?.artifact?.speaker_reference?.speaker_reference_id
    || "";
  const selectedVoiceLabel = selectedSpeakerReferenceLabel(workbench.project, scriptId) || "Choose a voice";
  const returnPath = `/studio/${workbench.project?.session.session_id ?? ""}/${scriptId}`;
  const voiceLibraryPath = `/voice-studio/${workbench.project?.session.session_id ?? ""}/${scriptId}?returnTo=${encodeURIComponent(returnPath)}`;

  const playReference = (reference: SpeakerReference) => {
    const audio = sampleAudioRef.current;
    if (!audio) return;
    if (playingReferenceId === reference.speaker_reference_id && !audio.paused) {
      audio.pause();
      setPlayingReferenceId("");
      return;
    }
    audio.src = resolveAudioFileUrl(reference.audio_path);
    setPlayingReferenceId(reference.speaker_reference_id);
    void audio.play().catch(() => setPlayingReferenceId(""));
  };

  const selectReference = async (referenceId: string) => {
    await workbench.handleSelectSpeakerReference(referenceId);
    setVoicePickerOpen(false);
  };

  const renderReferenceGroup = (label: string, items: SpeakerReference[]) => {
    if (!items.length) return null;
    return (
      <div>
        <p className="mb-1.5 px-1 text-[10px] font-bold uppercase tracking-[0.1em] text-secondary/60">{label}</p>
        <div className="space-y-1">
          {items.map((reference) => {
            const selected = reference.speaker_reference_id === selectedReferenceId;
            const playing = reference.speaker_reference_id === playingReferenceId;
            return (
              <div
                key={reference.speaker_reference_id}
                className={cn(
                  "flex items-center gap-2 rounded-xl border px-2 py-1.5 transition-colors",
                  selected
                    ? "border-accent-amber/30 bg-accent-amber/8"
                    : "border-transparent hover:bg-primary/5",
                )}
              >
                <button
                  type="button"
                  onClick={() => void selectReference(reference.speaker_reference_id)}
                  disabled={workbench.generating}
                  className="flex min-h-11 min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-container-high text-secondary">
                    <Mic2 className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold text-primary">{reference.name}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-secondary">
                      {reference.language || "Voice sample"}
                    </span>
                  </span>
                  {selected ? <Check className="h-4 w-4 shrink-0 text-accent-amber" aria-hidden="true" /> : null}
                </button>
                <button
                  type="button"
                  onClick={() => playReference(reference)}
                  aria-label={`${playing ? "Pause" : "Preview"} ${reference.name}`}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-primary/8 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
                >
                  {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <aside className="flex h-full min-h-0 flex-col overflow-y-auto bg-surface-container-low/35 mac-scrollbar">
      <audio
        ref={sampleAudioRef}
        onEnded={() => setPlayingReferenceId("")}
        onPause={() => setPlayingReferenceId("")}
        className="hidden"
      />

      <section className="border-b border-outline px-4 py-4">
        <InspectorTitle>Voice</InspectorTitle>
        <div className="mt-3 flex items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-amber/10 text-accent-amber">
            <Mic2 className="h-4.5 w-4.5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-primary">{selectedVoiceLabel}</p>
            <p className="mt-0.5 truncate text-[11px] text-secondary">
              {workbench.voiceSettings.style_name} · {workbench.voiceSettings.language?.toUpperCase() || "Auto"}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setVoicePickerOpen((open) => !open)}
          aria-expanded={voicePickerOpen}
          className="mt-3 inline-flex h-11 w-full items-center justify-between rounded-xl border border-outline bg-surface-container-low px-3 text-xs font-semibold text-primary transition-colors hover:bg-surface-container-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
        >
          Change voice
          <ChevronDown className={cn("h-4 w-4 transition-transform", voicePickerOpen && "rotate-180")} />
        </button>

        {voicePickerOpen ? (
          <div className="mt-2 space-y-3 rounded-2xl border border-outline bg-background/55 p-2.5">
            {renderReferenceGroup("Recent", recentReferences)}
            {renderReferenceGroup("Your voices", yourReferences)}
            {renderReferenceGroup("Built in", builtInReferences)}
            {!references.length ? (
              <p className="px-2 py-4 text-center text-xs leading-5 text-secondary">No saved voices yet.</p>
            ) : null}
            <button
              type="button"
              onClick={() => workbench.navigate(voiceLibraryPath)}
              className="inline-flex min-h-11 w-full items-center justify-between rounded-xl px-3 text-xs font-semibold text-secondary transition-colors hover:bg-primary/5 hover:text-primary"
            >
              Create or clone a voice
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        ) : null}
        {workbench.voiceSelectionError ? (
          <p className="mt-2 text-xs leading-5 text-red-700 dark:text-red-300" role="alert">
            {workbench.voiceSelectionError}
          </p>
        ) : null}
      </section>

      <section className="border-b border-outline px-4 py-4">
        <InspectorTitle>Delivery</InspectorTitle>
        <label htmlFor="episode-delivery-style" className="mt-3 block text-xs font-medium text-primary">Style</label>
        <select
          id="episode-delivery-style"
          value={workbench.selectedStyleId}
          onChange={(event) => workbench.setSelectedStyleId(event.target.value)}
          disabled={workbench.generating}
          className="mt-1.5 h-11 w-full rounded-xl border border-outline bg-surface-container-low px-3 text-xs font-semibold text-primary outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 disabled:opacity-45"
        >
          {!workbench.voiceStyles.length ? <option value="natural">Natural</option> : null}
          {workbench.voiceStyles.map((style) => (
            <option key={style.style_id} value={style.style_id}>{style.name}</option>
          ))}
        </select>

        <div className="mt-4 flex items-center justify-between gap-3">
          <label htmlFor="episode-delivery-speed" className="text-xs font-medium text-primary">Speed</label>
          <span className="text-xs font-semibold tabular-nums text-secondary">{workbench.deliverySpeed.toFixed(2)}×</span>
        </div>
        <input
          id="episode-delivery-speed"
          type="range"
          min="0.8"
          max="1.2"
          step="0.05"
          value={workbench.deliverySpeed}
          onChange={(event) => workbench.setDeliverySpeed(Number(event.target.value))}
          disabled={workbench.generating}
          className="premium-slider mt-2 w-full disabled:opacity-45"
        />
        <p className="mt-2 text-[11px] leading-5 text-secondary">Used for the next preview and full render.</p>
      </section>

      <section className="border-b border-outline px-4 py-4">
        <InspectorTitle>Before generating</InspectorTitle>
        <div className="mt-3 space-y-2">
          {[
            [readiness.scriptReady, "Script ready"],
            [readiness.voiceReady, "Voice selected"],
            [readiness.ttsReady, "Voice model ready"],
          ].map(([ready, label]) => (
            <div key={String(label)} className="flex min-h-8 items-center gap-2 text-xs">
              <span className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                ready
                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300",
              )}>
                {ready ? <Check className="h-3 w-3" /> : <span className="text-[10px] font-bold">!</span>}
              </span>
              <span className={ready ? "text-secondary" : "font-semibold text-primary"}>{label}</span>
            </div>
          ))}
        </div>
        {!readiness.voiceReady ? (
          <button
            type="button"
            onClick={() => setVoicePickerOpen(true)}
            className="mt-3 h-10 rounded-xl border border-accent-amber/25 bg-accent-amber/8 px-3 text-xs font-semibold text-accent-amber"
          >
            Choose voice
          </button>
        ) : null}
        {!readiness.ttsReady ? (
          <button
            type="button"
            onClick={() => workbench.navigate(workbench.selectedEngine === "local_mlx" ? "/models" : "/settings")}
            className="mt-3 h-10 rounded-xl border border-outline px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/5"
          >
            {workbench.selectedEngine === "local_mlx" ? "Open Models" : "Open Settings"}
          </button>
        ) : null}
      </section>

      <details className="group px-4 py-4">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between text-xs font-semibold text-secondary outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-accent-amber/50 [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-2"><Settings2 className="h-4 w-4" /> Advanced audio settings</span>
          <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-2" role="group" aria-label="Voice engine">
            {([
              ["local_mlx", Cpu, "Local"],
              ["cloud", Cloud, "Cloud"],
            ] as const).map(([engine, Icon, label]) => (
              <button
                key={engine}
                type="button"
                onClick={() => workbench.setSelectedEngine(engine)}
                disabled={workbench.generating}
                className={cn(
                  "inline-flex h-11 items-center justify-center gap-2 rounded-xl border text-xs font-semibold transition-colors disabled:opacity-45",
                  workbench.selectedEngine === engine
                    ? "border-accent-amber/30 bg-accent-amber/8 text-accent-amber"
                    : "border-outline text-secondary hover:bg-primary/5 hover:text-primary",
                )}
              >
                <Icon className="h-4 w-4" /> {label}
              </button>
            ))}
          </div>
          {workbench.selectedEngine === "local_mlx" ? (
            <div>
              <label htmlFor="episode-render-model" className="text-[11px] font-medium text-secondary">Model</label>
              <select
                id="episode-render-model"
                value={workbench.selectedModelId}
                onChange={(event) => workbench.setSelectedModelId(event.target.value)}
                disabled={workbench.generating}
                className="mt-1.5 h-11 w-full rounded-xl border border-outline bg-surface-container-low px-3 text-xs font-semibold text-primary outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 disabled:opacity-45"
              >
                <option value="">Choose installed model</option>
                {workbench.models
                  .filter((model) => model.downloaded && model.available !== false)
                  .map((model) => (
                    <option key={model.model_name} value={model.hf_repo_id || model.model_name}>{model.display_name}</option>
                  ))}
              </select>
            </div>
          ) : (
            <p className="rounded-xl border border-outline bg-background/40 px-3 py-2.5 text-[11px] leading-5 text-secondary">
              {workbench.cloudProvider} · configured in Settings
            </p>
          )}
        </div>
      </details>
    </aside>
  );
}
