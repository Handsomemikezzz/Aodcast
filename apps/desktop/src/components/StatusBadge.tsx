import { SessionState } from "../types";

const labelMap: Record<SessionState, string> = {
  topic_defined: "Topic Defined",
  interview_in_progress: "Interviewing",
  readiness_evaluation: "Evaluating",
  ready_to_generate: "Ready To Draft",
  script_generated: "Draft Ready",
  script_edited: "Edited",
  audio_rendering: "Rendering",
  completed: "Completed",
  failed: "Failed",
};

export function StatusBadge({ state }: { state: SessionState }) {
  return <span className={`status-chip status-${state}`}>{labelMap[state]}</span>;
}
