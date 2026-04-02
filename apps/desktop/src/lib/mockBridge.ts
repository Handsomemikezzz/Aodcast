import { createId } from "./id";
import { ConfigureTTSInput, CreateSessionInput, DesktopBridge, ListProjectsOptions, ShowSessionOptions } from "./desktopBridge";
import { generateMockDraft } from "./generateDraft";
import { appendTurn, evaluateReadiness, nextQuestion, transcriptToText } from "./readiness";
import { nowIso } from "./time";
import { seededProjects } from "./mockData";
import {
  InterviewTurnResult,
  ModelStatus,
  PromptInput,
  Readiness,
  RequestState,
  ScriptRevisionRecord,
  SessionProject,
  TTSProviderConfig,
} from "../types";

const MOCK_MODELS: ModelStatus[] = [
  {
    model_name: "qwen-tts-1.7B",
    display_name: "Qwen TTS 1.7B",
    category: "voice",
    hf_repo_id: "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
    downloaded: false,
    downloading: false,
    size_mb: 4.23 * 1024,
    loaded: false,
  },
  {
    model_name: "qwen-tts-0.6B",
    display_name: "Qwen TTS 0.6B",
    category: "voice",
    hf_repo_id: "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
    downloaded: false,
    downloading: false,
    size_mb: 4.23 * 1024,
    loaded: false,
  },
];

const RESTORE_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

function cloneProject(project: SessionProject): SessionProject {
  return JSON.parse(JSON.stringify(project)) as SessionProject;
}

function cloneRevisions(revisions: ScriptRevisionRecord[]): ScriptRevisionRecord[] {
  return JSON.parse(JSON.stringify(revisions)) as ScriptRevisionRecord[];
}

function isDeletedAt(value: string | null | undefined): value is string {
  return typeof value === "string" && value.length > 0;
}

function isWithinRestoreWindow(deletedAt: string): boolean {
  const deletedTime = Date.parse(deletedAt);
  if (Number.isNaN(deletedTime)) return false;
  return Date.now() - deletedTime <= RESTORE_WINDOW_MS;
}

function isSessionDeleted(project: SessionProject): boolean {
  return isDeletedAt(project.session.deleted_at);
}

function isScriptDeleted(project: SessionProject): boolean {
  return isDeletedAt(project.script?.deleted_at);
}

function sessionMatchesQuery(project: SessionProject, search: string): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  return [project.session.topic, project.session.creation_intent]
    .some((value) => value.toLowerCase().includes(needle));
}

function buildRevision(
  sessionId: string,
  content: string,
  kind: ScriptRevisionRecord["kind"],
  label?: string,
): ScriptRevisionRecord {
  return {
    revision_id: createId("revision"),
    session_id: sessionId,
    content,
    created_at: nowIso(),
    kind,
    label,
  };
}

function latestScriptContent(project: SessionProject): string {
  return project.script?.final?.trim() || project.script?.draft?.trim() || "";
}

function ensureProjectExists(store: Map<string, SessionProject>, sessionId: string): SessionProject {
  const project = store.get(sessionId);
  if (!project) {
    throw new Error(`Unknown session '${sessionId}'.`);
  }
  return project;
}

function ensureActiveSession(project: SessionProject): void {
  if (isSessionDeleted(project)) {
    throw new Error("This session is in trash. Restore it before continuing.");
  }
}

function ensureEditableScript(project: SessionProject): void {
  ensureActiveSession(project);
  if (!project.script) {
    throw new Error("This session has no script record.");
  }
  if (isScriptDeleted(project)) {
    throw new Error("This script is in trash. Restore it before editing.");
  }
}

