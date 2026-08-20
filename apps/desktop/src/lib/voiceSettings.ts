import type { SessionProject, SpeakerReference, VoiceRenderSettings } from "../types";

const BUILT_IN_SPEAKER_REFERENCE_LABELS: Record<string, string> = {
  builtin_clear_broadcast: "清晰播报型",
  builtin_warm_knowledge: "温和知识型",
};

/** Built-in profiles removed from the app but still returned by stale runtimes. */
const REMOVED_BUILTIN_SPEAKER_REFERENCE_IDS = new Set(["builtin_deep_story"]);

export function filterActiveSpeakerReferences(references: SpeakerReference[]): SpeakerReference[] {
  return references.filter((reference) => !REMOVED_BUILTIN_SPEAKER_REFERENCE_IDS.has(reference.speaker_reference_id));
}

export function defaultVoiceRenderSettings(): VoiceRenderSettings {
  return {
    voice_id: "warm_narrator",
    voice_name: "温和叙述者",
    style_id: "natural",
    style_name: "自然讲述",
    speed: 1.0,
    language: "zh",
    audio_format: "wav",
  };
}

export function resolveProjectVoiceSettings(project: SessionProject | null | undefined): VoiceRenderSettings {
  const defaults = defaultVoiceRenderSettings();
  const saved = project?.artifact?.voice_settings;
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

export function selectedSpeakerReferenceLabel(project: SessionProject | null | undefined): string {
  const reference = project?.artifact?.speaker_reference;
  if (!reference?.speaker_reference_id) return "";
  if (reference.name.trim()) return reference.name.trim();
  return BUILT_IN_SPEAKER_REFERENCE_LABELS[reference.speaker_reference_id] || "已选择音色";
}
