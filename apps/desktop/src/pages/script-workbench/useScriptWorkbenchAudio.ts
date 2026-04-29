import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { resolveAudioFileUrl } from "../../lib/audioFile";
import type { DesktopBridge } from "../../lib/desktopBridge";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  isActiveRequestState,
  isTerminalRequestState,
  withRequestStateFallback,
} from "../../lib/requestState";
import { revealInFinder } from "../../lib/shellOps";
import { resolveProjectVoiceSettings } from "../../lib/voiceSettings";
import type { RequestState, RuntimeInfo, SessionProject } from "../../types";

const POLL_INTERVAL_MS = 1000;
const POLL_FAILURE_THRESHOLD = 3;

type UseScriptWorkbenchAudioArgs = {
  bridge: DesktopBridge;
  sessionId: string;
  scriptId: string;
  onRefresh: () => Promise<void>;
  reload: () => Promise<void>;
  project: SessionProject | null;
  setProject: (project: SessionProject) => void;
  selectedEngine: "local_mlx" | "cloud";
  cloudProvider: string;
};

type UseScriptWorkbenchAudioResult = {
  generating: boolean;
  audioError: string | null;
  audioRequestState: RequestState | null;
  pollWarning: string | null;
  audioMessage: string | null;
  isAudioPlaying: boolean;
  audioRef: RefObject<HTMLAudioElement>;
  audioSrc: string;
  triggerRenderAudio: () => Promise<void>;
  handleCancelAudio: () => Promise<void>;
  handlePreviewAudio: () => Promise<void>;
  handleAudioLoadError: () => void;
  handleRevealInFinder: () => Promise<void>;
  handleDownloadAudio: () => void;
  handleShareAudio: (scriptName: string) => Promise<void>;
  handleDeleteAudio: () => Promise<void>;
};

