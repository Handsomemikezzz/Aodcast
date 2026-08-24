import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { resolveAudioFileUrl } from "../../lib/audioFile";
import type { DesktopBridge, LongTaskHandle } from "../../lib/desktopBridge";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  isActiveRequestState,
  isTerminalRequestState,
  keepCancellationProgress,
  requestStateRunToken,
  withRequestStateFallback,
} from "../../lib/requestState";
import { revealInFinder } from "../../lib/shellOps";
import { analyzeSpokenScript } from "./spokenScriptChecks";
import type {
  AudioRenderResult,
  RequestState,
  RuntimeInfo,
  SessionProject,
  VoiceRenderSettings,
} from "../../types";

const POLL_INTERVAL_MS = 1000;
const POLL_FAILURE_THRESHOLD = 3;
const EXPORT_MP3_FORMAT = "mp3";
const EXPORT_MP3_BITRATE = "192k";

type UseScriptWorkbenchAudioArgs = {
  bridge: DesktopBridge;
  sessionId: string;
  scriptId: string;
  onRefresh: () => Promise<void>;
  refreshProject: () => Promise<SessionProject>;
  project: SessionProject | null;
  setProject: (project: SessionProject) => void;
  selectedEngine: "local_mlx" | "cloud";
  cloudProvider: string;
  selectedModelId: string;
  voiceSettings: VoiceRenderSettings;
};

type UseScriptWorkbenchAudioResult = {
  generating: boolean;
  audioError: string | null;
  audioRequestState: RequestState | null;
  pollWarning: string | null;
  audioMessage: string | null;
  affectedSegmentIds: string[];
  isAudioPlaying: boolean;
  audioRef: RefObject<HTMLAudioElement>;
  audioSrc: string;
  previewing: boolean;
  previewError: string | null;
  previewRequestState: RequestState | null;
  previewSrc: string;
  previewAudioRef: RefObject<HTMLAudioElement>;
  triggerRenderAudio: (options?: { scriptToRender?: string }) => Promise<void>;
  triggerVoicePreview: (previewText: string) => Promise<void>;
  triggerRegenerateAudioWindow: (targetSegmentId: string) => Promise<void>;
  handleCancelAudio: () => Promise<void>;
  handleCancelPreview: () => Promise<void>;
  handlePreviewAudio: () => Promise<void>;
  handleAudioLoadError: () => void;
  handleRevealInFinder: () => Promise<void>;
  handleExportMp3: () => Promise<void>;
  handleDeleteAudio: () => Promise<void>;
  exportingMp3: boolean;
};

function taskHandleFromResult(result: AudioRenderResult): LongTaskHandle {
  if (!result.task_id || !result.run_token) {
    throw new Error("Audio rendering could not start. Please try again.");
  }
  return { taskId: result.task_id, runToken: result.run_token };
}

function taskStateForResult(result: AudioRenderResult): RequestState {
  return {
    ...(result.request_state ?? buildRequestState("render_audio", "running", "Rendering audio...")),
    task_id: result.task_id,
    run_token: result.run_token,
  };
}

