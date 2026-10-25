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
  return <h2 className="text-[12px] font-semibold text-primary">{children}</h2>;
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
  const localHttp = workbench.selectedEngine === "local_http";
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

  const missing = [
    !readiness.scriptReady && { label: "Script has issues to fix", action: null },
    !readiness.voiceReady && { label: "No voice selected", action: { label: "Choose voice", run: () => setVoicePickerOpen(true) } },
    !readiness.ttsReady && {
      label: localHttp ? "Local speech service isn't ready" : "Cloud voice isn't configured",
      action: { label: localHttp ? "Open Models" : "Open Settings", run: () => workbench.navigate(localHttp ? "/models" : "/settings") },
    },
  ].filter(Boolean) as { label: string; action: { label: string; run: () => void } | null }[];

  return (
    <aside className="flex h-full min-h-0 flex-col overflow-y-auto mac-scrollbar">
      <audio
        ref={sampleAudioRef}
        onEnded={() => setPlayingReferenceId("")}
        onPause={() => setPlayingReferenceId("")}
        className="hidden"
      />

      {missing.length ? (
        <section className="border-b border-outline px-4 py-4">
          <InspectorTitle>Before generating</InspectorTitle>
          <ul className="mt-2 space-y-2">
            {missing.map((item) => (
              <li key={item.label} className="flex items-center justify-between gap-2 text-[13px] text-amber-700 dark:text-amber-300">
                <span>{item.label}</span>
                {item.action ? (
                  <button
                    type="button"
                    onClick={item.action.run}
                    className="shrink-0 rounded-md px-2 py-1 text-[12px] font-medium text-primary hover:bg-primary/5"
                  >
                    {item.action.label}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="border-b border-outline px-4 py-4">
        <InspectorTitle>Voice</InspectorTitle>
        {localHttp ? (
          <>
            <label htmlFor="episode-preset-voice" className="sr-only">Preset voice</label>
            <select
              id="episode-preset-voice"
              value={workbench.selectedPresetVoiceId}
              onChange={(event) => workbench.setSelectedPresetVoiceId(event.target.value)}
              disabled={workbench.generating}
              className="mt-2 h-9 w-full rounded-lg border border-outline bg-transparent px-2.5 text-[13px] text-primary outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 disabled:opacity-45"
            >
              {!workbench.voicePresets.some((voice) => voice.voice_id === workbench.selectedPresetVoiceId) && (
                <option value={workbench.selectedPresetVoiceId}>{workbench.selectedPresetVoiceId}</option>
              )}
              {workbench.voicePresets.map((voice) => <option key={voice.voice_id} value={voice.voice_id}>{voice.name}</option>)}
            </select>
            <p className="mt-2 text-[12px] leading-5 text-secondary">
              The local speech service uses preset voices at natural style and 1.0× speed.
            </p>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setVoicePickerOpen((open) => !open)}
              aria-expanded={voicePickerOpen}
              aria-label={`Change voice (current: ${selectedVoiceLabel})`}
              className="mt-2 inline-flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-outline px-2.5 text-[13px] text-primary transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
            >
              <span className="truncate">{selectedVoiceLabel}</span>
              <ChevronDown className={cn("h-4 w-4 shrink-0 text-secondary transition-transform", voicePickerOpen && "rotate-180")} />
            </button>
            {voicePickerOpen ? (
              <div className="mt-2 space-y-3 rounded-xl border border-outline p-2">
                {renderReferenceGroup("Recent", recentReferences)}
                {renderReferenceGroup("Your voices", yourReferences)}
                {renderReferenceGroup("Built in", builtInReferences)}
                {!references.length ? (
                  <p className="px-2 py-4 text-center text-xs leading-5 text-secondary">No saved voices yet.</p>
                ) : null}
                <button
                  type="button"
                  onClick={() => workbench.navigate(voiceLibraryPath)}
                  className="inline-flex h-9 w-full items-center justify-between rounded-lg px-2 text-[13px] text-secondary transition-colors hover:bg-primary/5 hover:text-primary"
                >
                  Create or clone a voice
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>
            ) : null}
          </>
        )}
        {workbench.voiceSelectionError ? (
          <p className="mt-2 text-xs leading-5 text-red-700 dark:text-red-300" role="alert">
            {workbench.voiceSelectionError}
          </p>
        ) : null}
      </section>

      {!localHttp ? (
        <section className="border-b border-outline px-4 py-4">
          <InspectorTitle>Delivery</InspectorTitle>
          <label htmlFor="episode-delivery-style" className="mt-3 block text-[12px] text-secondary">Style</label>
          <select
            id="episode-delivery-style"
            value={workbench.selectedStyleId}
            onChange={(event) => workbench.setSelectedStyleId(event.target.value)}
            disabled={workbench.generating}
            className="mt-1 h-9 w-full rounded-lg border border-outline bg-transparent px-2.5 text-[13px] text-primary outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 disabled:opacity-45"
          >
            {!workbench.voiceStyles.length ? <option value="natural">Natural</option> : null}
            {workbench.voiceStyles.map((style) => (
              <option key={style.style_id} value={style.style_id}>{style.name}</option>
            ))}
          </select>

          <div className="mt-4 flex items-center justify-between gap-3">
            <label htmlFor="episode-delivery-speed" className="text-[12px] text-secondary">Speed</label>
            <span className="text-[12px] tabular-nums text-secondary">{workbench.deliverySpeed.toFixed(2)}×</span>
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
        </section>
      ) : null}

      <details className="group px-4 py-3">
        <summary className="flex h-9 cursor-pointer list-none items-center justify-between text-[12px] font-medium text-secondary outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-accent-amber/50 [&::-webkit-details-marker]:hidden">
          Advanced
          <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-2 space-y-3">
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-outline p-0.5" role="group" aria-label="Voice engine">
            {([
              ["local_http", Cpu, "Local"],
              ["cloud", Cloud, "Cloud"],
            ] as const).map(([engine, Icon, label]) => (
              <button
                key={engine}
                type="button"
                onClick={() => workbench.setSelectedEngine(engine)}
                disabled={workbench.generating}
                aria-pressed={workbench.selectedEngine === engine}
                className={cn(
                  "inline-flex h-8 items-center justify-center gap-1.5 rounded-md text-[12px] font-medium transition-colors disabled:opacity-45",
                  workbench.selectedEngine === engine
                    ? "bg-primary/[0.07] text-primary"
                    : "text-secondary hover:text-primary",
                )}
              >
                <Icon className="h-3.5 w-3.5" /> {label}
              </button>
            ))}
          </div>
          <p className="text-[12px] leading-5 text-secondary">
            {localHttp
              ? `Model: ${workbench.models.find((model) => (model.hf_repo_id || model.model_name) === workbench.selectedModelId)?.display_name || workbench.selectedModelId || "managed by the speech service"}`
              : `${workbench.cloudProvider} · configured in Settings`}
          </p>
        </div>
      </details>
    </aside>
  );
}
