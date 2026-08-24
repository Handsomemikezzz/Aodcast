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
  creation_mode: "interview" | "markdown";
  state: SessionState;
  llm_provider: string;
  tts_provider: string;
  last_error: string;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  memory_mode?: "enabled" | "disabled";
  memory_processed_through_turn_id?: string;
  authorized_memory_ids?: string[];
  memory_usage_events?: { operation: string; memory_ids: string[]; used_at: string }[];
};

/** Lightweight interview routing metadata stored on transcript turns.
 *  Optional — legacy turns without this field load as-is. */
export type TranscriptTurnMetadata = {
  /** The readiness dimension being explored at the time of this turn. */
  interview_focus?: string;
  /** Role of this turn in the interview flow. */
  turn_role?: "question" | "answer" | "ready_message" | "revision_note" | "freeform";
  /** Prompt version that produced this agent turn, when available. */
  prompt_version?: string;
  /** Compact section ids for agent turns, for debugging. */
  prompt_section_ids?: string[];
};

export type TranscriptTurn = {
  speaker: Speaker;
  content: string;
  created_at: string;
  turn_id?: string;
  /** Optional — absent on turns saved before metadata support was added. */
  metadata?: TranscriptTurnMetadata;
};

export type TranscriptRecord = {
  session_id: string;
  turns: TranscriptTurn[];
};

export type ScriptRecord = {
  session_id: string;
  script_id: string;
  name: string;
  draft: string;
  final: string;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  generation_metadata?: {
    source?: {
      source_id: string;
      source_kind: "markdown";
      version: number;
      content_hash: string;
      conversion_mode: "adapt" | "narrate";
      target_length: "auto" | "short" | "standard" | "long";
    };
    [key: string]: unknown;
  };
};

export type EpisodeSourceRecord = {
  source_id: string;
  session_id: string;
  source_kind: "markdown";
  import_kind: "file" | "paste";
  name: string;
  title: string;
  raw_markdown: string;
  normalized_text: string;
  content_hash: string;
  version: number;
  word_count: number;
  estimated_audio_minutes: number;
  conversion_mode: "adapt" | "narrate";
  target_length: "auto" | "short" | "standard" | "long";
  focus_instructions: string;
  warnings: string[];
  created_at: string;
  updated_at: string;
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
  takes?: AudioTakeRecord[];
  final_take_id?: string;
  voice_settings?: VoiceRenderSettings;
  speaker_reference?: SpeakerReference | null;
  script_artifacts?: Record<string, ScriptArtifactRecord>;
};

export type ScriptArtifactRecord = {
  transcript_path?: string;
  audio_path?: string;
  provider?: string;
  takes?: AudioTakeRecord[];
  final_take_id?: string;
  voice_settings?: VoiceRenderSettings;
  speaker_reference?: SpeakerReference | null;
};

export type AudioTakeRecord = {
  take_id: string;
  session_id: string;
  script_id: string;
  speech_plan_id: string;
  render_id: string;
  audio_path: string;
  transcript_path: string;
  provider: string;
  model: string;
  voice_id: string;
  voice_name: string;
  style_id: string;
  style_name: string;
  speed: number;
  language: string;
  audio_format: string;
  created_at: string;
};

export type SessionProject = {
  session: SessionRecord;
  source: EpisodeSourceRecord | null;
  transcript: TranscriptRecord | null;
  script: ScriptRecord | null;
  artifact: ArtifactRecord | null;
  speech_plan: SpeechPlan | null;
  render_manifest: RenderManifest | null;
};

export type SpeechSourceSpan = {
  start: number;
  end: number;
};

export type SpeechDelivery = {
  intent: string;
  emotion: string;
  energy: number;
  pace: number;
};

export type SpeechBreak = {
  offset: number;
  duration_ms: number;
};

export type SpeechEmphasis = {
  start: number;
  end: number;
  level: "light" | "medium" | "strong";
};

export type SpeechPronunciation = {
  start: number;
  end: number;
  spoken_as: string;
};

export type SpeechSegment = {
  segment_id: string;
  position: number;
  text: string;
  text_hash: string;
  source_span: SpeechSourceSpan;
  delivery: SpeechDelivery;
  breaks: SpeechBreak[];
  emphasis: SpeechEmphasis[];
  pronunciations: SpeechPronunciation[];
  pause_after_ms: number;
  segment_hash: string;
};

export type SpeechPlan = {
  schema_version: 1;
  plan_id: string;
  version: number;
  session_id: string;
  script_id: string;
  script_hash: string;
  plan_hash: string;
  language: string;
  segments: SpeechSegment[];
  director_metadata: {
    prompt_version: string;
    provider: string;
    model: string;
  };
  created_at: string;
};