export function useScriptWorkbenchAudio({
  bridge,
  sessionId,
  scriptId,
  onRefresh,
  refreshProject,
  project,
  setProject,
  selectedEngine,
  cloudProvider,
  selectedModelId,
  voiceSettings,
}: UseScriptWorkbenchAudioArgs): UseScriptWorkbenchAudioResult {
  const audioRef = useRef<HTMLAudioElement>(null);
  const previewAudioRef = useRef<HTMLAudioElement>(null);
  const pollHandleRef = useRef<number | null>(null);
  const pollingInFlightRef = useRef(false);
  const pollFailureCountRef = useRef(0);
  const activeTaskRef = useRef<LongTaskHandle | null>(null);
  const previewTaskRef = useRef<LongTaskHandle | null>(null);
  const previewRequestTokenRef = useRef(0);
  const taskId = `render_audio:${sessionId}:${scriptId}`;

  const [generating, setGenerating] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [audioRequestState, setAudioRequestState] = useState<RequestState | null>(null);
  const [pollWarning, setPollWarning] = useState<string | null>(null);
  const [audioMessage, setAudioMessage] = useState<string | null>(null);
  const [affectedSegmentIds, setAffectedSegmentIds] = useState<string[]>([]);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [exportingMp3, setExportingMp3] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewRequestState, setPreviewRequestState] = useState<RequestState | null>(null);
  const [previewSrc, setPreviewSrc] = useState("");

  const audioPath = project?.render_manifest?.output.audio_path || project?.artifact?.audio_path || "";
  const audioSrc = useMemo(() => (audioPath ? resolveAudioFileUrl(audioPath) : ""), [audioPath]);
  const speakerReference = project?.artifact?.script_artifacts?.[scriptId]?.speaker_reference
    ?? project?.artifact?.speaker_reference;
  const previewInputKey = JSON.stringify({
    engine: selectedEngine,
    model: selectedModelId,
    reference: speakerReference?.speaker_reference_id ?? "",
    style: voiceSettings.style_id,
    speed: voiceSettings.speed,
  });

  useEffect(() => {
    previewRequestTokenRef.current += 1;
    previewTaskRef.current = null;
    setPreviewing(false);
    setPreviewError(null);
    setPreviewRequestState(null);
    setPreviewSrc("");
  }, [previewInputKey]);

  const stopTaskPolling = () => {
    if (pollHandleRef.current !== null) {
      window.clearInterval(pollHandleRef.current);
      pollHandleRef.current = null;
    }
    pollingInFlightRef.current = false;
    pollFailureCountRef.current = 0;
  };

  const runtimeLabel = (runtime: RuntimeInfo): string => {
    const startedAt = new Date(runtime.started_at_unix * 1000).toLocaleString();
    return `runtime pid=${runtime.pid}, started=${startedAt}, build=${runtime.build_token.slice(0, 8)}`;
  };

  const runtimeLabelFromError = (error: unknown): string | null => {
    if (typeof error !== "object" || error === null) return null;
    const candidate = error as { runtime?: RuntimeInfo; details?: { runtime?: RuntimeInfo } };
    const runtime = candidate.runtime ?? candidate.details?.runtime;
    if (
      runtime
      && typeof runtime.pid === "number"
      && typeof runtime.started_at_unix === "number"
      && typeof runtime.build_token === "string"
    ) {
      return runtimeLabel(runtime);
    }
    return null;
  };

  const refreshRenderedAudio = async () => {
    await Promise.allSettled([onRefresh(), refreshProject()]);
  };

  const acceptPolledState = (state: RequestState | null, expected: LongTaskHandle): boolean => {
    const active = activeTaskRef.current;
    if (!active || active.taskId !== expected.taskId || active.runToken !== expected.runToken) return false;
    if (!state) return false;
    if (state.run_token !== expected.runToken) {
      stopTaskPolling();
      activeTaskRef.current = null;
      setGenerating(false);
      setPollWarning("A newer render replaced this task. The workspace has been refreshed.");
      void refreshProject();
      return false;
    }
    setAudioRequestState((previous) => keepCancellationProgress(previous, state));
    void refreshProject().catch(() => undefined);
    if (isTerminalRequestState(state)) {
      stopTaskPolling();
      activeTaskRef.current = null;
      setGenerating(false);
      setAffectedSegmentIds([]);
      if (state.phase === "succeeded") {
        setAudioError(null);
        void refreshRenderedAudio();
      } else if (state.phase === "failed") {
        setAudioError(state.message || "Audio rendering failed.");
      } else if (state.phase === "cancelled") {
        setAudioError(null);
        setAudioMessage("Render cancelled.");
      }
    } else {
      setGenerating(true);
    }
    return true;
  };

  const pollOnce = () => {
    const expected = activeTaskRef.current;
    if (!expected || pollingInFlightRef.current) return;
    pollingInFlightRef.current = true;
    void bridge
      .showTaskState(expected.taskId)
      .then((state) => {
        pollFailureCountRef.current = 0;
        setPollWarning(null);
        acceptPolledState(state, expected);
      })
      .catch((err: unknown) => {
        pollFailureCountRef.current += 1;
        if (pollFailureCountRef.current >= POLL_FAILURE_THRESHOLD) {
          setPollWarning(getErrorMessage(err, "Lost connection to the rendering runtime."));
        }
      })
      .finally(() => {
        pollingInFlightRef.current = false;
      });
  };

  const startTaskPolling = () => {
    if (pollHandleRef.current !== null) return;
    pollFailureCountRef.current = 0;
    setPollWarning(null);
    pollHandleRef.current = window.setInterval(pollOnce, POLL_INTERVAL_MS);
  };

  useEffect(() => {
    stopTaskPolling();
    activeTaskRef.current = null;
    setAffectedSegmentIds([]);
    void bridge
      .showTaskState(taskId)
      .then((state) => {
        const runToken = requestStateRunToken(state);
        if (!state || !runToken || !isActiveRequestState(state)) {
          setGenerating(false);
          return;
        }
        activeTaskRef.current = { taskId, runToken };
        setAudioRequestState(state);
        setGenerating(true);
        startTaskPolling();
      })
      .catch(() => undefined);
    return () => {
      stopTaskPolling();
      activeTaskRef.current = null;
    };
  }, [taskId]);

  useEffect(() => {
    const audioElement = audioRef.current;
    if (!audioElement) return undefined;
    const syncPlayback = () => setIsAudioPlaying(!audioElement.paused);
    audioElement.addEventListener("play", syncPlayback);
    audioElement.addEventListener("pause", syncPlayback);
    audioElement.addEventListener("ended", syncPlayback);
    return () => {
      audioElement.removeEventListener("play", syncPlayback);
      audioElement.removeEventListener("pause", syncPlayback);
      audioElement.removeEventListener("ended", syncPlayback);
    };
  }, [audioPath]);

  const beginTask = (result: AudioRenderResult) => {
    stopTaskPolling();
    const handle = taskHandleFromResult(result);
    activeTaskRef.current = handle;
    setProject(result.project);
    setAffectedSegmentIds(result.affected_segment_ids ?? []);
    setAudioRequestState(taskStateForResult(result));
    setGenerating(true);
    startTaskPolling();
    pollOnce();
  };

  const prepareRender = async (scriptToRender?: string): Promise<SessionProject | null> => {
    if (scriptToRender !== undefined) {
      const renderCheck = analyzeSpokenScript(scriptToRender);
      if (!renderCheck.canRender) {
        setAudioError(renderCheck.blockingSummary || "Fix blocking script issues before generating audio.");
        setAudioMessage(null);
        setAudioRequestState(null);
        return null;
      }
    }
    const currentTask = activeTaskRef.current;
    if (currentTask) {
      const state = await bridge.showTaskState(currentTask.taskId).catch(() => null);
      if (state?.run_token === currentTask.runToken && isActiveRequestState(state)) {
        setGenerating(true);
        startTaskPolling();
        return null;
      }
    }
    let renderProject = project;
    const renderSpeakerReference = renderProject?.artifact?.script_artifacts?.[scriptId]?.speaker_reference
      ?? renderProject?.artifact?.speaker_reference;
    if (selectedEngine === "local_mlx" && !selectedModelId) {
      setAudioError("请先选择一个已安装的本地语音模型。");
      setAudioMessage(null);
      setAudioRequestState(null);
      return null;
    }
    if (selectedEngine === "local_mlx" && !renderSpeakerReference?.speaker_reference_id) {
      setAudioError("Choose a voice in this episode before generating audio.");
      setAudioMessage(null);
      setAudioRequestState(null);
      return null;
    }
    if (renderSpeakerReference?.speaker_reference_id) {
      renderProject = await bridge.selectSpeakerReference(sessionId, scriptId, renderSpeakerReference.speaker_reference_id);
      setProject(renderProject);
    }
    return renderProject;
  };

  const triggerRenderAudio = async (options?: { scriptToRender?: string }) => {
    try {
      const renderProject = await prepareRender(options?.scriptToRender);
      if (!renderProject) return;
      setAudioError(null);
      setAudioMessage(null);
      setAudioRequestState(buildRequestState("render_audio", "running", "Preparing speech plan..."));
      setGenerating(true);
      const result = await bridge.renderAudio(sessionId, {
        providerOverride: selectedEngine === "local_mlx" ? "local_mlx" : cloudProvider,
        modelId: selectedEngine === "local_mlx" ? selectedModelId : undefined,
        scriptId,
        voiceSettings,
        requireSpeakerReference: selectedEngine === "local_mlx",
      });
      beginTask(result);
      await onRefresh();
    } catch (err: unknown) {
      const errorState = getErrorRequestState(err);
      const runtimeHint = runtimeLabelFromError(err);
      const baseMessage = getErrorMessage(err, "Failed to render audio.");
      setAudioError(errorState?.phase === "cancelled" ? null : runtimeHint ? `${baseMessage} (${runtimeHint})` : baseMessage);
      setAudioRequestState(withRequestStateFallback(errorState, buildRequestState("render_audio", "failed", baseMessage)));
      setGenerating(false);
      activeTaskRef.current = null;
      stopTaskPolling();
    }
  };

  const triggerVoicePreview = async (previewText: string) => {
    const text = previewText.trim();
    if (!text) {
      setPreviewError("Add some script text before previewing.");
      return;
    }
    if (!speakerReference?.speaker_reference_id) {
      setPreviewError("Choose a voice before previewing this passage.");
      return;
    }
    if (selectedEngine === "local_mlx" && !selectedModelId) {
      setPreviewError("Choose an installed voice model before previewing.");
      return;
    }

    const requestToken = previewRequestTokenRef.current + 1;
    previewRequestTokenRef.current = requestToken;
    const isCurrentRequest = () => previewRequestTokenRef.current === requestToken;

    try {
      setPreviewing(true);
      setPreviewError(null);
      setPreviewSrc("");
      setPreviewRequestState(buildRequestState("render_voice_preview", "running", "Preparing preview..."));
      const result = await bridge.renderVoicePreview(
        { ...voiceSettings, preview_text: text },
        {
          sessionId,
          scriptId,
          providerOverride: selectedEngine === "local_mlx" ? "local_mlx" : cloudProvider,
          modelId: selectedEngine === "local_mlx" ? selectedModelId : undefined,
          speakerReferenceId: speakerReference.speaker_reference_id,
          onState: (state) => {
            if (isCurrentRequest()) setPreviewRequestState(state);
          },
          onTaskStarted: (handle) => {
            if (isCurrentRequest()) previewTaskRef.current = handle;
          },
        },
      );
      if (!isCurrentRequest()) return;
      setPreviewRequestState(result.request_state ?? null);
      setPreviewSrc(resolveAudioFileUrl(result.audio_path));
      window.setTimeout(() => {
        if (isCurrentRequest()) void previewAudioRef.current?.play().catch(() => undefined);
      }, 100);
    } catch (err: unknown) {
      if (!isCurrentRequest()) return;
      const message = getErrorMessage(err, "Failed to render this preview.");
      setPreviewError(/cancel/i.test(message) ? null : message);
      setPreviewRequestState(null);
    } finally {
      if (isCurrentRequest()) {
        previewTaskRef.current = null;
        setPreviewing(false);
      }
    }
  };

  const triggerRegenerateAudioWindow = async (targetSegmentId: string) => {
    const plan = project?.speech_plan;
    const manifest = project?.render_manifest;
    if (!plan || !manifest) {
      setAudioError("请先生成完整音频，再进行局部重生成。");
      return;
    }
    try {
      setAudioError(null);
      setAudioMessage(null);
      setGenerating(true);
      const result = await bridge.regenerateAudioWindow(sessionId, scriptId, targetSegmentId, {
        speechPlanId: plan.plan_id,
        renderManifestId: manifest.render_id,
      });
      beginTask(result);
      await onRefresh();
    } catch (err: unknown) {
      const errorState = getErrorRequestState(err);
      const message = getErrorMessage(err, "Failed to regenerate the speech window.");
      setAudioError(message);
      setAudioRequestState(withRequestStateFallback(errorState, buildRequestState("regenerate_audio_window", "failed", message)));
      setGenerating(false);
      activeTaskRef.current = null;
      stopTaskPolling();
    }
  };

  const handleCancelAudio = async () => {
    const handle = activeTaskRef.current;
    if (!handle) return;
    try {
      const state = await bridge.cancelTask(handle.taskId, handle.runToken);
      const nextState =
        state ?? {
          ...buildRequestState("render_audio", "cancelling", "Cancellation requested."),
          task_id: handle.taskId,
          run_token: handle.runToken,
        };
      setAudioRequestState(nextState);
      // Orphaned workers finalize to cancelled/failed immediately — clear the spinner now.
      if (isTerminalRequestState(nextState)) {
        stopTaskPolling();
        activeTaskRef.current = null;
        setGenerating(false);
        setAffectedSegmentIds([]);
        if (nextState.phase === "cancelled") {
          setAudioError(null);
          setAudioMessage("Render cancelled.");
        } else if (nextState.phase === "failed") {
          setAudioError(nextState.message || "Render failed.");
        }
        void refreshProject().catch(() => undefined);
      } else {
        setGenerating(true);
        startTaskPolling();
        pollOnce();
      }
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to request cancellation."));
    }
  };

  const handleCancelPreview = async () => {
    const handle = previewTaskRef.current;
    if (!handle) return;
    try {
      const state = await bridge.cancelTask(handle.taskId, handle.runToken);
      if (state) setPreviewRequestState(state);
    } catch (err: unknown) {
      setPreviewError(getErrorMessage(err, "Failed to cancel the preview."));
    }
  };

  const handlePreviewAudio = async () => {
    const audioElement = audioRef.current;
    if (!audioElement || !audioSrc) return;
    try {
      if (audioElement.paused) await audioElement.play();
      else audioElement.pause();
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to preview audio."));
    }
  };

  const handleAudioLoadError = () => {
    setAudioError("无法加载音频文件。文件可能已移动或删除，请重新生成音频。");
  };

  const handleRevealInFinder = async () => {
    if (!audioPath) return;
    try {
      await revealInFinder(audioPath);
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to reveal audio in Finder."));
    }
  };

  const handleDeleteAudio = async () => {
    if (!audioPath) return;
    try {
      setAudioError(null);
      const updated = await bridge.deleteGeneratedAudio(sessionId, { scriptId: project?.script?.script_id });
      setProject(updated);
      setAudioRequestState(null);
      setAudioMessage("Audio artifact deleted.");
      await onRefresh();
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to delete audio."));
    }
  };

  const handleExportMp3 = async () => {
    if (!audioPath || exportingMp3) return;
    setExportingMp3(true);
    setAudioError(null);
    setAudioMessage(null);
    try {
      const result = await bridge.exportPodcastAudio(audioPath, EXPORT_MP3_FORMAT, EXPORT_MP3_BITRATE, "");
      try {
        await revealInFinder(result.audio_path);
        setAudioMessage(`MP3 已导出：${result.file_name}`);
      } catch {
        setAudioMessage(`MP3 已导出到 ${result.audio_path}`);
      }
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to export MP3."));
    } finally {
      setExportingMp3(false);
    }
  };

  return {
    generating,
    audioError,
    audioRequestState,
    pollWarning,
    audioMessage,
    affectedSegmentIds,
    isAudioPlaying,
    audioRef,
    audioSrc,
    previewing,
    previewError,
    previewRequestState,
    previewSrc,
    previewAudioRef,
    triggerRenderAudio,
    triggerVoicePreview,
    triggerRegenerateAudioWindow,
    handleCancelAudio,
    handleCancelPreview,
    handlePreviewAudio,
    handleAudioLoadError,
    handleRevealInFinder,
    handleExportMp3,
    handleDeleteAudio,
    exportingMp3,
  };
}
