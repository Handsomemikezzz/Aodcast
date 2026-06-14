import type { SessionProject, StudioProgressState } from "../types";
import type { ScriptCheckResult } from "../pages/script-workbench/spokenScriptTypes";

function hasVoiceSelected(project: SessionProject, scriptId?: string): boolean {
  if (project.artifact?.voice_reference) return true;
  if (scriptId && project.artifact?.script_artifacts?.[scriptId]?.voice_reference) return true;
  return false;
}

function hasAudio(project: SessionProject, scriptId?: string): boolean {
  if (scriptId) {
    const sa = project.artifact?.script_artifacts?.[scriptId];
    if (sa?.audio_path) return true;
  }
  return Boolean(project.artifact?.audio_path);
}

function isScriptChangedAfterAudio(
  project: SessionProject,
  scriptId: string | undefined,
  isDirty: boolean,
): boolean {
  if (!hasAudio(project, scriptId)) return false;
  if (isDirty) return true;
  const scriptUpdatedAt = project.script?.updated_at;
  const artifactCreatedAt = project.artifact?.created_at;
  if (scriptUpdatedAt && artifactCreatedAt && scriptUpdatedAt > artifactCreatedAt) return true;
  // script_edited state while audio already exists means the script was re-edited post-render
  if (project.session.state === "script_edited") return true;
  return false;
}

export function deriveStudioState(
  project: SessionProject | null,
  _scriptText: string,
  scriptCheck: ScriptCheckResult,
  isDirty: boolean,
  scriptId?: string,
): StudioProgressState {
  if (!project) return "needs_brief";

  const { state } = project.session;
  const transcriptTurns = project.transcript?.turns ?? [];
  const hasScript = Boolean(project.script && !project.script.deleted_at);

  if (state === "topic_defined") {
    return "needs_brief";
  }

  if (state === "interview_in_progress" || state === "readiness_evaluation") {
    return "needs_interview";
  }

  if (state === "ready_to_generate") {
    return "ready_to_generate_script";
  }

  if (!hasScript) {
    return "script_ready_needs_review";
  }

  if (!scriptCheck.canRender) {
    return "script_blocked_for_tts";
  }

  if (isScriptChangedAfterAudio(project, scriptId, isDirty)) {
    return "script_changed_after_audio";
  }

  if (hasAudio(project, scriptId)) {
    return "audio_ready";
  }

  // Script just generated (not yet edited/reviewed by user): prompt review first
  if (state === "script_generated" && !isDirty) {
    return "script_ready_needs_review";
  }

  if (!hasVoiceSelected(project, scriptId)) {
    return "needs_voice";
  }

  return "ready_to_generate_audio";
}