export type RenderPipelineStage = {
  stage: "speech_synthesis" | "voice_conversion";
  provider: string;
  model: string;
  adapter_version: string;
};

export type RenderSpeakerReferenceSnapshot = {
  speaker_reference_id: string;
  reference_hash: string;
  audio_path: string;
  audio_hash: string;
  reference_text: string;
  language: string;
};

export type RenderedSegment = {
  segment_artifact_id: string;
  segment_id: string;
  position: number;
  text_hash: string;
  segment_hash: string;
  audio_path: string;
  audio_hash: string;
  duration_ms: number;
  generated_by_render_id: string;
  seed: number | null;
};

export type RenderManifest = {
  schema_version: 1;
  render_id: string;
  session_id: string;
  script_id: string;
  script_hash: string;
  speech_plan: {
    plan_id: string;
    version: number;
    plan_hash: string;
  };
  speaker_reference: RenderSpeakerReferenceSnapshot | null;
  pipeline: RenderPipelineStage[];
  pipeline_hash: string;
  parent_render_id: string | null;
  regeneration: {
    mode: "context_window";
    target_segment_id: string;
    window_segment_ids: string[];
  } | null;
  segments: RenderedSegment[];
  assembly: {
    audio_format: "wav";
    sample_rate_hz: number;
    channels: 1 | 2;
    sample_width_bits: 16 | 24 | 32;
    target_rms_dbfs: number;
    peak_ceiling_dbfs: number;
    edge_fade_ms: number;
  };
  output: {
    audio_path: string;
    audio_hash: string;
    transcript_path: string;
    duration_ms: number;
  };
  created_at: string;
};

export type Readiness = {
  topic_context: boolean;
  core_viewpoint: boolean;
  example_or_detail: boolean;
  conclusion: boolean;
  is_ready: boolean;
  /** User answer count used for the script soft-offer floor. */
  user_turn_count?: number;
  meets_turn_floor?: boolean;
  /** True when content dims + turn floor allow soft-offering script generation. */
  can_offer_script?: boolean;
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
  run_token?: string;
  task_id?: string;
  audio_path?: string;
  provider?: string;
  model?: string;
  settings?: VoiceRenderSettings;
};

export type RuntimeInfo = {
  pid: number;
  started_at_unix: number;
  build_token: string;
};

type BridgeResultMeta = {
  request_state?: RequestState;
  runtime?: RuntimeInfo;
};

export type MemoryActionSignal =
  | "remember"
  | "correct"
  | "forget_candidates"
  | "none";

export type InterviewTurnResult = BridgeResultMeta & {
  project: SessionProject;
  readiness: Readiness;
  prompt_input: PromptInput;
  next_question: string | null;
  ai_can_finish: boolean;
  /** §10.5: memory control signal detected from this turn. */
  memory_action?: MemoryActionSignal;
  /** §10.3/§10.4: disambiguation candidates when target is ambiguous. */
  memory_action_candidates?: MemoryEntry[];
};

export type GenerationResult = BridgeResultMeta & {
  project: SessionProject;
  provider: string;
  model: string;
  script_id?: string;
};

export type AudioRenderResult = BridgeResultMeta & {
  project: SessionProject;
  provider: string;
  model: string;
  audio_path: string;
  transcript_path: string;
  task_id: string;
  run_token: string;
  affected_segment_ids: string[];
};

export type VoicePreset = {
  voice_id: string;
  name: string;
  description: string;
  scenario: string;
  tags: string[];
  provider_voice: string;
};

export type VoiceStylePreset = {
  style_id: string;
  name: string;
  prompt: string;
};

export type VoiceRenderSettings = {
  voice_id: string;
  voice_name?: string;
  style_id: string;
  style_name?: string;
  speed: number;
  language?: string;
  audio_format?: string;
  preview_text?: string;
};

export type SpeakerReference = {
  schema_version: 1;
  speaker_reference_id: string;
  name: string;
  source: "built_in" | "user_saved";
  audio_path: string;
  audio_hash: string;
  audio_format: string;
  duration_ms: number;
  reference_text: string;
  language: string;
  reference_hash: string;
  description?: string;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
};

export type VoicePresetCatalog = BridgeResultMeta & {
  voices: VoicePreset[];
  styles: VoiceStylePreset[];
  standard_preview_text: string;
};

export type VoicePreviewResult = BridgeResultMeta & {
  provider: string;
  model: string;
  audio_path: string;
  settings: VoiceRenderSettings;
};

