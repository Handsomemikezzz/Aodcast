import type { LocalVoiceMode, ModelStatus, SessionProject, SpeakerReference, VoiceRenderSettings } from "../types";

const BUILT_IN_SPEAKER_REFERENCE_LABELS: Record<string, string> = {
  builtin_clear_broadcast: "Clear broadcaster",
  builtin_warm_knowledge: "Warm explainer",
};

/** Built-in profiles removed from the app but still returned by stale runtimes. */
const REMOVED_BUILTIN_SPEAKER_REFERENCE_IDS = new Set(["builtin_deep_story"]);

export function filterActiveSpeakerReferences(references: SpeakerReference[]): SpeakerReference[] {
  return references.filter((reference) => !REMOVED_BUILTIN_SPEAKER_REFERENCE_IDS.has(reference.speaker_reference_id));
}

function defaultVoiceRenderSettings(): VoiceRenderSettings {
  return {
    voice_id: "warm_narrator",
    voice_name: "Warm narrator",
    style_id: "natural",
    style_name: "Natural",
    speed: 1.0,
    language: "zh",
    audio_format: "wav",
  };
}

export function resolveProjectVoiceSettings(
  project: SessionProject | null | undefined,
  scriptId?: string,
): VoiceRenderSettings {
  const defaults = defaultVoiceRenderSettings();
  const saved = scriptId
    ? project?.artifact?.script_artifacts?.[scriptId]?.voice_settings ?? project?.artifact?.voice_settings
    : project?.artifact?.voice_settings;
  if (!saved) return defaults;
  return {
    ...defaults,
    ...saved,
    voice_id: saved.voice_id?.trim() || defaults.voice_id,
    style_id: saved.style_id?.trim() || defaults.style_id,
    speed: typeof saved.speed === "number" ? saved.speed : defaults.speed,
    language: saved.language?.trim() || defaults.language,
    audio_format: saved.audio_format?.trim() || defaults.audio_format,
  };
}

export function selectedSpeakerReferenceLabel(
  project: SessionProject | null | undefined,
  scriptId?: string,
): string {
  const reference = scriptId
    ? project?.artifact?.script_artifacts?.[scriptId]?.speaker_reference ?? project?.artifact?.speaker_reference
    : project?.artifact?.speaker_reference;
  if (!reference?.speaker_reference_id) return "";
  if (reference.name.trim()) return reference.name.trim();
  return BUILT_IN_SPEAKER_REFERENCE_LABELS[reference.speaker_reference_id] || "Selected voice";
}


export function modelId(model: ModelStatus): string {
  return model.hf_repo_id || model.model_name;
}

/** Voice options follow the model's declared capability, never its name. */
export function modelMode(model: ModelStatus | undefined): LocalVoiceMode {
  return model?.capabilities?.capabilities.speaker_cloning === "native" ? "clone" : "preset";
}

export function readySpeechModel(models: ModelStatus[], ...preferredIds: string[]): ModelStatus | undefined {
  const ready = models.filter((model) => model.ready === true && model.available !== false);
  for (const id of preferredIds) {
    const match = ready.find((model) => model.hf_repo_id === id || model.model_name === id);
    if (match) return match;
  }
  return ready.find((model) => model.default_for_mode) ?? ready[0];
}

/** Ready local model for one voice mode; cloning never falls back to a preset model. */
export function readyModelForMode(
  models: ModelStatus[],
  mode: LocalVoiceMode,
  ...preferredIds: string[]
): ModelStatus | undefined {
  return readySpeechModel(models.filter((model) => modelMode(model) === mode), ...preferredIds);
}

/** Speech-service model that rendered the current audio, if any. */
export function renderedSpeechModel(project: SessionProject | null | undefined): string {
  return project?.render_manifest?.pipeline.find((stage) => stage.stage === "speech_synthesis")?.model || "";
}

/** Spoken-length window the clone model accepts, from the service capability. */
export function referenceDurationIssue(
  durationMs: number,
  limits: { min?: number | null; max?: number | null },
): string {
  const seconds = (ms: number) => `${Math.round(ms / 1000)} s`;
  if (limits.max && durationMs > limits.max) {
    return `This sample is ${seconds(durationMs)}; local cloning uses at most ${seconds(limits.max)} of speech. Record a shorter clip.`;
  }
  if (limits.min && durationMs < limits.min) {
    return `This sample is ${seconds(durationMs)}; local cloning needs at least ${seconds(limits.min)} of speech.`;
  }
  return "";
}
