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
  deleted_at?: string | null;
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
  deleted_at?: string | null;
};

export type ScriptRevisionRecord = {
  revision_id: string;
  session_id: string;
  content: string;
  created_at: string;
  label?: string;
  kind?: string;
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

export type RequestState = {
  operation: string;
  phase: "running" | "cancelling" | "succeeded" | "failed" | "cancelled";
  progress_percent: number;
  message: string;
};

type BridgeResultMeta = {
  request_state?: RequestState;
};

export type InterviewTurnResult = BridgeResultMeta & {
  project: SessionProject;
  readiness: Readiness;
  prompt_input: PromptInput;
  next_question: string | null;
  ai_can_finish: boolean;
};

export type GenerationResult = BridgeResultMeta & {
  project: SessionProject;
  provider: string;
  model: string;
};

export type AudioRenderResult = BridgeResultMeta & {
  project: SessionProject;
  provider: string;
  model: string;
  audio_path: string;
  transcript_path: string;
  task_id?: string;
};

export type TTSCapability = {
  provider: string;
  runtime: string;
  platform: string;
  mlx_installed: boolean;
  mlx_audio_installed: boolean;
  model_path_configured: boolean;
  model_path_exists: boolean;
  available: boolean;
  reasons: string[];
  model_path: string;
  model_source: string;
  resolved_model: string;
  fallback_provider: string;
};

export type TTSProviderConfig = {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  voice: string;
  audio_format: string;
  local_runtime: string;
  local_model_path: string;
  local_ref_audio_path: string;
};

/** Voicebox-aligned model row from python-core `--list-models-status`. */
export type ModelStatus = {
  model_name: string;
  display_name: string;
  category: "voice";
  hf_repo_id?: string;
  downloaded: boolean;
  downloading: boolean;
  size_mb?: number;
  loaded: boolean;
};