export type TTSCapability = {
  provider: string;
  runtime: string;
  platform: string;
  architecture: string;
  mlx_installed: boolean;
  mlx_audio_installed: boolean;
  model_path_configured: boolean;
  model_path_exists: boolean;
  available: boolean;
  reasons: string[];
  model_path: string;
  model_source: string;
  resolved_model: string;
  model_family: string;
  model_variant: string;
  model_type: string;
  fallback_provider: string;
};

export type LLMProviderConfig = {
  provider: string;
  model: string;
  reasoning_effort: string;
  base_url: string;
  api_key: string;
};

export type LLMProviderModel = {
  id: string;
  display_name: string;
  is_default: boolean;
  default_reasoning_effort: string | null;
  supported_reasoning_efforts: string[];
};

export type LLMProviderStatus = {
  provider: "codex_subscription";
  installed: boolean;
  executable_path: string;
  version: string;
  authenticated: boolean;
  auth_mode: string | null;
  plan_type: string | null;
  account_email: string | null;
  models: LLMProviderModel[];
  rate_limit: {
    used_percent: number;
    window_duration_minutes: number | null;
    resets_at: number | null;
  } | null;
  message: string;
};

export type LLMAuthStartResult = {
  provider: "codex_subscription";
  login_id: string;
  auth_url: string;
};

export type LLMConfigPreflight = {
  ready: boolean;
  provider: string;
  missing_fields: string[];
  supported_actions: string[];
  message: string;
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

export type TTSModelSupportLevel = "native" | "approximated" | "unsupported";

export type TTSModelCapability = {
  schema_version: 1;
  provider: string;
  model: string;
  runtime: string;
  adapter_version: string;
  platforms: Array<"macos_apple_silicon" | "nvidia_cuda" | "remote_api">;
  languages: string[];
  reference_audio_formats: string[];
  output_audio_formats: string[];
  capabilities: {
    speaker_cloning: TTSModelSupportLevel;
    style_instruction: TTSModelSupportLevel;
    emotion: TTSModelSupportLevel;
    energy: TTSModelSupportLevel;
    pace: TTSModelSupportLevel;
    emphasis: TTSModelSupportLevel;
    explicit_breaks: TTSModelSupportLevel;
    pronunciation: TTSModelSupportLevel;
    deterministic_seed: TTSModelSupportLevel;
    text_context: TTSModelSupportLevel;
    audio_context: TTSModelSupportLevel;
    voice_conversion: TTSModelSupportLevel;
  };
  limits: {
    max_reference_duration_ms: number | null;
    max_segment_characters: number | null;
  };
};

/** Voice-generation model row from python-core `--list-models-status`. */
export type ModelStatus = {
  model_name: string;
  display_name: string;
  category: "voice";
  hf_repo_id?: string;
  family?: string;
  variant?: string;
  recommendation?: string;
  downloaded: boolean;
  downloading: boolean;
  size_mb?: number;
  loaded: boolean;
  active?: boolean;
  resident?: boolean;
  available?: boolean;
  unavailable_reason?: string;
  capability?: TTSModelCapability;
};

export type ModelStorageStatus = {
  current_base: string;
  default_base: string;
  custom_base: string;
  is_custom: boolean;
  exists: boolean;
};

export type MemoryType = "profile" | "experience" | "viewpoint" | "preference";

export type MemoryOrigin = "auto" | "explicit";

export type MemoryEvidence = {
  session_id: string;
  turn_id: string;
  observed_at: string;
  quote: string;
};

export type MemoryEntry = {
  id: string;
  name: string;
  description: string;
  type: MemoryType;
  origin: MemoryOrigin;
  sensitive: boolean;
  created_at: string;
  updated_at: string;
  last_used_at?: string | null;
  use_count: number;
  source_count: number;
  body?: string;
  keywords?: string[];
  evidence?: MemoryEvidence[];
};

export type MemorySettings = {
  first_run_acknowledged: boolean;
  writing_enabled: boolean;
  usage_enabled: boolean;
  last_maintenance_at: string | null;
  changes_since_maintenance: number;
};

export type MemoryWorkerState = {
  status: "idle" | "running" | "error";
  last_error: string;
  updated_at: string | null;
};

export type MemoryOverview = {
  settings: MemorySettings;
  worker: MemoryWorkerState;
  entry_count: number;
  pending_job_count: number;
  superseded_count: number;
};

export type MemoryUsageEvent = {
  session_id: string;
  session_topic: string;
  operation: string;
  memory_ids: string[];
  used_at: string;
};
