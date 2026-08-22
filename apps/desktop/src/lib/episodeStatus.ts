import type { SessionProject } from "../types";

export type EpisodeProductStatusKind =
  | "draft"
  | "ready_to_generate"
  | "generating"
  | "audio_ready"
  | "audio_needs_update"
  | "failed";

export type EpisodeProductStatus = {
  kind: EpisodeProductStatusKind;
  label: string;
};

const STATUS_LABELS: Record<EpisodeProductStatusKind, string> = {
  draft: "Draft",
  ready_to_generate: "Ready to generate",
  generating: "Generating audio",
  audio_ready: "Audio ready",
  audio_needs_update: "Audio needs update",
  failed: "Generation failed",
};

export function projectAudioPath(project: SessionProject | null, scriptId?: string): string {
  if (!project) return "";
  if (scriptId) {
    const scriptAudio = project.artifact?.script_artifacts?.[scriptId]?.audio_path;
    if (scriptAudio) return scriptAudio;
  }
  return project.render_manifest?.output.audio_path || project.artifact?.audio_path || "";
}

export function projectHasSelectedVoice(project: SessionProject | null, scriptId?: string): boolean {
  if (!project) return false;
  const scriptReference = scriptId
    ? project.artifact?.script_artifacts?.[scriptId]?.speaker_reference
    : null;
  const reference = scriptReference ?? project.artifact?.speaker_reference;
  return Boolean(reference?.speaker_reference_id);
}

export function isProjectSourceOutOfDate(project: SessionProject | null): boolean {
  const source = project?.source;
  const generatedSource = project?.script?.generation_metadata?.source;
  if (!source || !generatedSource) return false;
  return generatedSource.version !== source.version || generatedSource.content_hash !== source.content_hash;
}

export function isProjectAudioOutOfDate(
  project: SessionProject | null,
  scriptId?: string,
  isDirty = false,
): boolean {
  if (!projectAudioPath(project, scriptId)) return false;
  if (isDirty || isProjectSourceOutOfDate(project)) return true;
  if (scriptId && project?.render_manifest?.script_id && project.render_manifest.script_id !== scriptId) return true;
  if (project?.session.state === "script_edited") return true;

  const scriptUpdatedAt = Date.parse(project?.script?.updated_at || "");
  const renderedAt = Date.parse(
    project?.render_manifest?.created_at || project?.artifact?.created_at || "",
  );
  return Number.isFinite(scriptUpdatedAt) && Number.isFinite(renderedAt) && scriptUpdatedAt > renderedAt;
}

export function deriveEpisodeProductStatus({
  project,
  scriptId,
  isDirty = false,
  generating = false,
  generationFailed = false,
  audioOutOfDate,
  readyToGenerate,
}: {
  project: SessionProject | null;
  scriptId?: string;
  isDirty?: boolean;
  generating?: boolean;
  generationFailed?: boolean;
  audioOutOfDate?: boolean;
  readyToGenerate?: boolean;
}): EpisodeProductStatus {
  let kind: EpisodeProductStatusKind;
  const hasScript = Boolean(project?.script && !project.script.deleted_at);
  const hasAudio = Boolean(projectAudioPath(project, scriptId));

  if (generating || project?.session.state === "audio_rendering") kind = "generating";
  else if (generationFailed || project?.session.state === "failed") kind = "failed";
  else if (hasAudio && (audioOutOfDate ?? isProjectAudioOutOfDate(project, scriptId, isDirty))) {
    kind = "audio_needs_update";
  } else if (hasAudio) kind = "audio_ready";
  else if (!hasScript && project?.session.state === "completed") kind = "audio_ready";
  else if (
    !hasScript
    && (project?.session.state === "script_generated" || project?.session.state === "script_edited")
  ) kind = "ready_to_generate";
  else if (hasScript && (readyToGenerate ?? true)) kind = "ready_to_generate";
  else kind = "draft";

  return { kind, label: STATUS_LABELS[kind] };
}

export function episodeStatusTone(kind: EpisodeProductStatusKind): string {
  if (kind === "audio_ready") return "text-emerald-700 dark:text-emerald-300";
  if (kind === "audio_needs_update") return "text-amber-700 dark:text-amber-300";
  if (kind === "generating") return "text-accent-amber";
  if (kind === "failed") return "text-red-700 dark:text-red-300";
  return "text-secondary";
}

export function formatEpisodeDuration(project: SessionProject): string {
  const durationMs = project.render_manifest?.output.duration_ms;
  if (!durationMs || durationMs <= 0) return "";
  const totalSeconds = Math.round(durationMs / 1_000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function formatRelativeEpisodeTime(value: string, now = Date.now()): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "";
  const elapsedSeconds = Math.max(0, Math.round((now - timestamp) / 1_000));
  if (elapsedSeconds < 60) return "Just now";
  const minutes = Math.floor(elapsedSeconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