export function createMockBridge(): DesktopBridge {
  const store = new Map<string, SessionProject>();
  const revisionsBySession = new Map<string, ScriptRevisionRecord[]>();
  const taskStates = new Map<string, RequestState>();

  for (const project of seededProjects) {
    const cloned = cloneProject(project);
    store.set(cloned.session.session_id, cloned);

    const content = latestScriptContent(cloned);
    if (content) {
      revisionsBySession.set(
        cloned.session.session_id,
        [buildRevision(cloned.session.session_id, content, "generated", "Seeded script")],
      );
    } else {
      revisionsBySession.set(cloned.session.session_id, []);
    }
  }

  let ttsConfig: TTSProviderConfig = {
    provider: "mock_remote",
    model: "mock-voice",
    base_url: "",
    api_key: "",
    voice: "alloy",
    audio_format: "wav",
    local_runtime: "mlx",
    local_model_path: "",
    local_ref_audio_path: "",
  };

  async function listProjects(options?: ListProjectsOptions) {
    const search = options?.search?.trim() ?? "";
    const includeDeleted = options?.includeDeleted ?? false;

    return Array.from(store.values())
      .filter((project) => {
        if (!includeDeleted && isSessionDeleted(project)) {
          return false;
        }
        return sessionMatchesQuery(project, search);
      })
      .sort((left, right) => right.session.updated_at.localeCompare(left.session.updated_at))
      .map(cloneProject);
  }

  async function createSession(input: CreateSessionInput) {
    const sessionId = createId("session");
    const now = nowIso();
    const project: SessionProject = {
      session: {
        session_id: sessionId,
        topic: input.topic,
        creation_intent: input.creationIntent,
        state: "topic_defined",
        llm_provider: "",
        tts_provider: "",
        last_error: "",
        created_at: now,
        updated_at: now,
        deleted_at: null,
      },
      transcript: {
        session_id: sessionId,
        turns: [],
      },
      script: {
        session_id: sessionId,
        draft: "",
        final: "",
        updated_at: now,
        deleted_at: null,
      },
      artifact: {
        session_id: sessionId,
        transcript_path: `sessions/${sessionId}/transcript.json`,
        audio_path: "",
        provider: "",
        created_at: now,
      },
    };
    store.set(sessionId, project);
    revisionsBySession.set(sessionId, []);
    return cloneProject(project);
  }

  async function showSession(sessionId: string, options?: ShowSessionOptions) {
    const project = ensureProjectExists(store, sessionId);
    if (isSessionDeleted(project) && !options?.includeDeleted) {
      throw new Error(`Session '${sessionId}' is in trash.`);
    }
    return cloneProject(project);
  }

  async function renameSession(sessionId: string, topic: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureActiveSession(project);
    project.session.topic = topic.trim() || project.session.topic;
    project.session.updated_at = nowIso();
    store.set(sessionId, project);
    return cloneProject(project);
  }

  async function deleteSession(sessionId: string) {
    const project = ensureProjectExists(store, sessionId);
    if (isSessionDeleted(project)) {
      return cloneProject(project);
    }
    project.session.deleted_at = nowIso();
    project.session.updated_at = project.session.deleted_at;
    store.set(sessionId, project);
    return cloneProject(project);
  }

  async function restoreSession(sessionId: string) {
    const project = ensureProjectExists(store, sessionId);
    if (!isSessionDeleted(project)) {
      return cloneProject(project);
    }
    if (!project.session.deleted_at || !isWithinRestoreWindow(project.session.deleted_at)) {
      throw new Error("Session restore window has expired.");
    }
    project.session.deleted_at = null;
    project.session.updated_at = nowIso();
    store.set(sessionId, project);
    return cloneProject(project);
  }

  async function startInterview(sessionId: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureActiveSession(project);
    const transcript = project.transcript!;
    if (transcript.turns.length === 0) {
      const question = nextQuestion(project.session.topic, [
        "topic_context",
        "core_viewpoint",
        "example_or_detail",
        "conclusion",
      ]);
      transcript.turns.push({
        speaker: "agent",
        content: question,
        created_at: nowIso(),
      });
      project.session.state = "interview_in_progress";
      project.session.updated_at = nowIso();
      store.set(sessionId, project);
      return buildInterviewResult(project, question, false);
    }

    const readiness = evaluateReadiness(project.transcript);
    return buildInterviewResult(project, null, readiness.is_ready);
  }

  async function submitReply(sessionId: string, message: string, userRequestedFinish = false) {
    const project = ensureProjectExists(store, sessionId);
    ensureActiveSession(project);
    const transcript = project.transcript!;
    project.session.state = "interview_in_progress";
    project.session.updated_at = nowIso();
    project.transcript = appendTurn(transcript, "user", message, nowIso());
    project.session.state = "readiness_evaluation";

    const readiness = evaluateReadiness(project.transcript);
    if (userRequestedFinish || readiness.is_ready) {
      project.session.state = "ready_to_generate";
      project.session.updated_at = nowIso();
      store.set(sessionId, project);
      return buildInterviewResult(project, null, true);
    }

    project.session.state = "interview_in_progress";
    project.session.updated_at = nowIso();
    const question = nextQuestion(project.session.topic, readiness.missing_dimensions);
    project.transcript = appendTurn(project.transcript!, "agent", question, nowIso());
    store.set(sessionId, project);
    return buildInterviewResult(project, question, false);
  }

  async function requestFinish(sessionId: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureActiveSession(project);
    project.session.state = "ready_to_generate";
    project.session.updated_at = nowIso();
    store.set(sessionId, project);
    return buildInterviewResult(project, null, true);
  }

  async function generateScript(sessionId: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureEditableScript(project);
    if (project.session.state !== "ready_to_generate" && project.session.state !== "failed") {
      throw new Error("Session must be ready to generate before drafting.");
    }

    const draft = generateMockDraft(
      project.session.topic,
      project.session.creation_intent,
      transcriptToText(project.transcript),
    );
    project.script = {
      ...project.script!,
      draft,
      final: project.script?.final?.trim() ? project.script.final : draft,
      updated_at: nowIso(),
      deleted_at: null,
    };
    revisionsBySession.set(
      sessionId,
      [...(revisionsBySession.get(sessionId) ?? []), buildRevision(sessionId, draft, "generated", "Generated draft")],
    );
    project.session.state = "script_generated";
    project.session.llm_provider = "mock";
    project.session.last_error = "";
    project.session.updated_at = nowIso();
    store.set(sessionId, project);

    return {
      project: cloneProject(project),
      provider: "mock",
      model: "mock-solo-writer",
    };
  }

  async function saveEditedScript(sessionId: string, finalText: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureEditableScript(project);
    project.script = {
      ...project.script!,
      draft: project.script?.draft || finalText,
      final: finalText,
      updated_at: nowIso(),
      deleted_at: null,
    };
    revisionsBySession.set(
      sessionId,
      [...(revisionsBySession.get(sessionId) ?? []), buildRevision(sessionId, finalText, "edited", "Saved edit")],
    );
    project.session.state = "script_edited";
    project.session.updated_at = nowIso();
    store.set(sessionId, project);
    return cloneProject(project);
  }

  async function deleteScript(sessionId: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureActiveSession(project);
    if (!project.script) {
      throw new Error("This session has no script record.");
    }
    if (isScriptDeleted(project)) {
      return cloneProject(project);
    }
    project.script.deleted_at = nowIso();
    project.script.updated_at = project.script.deleted_at;
    store.set(sessionId, project);
    return cloneProject(project);
  }

  async function restoreScript(sessionId: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureActiveSession(project);
    if (!project.script) {
      throw new Error("This session has no script record.");
    }
    if (!isScriptDeleted(project)) {
      return cloneProject(project);
    }
    if (!project.script.deleted_at || !isWithinRestoreWindow(project.script.deleted_at)) {
      throw new Error("Script restore window has expired.");
    }
    project.script.deleted_at = null;
    project.script.updated_at = nowIso();
    store.set(sessionId, project);
    return cloneProject(project);
  }

  async function listScriptRevisions(sessionId: string) {
    ensureProjectExists(store, sessionId);
    return cloneRevisions(revisionsBySession.get(sessionId) ?? []);
  }

  async function rollbackScriptRevision(sessionId: string, revisionId: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureEditableScript(project);
    const revisions = revisionsBySession.get(sessionId) ?? [];
    const revision = revisions.find((entry) => entry.revision_id === revisionId);
    if (!revision) {
      throw new Error(`Unknown revision '${revisionId}'.`);
    }

    project.script = {
      ...project.script!,
      draft: revision.content,
      final: revision.content,
      updated_at: nowIso(),
      deleted_at: null,
    };
    revisionsBySession.set(
      sessionId,
      [...revisions, buildRevision(sessionId, revision.content, "rollback", "Rollback revision")],
    );
    project.session.state = "script_edited";
    project.session.updated_at = nowIso();
    store.set(sessionId, project);
    return cloneProject(project);
  }

  async function renderAudio(sessionId: string) {
    const project = ensureProjectExists(store, sessionId);
    ensureEditableScript(project);
    if (
      project.session.state !== "script_generated" &&
      project.session.state !== "script_edited" &&
      project.session.state !== "failed"
    ) {
      throw new Error("Audio rendering requires a generated or edited script.");
    }

    const now = nowIso();
    project.session.state = "audio_rendering";
    project.session.updated_at = now;
    const basePath = `exports/${sessionId}`;
    project.artifact = {
      ...project.artifact!,
      provider: "mock_remote",
      transcript_path: `${basePath}/transcript.txt`,
      audio_path: `${basePath}/audio.wav`,
      created_at: now,
    };
    project.session.tts_provider = "mock_remote";
    project.session.last_error = "";
    project.session.state = "completed";
    project.session.updated_at = nowIso();
    store.set(sessionId, project);

    return {
      project: cloneProject(project),
      provider: "mock_remote",
      model: "mock-voice",
      audio_path: project.artifact.audio_path,
      transcript_path: project.artifact.transcript_path,
    };
  }

  async function getLocalTTSCapability() {
    return {
      provider: "local_mlx",
      runtime: "mlx",
      platform: "darwin",
      mlx_installed: false,
      mlx_audio_installed: false,
      model_path_configured: false,
      model_path_exists: false,
      available: false,
      reasons: [
        "Mock bridge is active, so no native MLX runtime is attached yet.",
        "Configure a local model path and install the Python mlx package before switching to the real bridge.",
      ],
      model_path: "",
      model_source: "mock",
      resolved_model: "",
      fallback_provider: "mock_remote",
    };
  }

  async function showTTSConfig() {
    return { ...ttsConfig };
  }

  async function configureTTSProvider(input: ConfigureTTSInput) {
    ttsConfig = {
      ...ttsConfig,
      provider: input.provider,
      model: input.model,
      base_url: input.base_url,
      api_key: input.api_key,
      voice: input.voice,
      audio_format: input.audio_format,
      local_runtime: input.local_runtime,
      local_model_path: input.local_model_path,
    };
    return { ...ttsConfig };
  }

  async function listModelsStatus() {
    return MOCK_MODELS.map((model) => ({ ...model }));
  }

  async function downloadModel(modelName: string) {
    const taskId = `download_model:${modelName}`;
    taskStates.set(taskId, {
      operation: "download_model",
      phase: "running",
      progress_percent: 10,
      message: `Downloading model ${modelName}...`,
    });
    await new Promise((resolve) => window.setTimeout(resolve, 300));
    const current = taskStates.get(taskId);
    if (current?.phase === "cancelling" || current?.phase === "cancelled") {
      const cancelledState: RequestState = {
        operation: "download_model",
        phase: "cancelled",
        progress_percent: current.progress_percent,
        message: `Download cancelled for ${modelName}.`,
      };
      taskStates.set(taskId, cancelledState);
      return {
        message: "mock: model download cancelled.",
        task_id: taskId,
        request_state: cancelledState,
      };
    }
    return {
      message: "mock: model download finished.",
      task_id: taskId,
      request_state: (() => {
        const doneState: RequestState = {
          operation: "download_model",
          phase: "succeeded",
          progress_percent: 100,
          message: `Model ${modelName} is ready.`,
        };
        taskStates.set(taskId, doneState);
        return doneState;
      })(),
    };
  }

  async function deleteModel() {
    return { message: "mock: no local files removed." };
  }

  async function showTaskState(taskId: string) {
    return taskStates.get(taskId) ?? null;
  }

  async function cancelTask(taskId: string) {
    const current = taskStates.get(taskId);
    if (!current) return null;
    if (current.phase === "succeeded" || current.phase === "failed" || current.phase === "cancelled") {
      return current;
    }
    if (current.phase === "cancelling") {
      return current;
    }
    const cancelling: RequestState = {
      ...current,
      phase: "cancelling",
      message: `Cancellation requested for ${taskId}.`,
    };
    taskStates.set(taskId, cancelling);
    return cancelling;
  }

  return {
    listProjects,
    createSession,
    showSession,
    renameSession,
    deleteSession,
    restoreSession,
    startInterview,
    submitReply,
    requestFinish,
    generateScript,
    renderAudio,
    saveEditedScript,
    deleteScript,
    restoreScript,
    listScriptRevisions,
    rollbackScriptRevision,
    getLocalTTSCapability,
    showTTSConfig,
    configureTTSProvider,
    listModelsStatus,
    downloadModel,
    deleteModel,
    showTaskState,
    cancelTask,
  };
}

function buildInterviewResult(
  project: SessionProject,
  nextQuestion: string | null,
  aiCanFinish: boolean,
): InterviewTurnResult {
  const readiness = evaluateReadiness(project.transcript);
  const promptInput: PromptInput = {
    session_id: project.session.session_id,
    topic: project.session.topic,
    creation_intent: project.session.creation_intent,
    state: project.session.state,
    transcript_turn_count: project.transcript?.turns.length ?? 0,
    missing_dimensions: readiness.missing_dimensions,
    suggested_focus: readiness.missing_dimensions[0] ?? "ready_to_generate",
    role_instruction:
      "You are a perceptive podcast interviewer helping the user clarify a real point of view.",
    goal_instruction:
      "Gather enough material for a solo podcast script with a hook, a clear argument, supporting detail, and a conclusion.",
    strategy_instruction:
      "Ask one high-value follow-up that fills the most important missing dimension first.",
    boundary_instruction:
      "Do not invent user details, ask multiple unrelated questions at once, or switch into long-form script writing.",
  };

  return {
    project: cloneProject(project),
    readiness: readiness as Readiness,
    prompt_input: promptInput,
    next_question: nextQuestion,
    ai_can_finish: aiCanFinish,
  };
}
