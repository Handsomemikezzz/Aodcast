import type { SessionProject, VoiceProfileRecord, VoiceRenderSettings } from "../types";

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

export function selectedVoiceProfileId(project: SessionProject | null | undefined): string {
  const reference = project?.artifact?.voice_reference;
  return reference?.source === "voice_profile" ? reference.voice_profile_id ?? "" : "";
}

export function resolveSelectedVoiceProfile(
  project: SessionProject | null | undefined,
  profiles: VoiceProfileRecord[],
): VoiceProfileRecord | null {
  const profileId = selectedVoiceProfileId(project);
  if (!profileId) return null;
  return profiles.find((profile) => profile.voice_profile_id === profileId) ?? null;
}

export function selectedVoiceProfileLabel(project: SessionProject | null | undefined): string {
  const reference = project?.artifact?.voice_reference;
  if (reference?.source === "voice_profile" && reference.voice_profile_id) {
    const referenceName = (reference as { name?: unknown }).name;
    return String(referenceName || reference.voice_profile_id);
  }
  return "";
}