export function useScriptWorkbenchAudio({
  bridge,
  sessionId,
  scriptId,
  onRefresh,
  reload,
  project,
  setProject,
  selectedEngine,
  cloudProvider,
}: UseScriptWorkbenchAudioArgs): UseScriptWorkbenchAudioResult {
  const audioRef = useRef<HTMLAudioElement>(null);
  const pollHandleRef = useRef<number | null>(null);
  const pollingInFlightRef = useRef(false);
  const pollFailureCountRef = useRef(0);
  const expectedRunTokenRef = useRef<string | null>(null);

  const taskId = `render_audio:${sessionId}`;

  const [generating, setGenerating] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [audioRequestState, setAudioRequestState] = useState<RequestState | null>(null);
  const [pollWarning, setPollWarning] = useState<string | null>(null);
  const [audioMessage, setAudioMessage] = useState<string | null>(null);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);

  const audioSrc = useMemo(() => {
    const audioPath = project?.artifact?.audio_path;
    return audioPath ? resolveAudioFileUrl(audioPath) : "";
  }, [project?.artifact?.audio_path]);

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
    const shortToken = runtime.build_token.slice(0, 8);
    return `runtime pid=${runtime.pid}, started=${startedAt}, build=${shortToken}`;
  };

  const runtimeLabelFromError = (error: unknown): string | null => {
    if (typeof error !== "object" || error === null) return null;
    const candidate = error as {
      runtime?: RuntimeInfo;
      details?: { runtime?: RuntimeInfo };
    };
    if (
      candidate.runtime
      && typeof candidate.runtime.pid === "number"
      && typeof candidate.runtime.started_at_unix === "number"
      && typeof candidate.runtime.build_token === "string"
    ) {
      return runtimeLabel(candidate.runtime);
    }
    const nestedRuntime = candidate.details?.runtime;
    if (
      nestedRuntime
      && typeof nestedRuntime.pid === "number"
      && typeof nestedRuntime.started_at_unix === "number"
      && typeof nestedRuntime.build_token === "string"
    ) {
      return runtimeLabel(nestedRuntime);
    }
    return null;
  };

  const acceptPolledState = (state: RequestState | null): boolean => {
    if (!state) return false;
    const expectedToken = expectedRunTokenRef.current;
    if (expectedToken && state.run_token !== expectedToken) {
      return false;
    }
    setAudioRequestState((previous: RequestState | null) => {
      if ((previous?.phase === "cancelling" || previous?.phase === "cancelled") && state.phase === "running") {
        return previous;
      }
      return state;
    });
    if (isTerminalRequestState(state)) {
      stopTaskPolling();
      setGenerating(false);
    } else {
      setGenerating(true);
    }
    return true;
  };

  const startTaskPolling = () => {
    if (pollHandleRef.current !== null) return;
    pollFailureCountRef.current = 0;
    setPollWarning(null);
    pollHandleRef.current = window.setInterval(() => {
      if (pollingInFlightRef.current) return;
      pollingInFlightRef.current = true;
      void bridge
        .showTaskState(taskId)
        .then((state) => {
          pollFailureCountRef.current = 0;
          setPollWarning((previous: string | null) => (previous ? null : previous));
          acceptPolledState(state);
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
    }, POLL_INTERVAL_MS);
  };

  const syncTaskState = async (): Promise<RequestState | null> => {
    const state = await bridge.showTaskState(taskId);
    if (!state) return null;
    const expectedToken = expectedRunTokenRef.current;
    if (expectedToken && state.run_token !== expectedToken) {
      return null;
    }
    setAudioRequestState((previous: RequestState | null) => {
      if ((previous?.phase === "cancelling" || previous?.phase === "cancelled") && state.phase === "running") {
        return previous;
      }
      return state;
    });
    return state;
  };

  useEffect(() => {
    expectedRunTokenRef.current = null;
    void syncTaskState()
      .then((state) => {
        if (state && isActiveRequestState(state)) {
          expectedRunTokenRef.current = state.run_token ?? null;
          setGenerating(true);
          startTaskPolling();
        } else {
          setGenerating(false);
        }
      })
      .catch(() => undefined);

    return () => {
      stopTaskPolling();
      expectedRunTokenRef.current = null;
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
  }, [project?.artifact?.audio_path]);

  const triggerRenderAudio = async () => {
    try {
      expectedRunTokenRef.current = null;
      stopTaskPolling();
      const existingState = await syncTaskState();
      if (existingState && isActiveRequestState(existingState)) {
        expectedRunTokenRef.current = existingState.run_token ?? null;
        setGenerating(true);
        startTaskPolling();
        return;
      }

      setGenerating(true);
      setAudioError(null);
      setAudioMessage(null);
      setAudioRequestState({
        operation: "render_audio",
        phase: "running",
        progress_percent: 0,
        message: "Rendering audio...",
      });

      const providerOverride = selectedEngine === "local_mlx" ? "local_mlx" : cloudProvider;
      const result = await bridge.renderAudio(sessionId, {
        providerOverride,
        scriptId,
        voiceSettings: resolveProjectVoiceSettings(project),
      });
      const runToken = typeof result.run_token === "string" && result.run_token.length > 0 ? result.run_token : result.request_state?.run_token ?? null;
      expectedRunTokenRef.current = runToken;
      setProject(result.project);
      const finalTaskId = result.task_id ?? taskId;
      const finalState = await bridge.showTaskState(finalTaskId).catch(() => null);
      const chosenState = finalState ?? result.request_state ?? buildRequestState("render_audio", "running", "Rendering audio...");
      if (runToken && !chosenState.run_token) {
        chosenState.run_token = runToken;
      }
      setAudioRequestState(chosenState);
      if (isTerminalRequestState(chosenState)) {
        setGenerating(false);
      } else {
        setGenerating(true);
        startTaskPolling();
      }
      await onRefresh();
      await reload();
    } catch (err: unknown) {
      const errorState = getErrorRequestState(err);
      const runtimeHint = runtimeLabelFromError(err);
      if (errorState?.phase === "cancelled") {
        setAudioError(null);
      } else {
        const baseMessage = getErrorMessage(err, "Failed to render audio.");
        setAudioError(runtimeHint ? `${baseMessage} (${runtimeHint})` : baseMessage);
      }
      setAudioRequestState(
        withRequestStateFallback(errorState, buildRequestState("render_audio", "failed", "Failed to render audio.")),
      );
      setGenerating(false);
      stopTaskPolling();
    }
  };

  const handleCancelAudio = async () => {
    try {
      const state = await bridge.cancelTask(taskId);
      if (state) {
        setAudioRequestState(state);
      } else {
        setAudioRequestState(buildRequestState("render_audio", "cancelling", "Cancellation requested."));
      }
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to request cancellation."));
    }
  };

  const handlePreviewAudio = async () => {
    const audioElement = audioRef.current;
    if (!audioElement || !audioSrc) return;
    try {
      if (audioElement.paused) {
        await audioElement.play();
      } else {
        audioElement.pause();
      }
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to preview audio."));
    }
  };

  const handleAudioLoadError = () => {
    setAudioError("无法加载音频文件。文件可能已移动或删除，请重新生成音频。");
  };

  const handleRevealInFinder = async () => {
    if (!project?.artifact?.audio_path) return;
    try {
      await revealInFinder(project.artifact.audio_path);
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to reveal audio in Finder."));
    }
  };

  const handleDeleteAudio = async () => {
    if (!project?.artifact?.audio_path) return;
    try {
      setAudioError(null);
      const updated = await bridge.deleteGeneratedAudio(sessionId, { scriptId: project.script?.script_id });
      setProject(updated);
      setAudioRequestState(null);
      setAudioMessage("Audio artifact deleted.");
      await onRefresh();
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to delete audio."));
    }
  };

  const handleDownloadAudio = () => {
    const outputFilename = project?.artifact?.audio_path?.split("/").pop() || "";
    if (!audioSrc || !outputFilename) return;
    const link = document.createElement("a");
    link.href = audioSrc;
    link.download = outputFilename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const handleShareAudio = async (scriptName: string) => {
    if (!project?.artifact?.audio_path) return;
    const payload = {
      title: `${scriptName} audio`,
      text: project.artifact.audio_path,
    };
    try {
      if (typeof navigator.share === "function") {
        await navigator.share(payload);
        setAudioMessage("Audio path shared.");
        return;
      }
      await navigator.clipboard.writeText(project.artifact.audio_path);
      setAudioMessage("Audio path copied to clipboard.");
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to share audio path."));
    }
  };

  return {
    generating,
    audioError,
    audioRequestState,
    pollWarning,
    audioMessage,
    isAudioPlaying,
    audioRef,
    audioSrc,
    triggerRenderAudio,
    handleCancelAudio,
    handlePreviewAudio,
    handleAudioLoadError,
    handleRevealInFinder,
    handleDownloadAudio,
    handleShareAudio,
    handleDeleteAudio,
  };
}
