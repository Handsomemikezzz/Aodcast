export type SessionState =
  | "topic_defined"
  | "interview_in_progress"
  | "readiness_evaluation"
  | "ready_to_generate"
  | "script_generated"
  | "script_edited"
  | "audio_rendering"
  | "completed"
  | "failed";

export type Speaker = "agent" | "user";

export type SessionRecord = {
  session_id: string;
  topic: string;
  creation_intent: string;
  state: SessionState;
  llm_provider: string;
  tts_provider: string;
  last_error: string;
  created_at: string;
  updated_at: string;
};

export type TranscriptTurn = {
  speaker: Speaker;
  content: string;
  created_at: string;
};

export type TranscriptRecord = {
  session_id: string;
  turns: TranscriptTurn[];
};

export type ScriptRecord = {
  session_id: string;
  draft: string;
  final: string;
  updated_at: string;
};

export type ArtifactRecord = {
  session_id: string;
  transcript_path: string;
  audio_path: string;
  provider: string;
  created_at: string;
};

export type SessionProject = {
  session: SessionRecord;
  transcript: TranscriptRecord | null;
  script: ScriptRecord | null;
  artifact: ArtifactRecord | null;
};

export type Readiness = {
  topic_context: boolean;
  core_viewpoint: boolean;
  example_or_detail: boolean;
  conclusion: boolean;
  is_ready: boolean;
  missing_dimensions: string[];
};

export type PromptInput = {
  session_id: string;
  topic: string;
  creation_intent: string;
  state: SessionState;
  transcript_turn_count: number;
  missing_dimensions: string[];
  suggested_focus: string;
  role_instruction: string;
  goal_instruction: string;
  strategy_instruction: string;
  boundary_instruction: string;
};

export type InterviewTurnResult = {
  project: SessionProject;
  readiness: Readiness;
  prompt_input: PromptInput;
  next_question: string | null;
  ai_can_finish: boolean;
};

export type GenerationResult = {
  project: SessionProject;
  provider: string;
  model: string;
};

export type AudioRenderResult = {
  project: SessionProject;
  provider: string;
  model: string;
  audio_path: string;
  transcript_path: string;
};
