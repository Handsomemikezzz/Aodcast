import { createId } from "./id";
import { ConfigureTTSInput, CreateSessionInput, DesktopBridge } from "./desktopBridge";
import { generateMockDraft } from "./generateDraft";
import { appendTurn, evaluateReadiness, nextQuestion, transcriptToText } from "./readiness";
import { nowIso } from "./time";
import { seededProjects } from "./mockData";
import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  ModelStatus,
  PromptInput,
  Readiness,
  SessionProject,
  TTSProviderConfig,
  TTSCapability,
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

function cloneProject(project: SessionProject): SessionProject {
  return JSON.parse(JSON.stringify(project)) as SessionProject;
}

export function createMockBridge(): DesktopBridge {
  const store = new Map(seededProjects.map((project) => [project.session.session_id, cloneProject(project)]));
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

  async function listProjects() {
    return Array.from(store.values())
      .map(cloneProject)
      .sort((left, right) => right.session.updated_at.localeCompare(left.session.updated_at));
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
    return cloneProject(project);
  }

  async function startInterview(sessionId: string) {
    const project = getProject(sessionId);
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

  async function submitReply(
    sessionId: string,
    message: string,
    userRequestedFinish = false,
  ) {
    const project = getProject(sessionId);
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
    const project = getProject(sessionId);
    project.session.state = "ready_to_generate";
    project.session.updated_at = nowIso();
    store.set(sessionId, project);
    return buildInterviewResult(project, null, true);
  }

  async function generateScript(sessionId: string) {
    const project = getProject(sessionId);
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
    };
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
    const project = getProject(sessionId);
    project.script = {
      ...project.script!,
      final: finalText,
      updated_at: nowIso(),
    };
    project.session.state = "script_edited";
    project.session.updated_at = nowIso();
    store.set(sessionId, project);
    return cloneProject(project);
  }

  async function renderAudio(sessionId: string) {
    const project = getProject(sessionId);
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
    return MOCK_MODELS.map((m) => ({ ...m }));
  }

  async function downloadModel() {
    return { message: "mock: use Tauri build to download via Python core." };
  }

  async function deleteModel() {
    return { message: "mock: no local files removed." };
  }

  return {
    listProjects,
    createSession,
    startInterview,
    submitReply,
    requestFinish,
    generateScript,
    renderAudio,
    saveEditedScript,
    getLocalTTSCapability,
    showTTSConfig,
    configureTTSProvider,
    listModelsStatus,
    downloadModel,
    deleteModel,
  };

  function getProject(sessionId: string) {
    const project = store.get(sessionId);
    if (!project) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    return project;
  }
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
