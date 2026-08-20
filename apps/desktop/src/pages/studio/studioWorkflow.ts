import type { SessionProject, SpeakerReference, VoiceRenderSettings } from "../../types";

export type GlobalCtaKind =
  | "generate-script"
  | "generate-audio"
  | "update-audio"
  | "ready"
  | "generating";

export function resolveGlobalCtaKind({
  generating,
  hasScript,
  hasAudio,
  audioOutOfDate,
  audioError,
}: {
  generating: boolean;
  hasScript: boolean;
  hasAudio: boolean;
  audioOutOfDate: boolean;
  audioError: boolean;
}): GlobalCtaKind {
  if (generating) return "generating";
  if (!hasScript) return "generate-script";
  if (hasAudio && (audioOutOfDate || audioError)) return "update-audio";
  if (hasAudio) return "ready";
  return "generate-audio";
}

export function deriveAudioFreshness({
  hasAudio,
  generating,
  isDirty,
  serverScript,
  currentScript,
  previousServerScript,
  voiceKey,
  previousVoiceKey,
}: {
  hasAudio: boolean;
  generating: boolean;
  isDirty: boolean;
  serverScript: string;
  currentScript: string;
  previousServerScript: string;
  voiceKey: string;
  previousVoiceKey: string;
}): { outOfDate: boolean; reason?: string } {
  if (!hasAudio || generating) return { outOfDate: false };
  if (isDirty || currentScript !== serverScript || serverScript !== previousServerScript) {
    return {
      outOfDate: true,
      reason: "Script was edited after audio was generated.",
    };
  }
  if (voiceKey !== previousVoiceKey) {
    return {
      outOfDate: true,
      reason: "Voice settings changed.",
    };
  }
  return { outOfDate: false };
}

function normalizeSpeakerReference(reference?: SpeakerReference | null) {
  if (!reference) return null;
  return {
    speaker_reference_id: reference.speaker_reference_id,
    reference_hash: reference.reference_hash,
    audio_hash: reference.audio_hash,
    language: reference.language ?? "",
    audio_format: reference.audio_format ?? "",
    audio_path: reference.audio_path ?? "",
  };
}

function normalizeVoiceSettings(settings?: VoiceRenderSettings) {
  if (!settings) return null;
  return {
    voice_id: settings.voice_id ?? "",
    voice_name: settings.voice_name ?? "",
    style_id: settings.style_id ?? "",
    style_name: settings.style_name ?? "",
    speed: settings.speed ?? null,
    language: settings.language ?? "",
    audio_format: settings.audio_format ?? "",
  };
}

export function buildVoiceFreshnessKey(project: SessionProject | null, scriptId?: string): string {
  const scriptArtifact = scriptId ? project?.artifact?.script_artifacts?.[scriptId] : undefined;
  return JSON.stringify({
    reference: normalizeSpeakerReference(scriptArtifact?.speaker_reference ?? project?.artifact?.speaker_reference),
    settings: normalizeVoiceSettings(scriptArtifact?.voice_settings ?? project?.artifact?.voice_settings),
  });
}
