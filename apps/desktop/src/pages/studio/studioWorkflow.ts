import type {
  SessionProject,
  SpeakerReference,
  TTSCapability,
  TTSProviderConfig,
  VoiceRenderSettings,
} from "../../types";

export type GlobalCtaKind =
  | "generate-script"
  | "generate-audio"
  | "update-audio"
  | "ready"
  | "generating";

export type EpisodeRenderReadiness = {
  scriptReady: boolean;
  voiceReady: boolean;
  ttsReady: boolean;
  ready: boolean;
};

export function deriveEpisodeRenderReadiness({
  scriptReady,
  hasSelectedVoice,
  selectedEngine,
  selectedModelId,
  capability,
  ttsConfig,
}: {
  scriptReady: boolean;
  hasSelectedVoice: boolean;
  selectedEngine: "local_mlx" | "cloud";
  selectedModelId: string;
  capability: TTSCapability | null;
  ttsConfig: TTSProviderConfig | null;
}): EpisodeRenderReadiness {
  const ttsReady = selectedEngine === "local_mlx"
    ? Boolean(selectedModelId && capability?.available)
    : Boolean(
        ttsConfig?.provider
        && ttsConfig.provider !== "local_mlx"
        && ttsConfig.model
        && ttsConfig.base_url
        && ttsConfig.api_key
      );
  return {
    scriptReady,
    voiceReady: hasSelectedVoice,
    ttsReady,
    ready: scriptReady && hasSelectedVoice && ttsReady,
  };
}

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

export function buildVoiceFreshnessKey(
  project: SessionProject | null,
  scriptId?: string,
  currentSettings?: VoiceRenderSettings,
): string {
  const scriptArtifact = scriptId ? project?.artifact?.script_artifacts?.[scriptId] : undefined;
  return JSON.stringify({
    reference: normalizeSpeakerReference(scriptArtifact?.speaker_reference ?? project?.artifact?.speaker_reference),
    settings: normalizeVoiceSettings(
      currentSettings ?? scriptArtifact?.voice_settings ?? project?.artifact?.voice_settings,
    ),
  });
}

export type PreviewExcerpt = {
  text: string;
  source: "selection" | "paragraph" | "opening";
  label: string;
};

const MAX_PREVIEW_CHARACTERS = 520;

function clampPreviewText(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= MAX_PREVIEW_CHARACTERS) return normalized;
  const clipped = normalized.slice(0, MAX_PREVIEW_CHARACTERS);
  const sentenceEnd = Math.max(
    clipped.lastIndexOf("。"),
    clipped.lastIndexOf("！"),
    clipped.lastIndexOf("？"),
    clipped.lastIndexOf(". "),
    clipped.lastIndexOf("! "),
    clipped.lastIndexOf("? "),
  );
  return `${(sentenceEnd >= 120 ? clipped.slice(0, sentenceEnd + 1) : clipped).trim()}…`;
}

export function buildPreviewExcerpt(
  script: string,
  selectionStart = 0,
  selectionEnd = selectionStart,
): PreviewExcerpt {
  const start = Math.max(0, Math.min(selectionStart, script.length));
  const end = Math.max(start, Math.min(selectionEnd, script.length));
  const selected = script.slice(start, end).trim();
  if (selected) {
    return { text: clampPreviewText(selected), source: "selection", label: "Selected text" };
  }

  const paragraphStartMarker = script.lastIndexOf("\n\n", Math.max(0, start - 1));
  const paragraphStart = paragraphStartMarker < 0 ? 0 : paragraphStartMarker + 2;
  const paragraphEndMarker = script.indexOf("\n\n", start);
  const paragraphEnd = paragraphEndMarker < 0 ? script.length : paragraphEndMarker;
  const paragraph = script.slice(paragraphStart, paragraphEnd).trim();
  if (paragraph) {
    return { text: clampPreviewText(paragraph), source: "paragraph", label: "Current paragraph" };
  }

  const opening = script.split(/\n\s*\n/).find((candidate) => candidate.trim()) ?? script;
  return { text: clampPreviewText(opening), source: "opening", label: "Script opening" };
}
