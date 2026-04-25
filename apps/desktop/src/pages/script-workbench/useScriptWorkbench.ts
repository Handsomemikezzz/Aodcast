import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { convertFileSrc } from "@tauri-apps/api/core";
import { useBridge } from "../../lib/BridgeContext";
import { revealInFinder } from "../../lib/shellOps";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  isActiveRequestState,
  isTerminalRequestState,
  withRequestStateFallback,
} from "../../lib/requestState";
import type {
  RequestState,
  SessionProject,
  TTSCapability,
  TTSProviderConfig,
} from "../../types";
import {
  estimateWordCount,
  formatEstimateMinutes,
  formatSessionState,
  type EditorTransform,
} from "./workbenchUtils";

const POLL_INTERVAL_MS = 1000;
const POLL_FAILURE_THRESHOLD = 3;

export type PendingDialogState =
  | { kind: "delete-script" }
  | { kind: "rollback"; revisionId: string }
  | { kind: "unsaved" }
  | null;

export type UseScriptWorkbenchResult = {
  navigate: NavigateFunction;
  loading: boolean;
  project: SessionProject | null;
  script: string;
  setScript: (value: string) => void;
  capability: TTSCapability | null;
  ttsConfig: TTSProviderConfig | null;
  selectedEngine: "local_mlx" | "cloud";
  setSelectedEngine: (value: "local_mlx" | "cloud") => void;
  loadingError: string | null;
  saving: boolean;
  generating: boolean;
  busyAction: string | null;
  editorError: string | null;
  audioError: string | null;
  editorRequestState: RequestState | null;
  audioRequestState: RequestState | null;
  pollWarning: string | null;
  audioMessage: string | null;
  dialogState: PendingDialogState;
  setDialogState: (state: PendingDialogState) => void;
  isAudioPlaying: boolean;
  textareaRef: RefObject<HTMLTextAreaElement>;
  audioRef: RefObject<HTMLAudioElement>;
  toolbarButtonClass: string;
  isScriptDeleted: boolean;
  isSessionDeleted: boolean;
  isDirty: boolean;
  topic: string;
  scriptName: string;
  updatedAt: string;
  wordCount: number;
  estMinutes: string;
  cloudProvider: string;
  audioSrc: string;
  outputFilename: string;
  localEngineDisabled: boolean;
  cloudEngineDisabled: boolean;
  sessionStateLabel: string;
  runWithUnsavedCheck: (action: () => Promise<void>) => void;
  applyToolbarAction: (
    formatter: (value: string, selectionStart: number, selectionEnd: number) => EditorTransform,
  ) => void;
  handleSave: () => Promise<boolean>;
  handleDeleteScript: () => Promise<void>;
  handleRestoreScript: () => Promise<void>;
  handleRestoreSession: () => Promise<void>;
  handleRollbackRevision: (revisionId: string) => Promise<void>;
  handleGenerateAudio: () => void;
  handleCancelAudio: () => Promise<void>;
  handlePreviewAudio: () => Promise<void>;
  handleRevealInFinder: () => Promise<void>;
  handleDownloadAudio: () => void;
  handleShareAudio: () => Promise<void>;
  reload: () => Promise<void>;
  refreshWorkspace: () => Promise<void>;
  closeDialog: () => void;
  runPendingAction: () => Promise<void>;
};

export function useScriptWorkbench(sessionId: string, scriptId: string, onRefresh: () => Promise<void>): UseScriptWorkbenchResult {
  const bridge = useBridge();
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const pendingActionRef = useRef<(() => Promise<void>) | null>(null);
  const pollHandleRef = useRef<number | null>(null);
  const pollingInFlightRef = useRef(false);
  const pollFailureCountRef = useRef(0);
  const expectedRunTokenRef = useRef<string | null>(null);
  const taskId = `render_audio:${sessionId}`;

  const [project, setProject] = useState<SessionProject | null>(null);
  const [script, setScript] = useState("");
  const [capability, setCapability] = useState<TTSCapability | null>(null);
  const [ttsConfig, setTtsConfig] = useState<TTSProviderConfig | null>(null);
  const [selectedEngine, setSelectedEngine] = useState<"local_mlx" | "cloud">("cloud");
  const [loading, setLoading] = useState(true);
  const [loadingError, setLoadingError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [editorRequestState, setEditorRequestState] = useState<RequestState | null>(null);
  const [audioRequestState, setAudioRequestState] = useState<RequestState | null>(null);
  const [pollWarning, setPollWarning] = useState<string | null>(null);
  const [audioMessage, setAudioMessage] = useState<string | null>(null);
  const [dialogState, setDialogState] = useState<PendingDialogState>(null);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);

  const stopTaskPolling = () => {
    if (pollHandleRef.current !== null) {
      window.clearInterval(pollHandleRef.current);
      pollHandleRef.current = null;
    }
    pollingInFlightRef.current = false;
    pollFailureCountRef.current = 0;
  };

  const acceptPolledState = (state: RequestState | null): boolean => {
    if (!state) return false;
    const expectedToken = expectedRunTokenRef.current;
    if (expectedToken && state.run_token !== expectedToken) {
      return false;
    }
    setAudioRequestState((previous) => {
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
          setPollWarning((previous) => (previous ? null : previous));
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
    setAudioRequestState((previous) => {
      if ((previous?.phase === "cancelling" || previous?.phase === "cancelled") && state.phase === "running") {
        return previous;
      }
      return state;
    });
    return state;
  };

  const reload = async () => {
    const [loadedProject, loadedCapability, loadedConfig] = await Promise.all([
      bridge.showScript(sessionId, scriptId),
      bridge.getLocalTTSCapability(),
      bridge.showTTSConfig(),
    ]);
    setProject(loadedProject);
    setScript(loadedProject.script?.final || loadedProject.script?.draft || "");
    setCapability(loadedCapability);
    setTtsConfig(loadedConfig);
  };

  const refreshWorkspace = async () => {
    await Promise.allSettled([reload(), onRefresh()]);
  };

  useEffect(() => {
    const loadWorkspace = async () => {
      try {
        setLoading(true);
        setLoadingError(null);
        setEditorError(null);
        setAudioError(null);
        await reload();
      } catch (err: unknown) {
        setLoadingError(getErrorMessage(err, "Failed to load the script workspace."));
        setEditorError(getErrorMessage(err, "Failed to load the script workspace."));
        setEditorRequestState(getErrorRequestState(err));
      } finally {
        setLoading(false);
      }
    };

    void loadWorkspace();
  }, [bridge, sessionId, scriptId]);

  useEffect(() => {
    const defaultEngine = ttsConfig?.provider === "local_mlx" ? "local_mlx" : capability?.available ? "local_mlx" : "cloud";
    setSelectedEngine(defaultEngine);
  }, [capability?.available, ttsConfig?.provider]);

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

  const cloudProvider = useMemo(() => {
    const configuredProvider = ttsConfig?.provider?.trim();
    if (configuredProvider && configuredProvider !== "local_mlx") {
      return configuredProvider;
    }
    return capability?.fallback_provider || "mock_remote";
  }, [capability?.fallback_provider, ttsConfig?.provider]);

  const serverScript = project?.script?.final || project?.script?.draft || "";
  const isScriptDeleted = Boolean(project?.script?.deleted_at);
  const isSessionDeleted = Boolean(project?.session.deleted_at);
  const isDirty = !isScriptDeleted && !isSessionDeleted && script !== serverScript;
  const wordCount = useMemo(() => estimateWordCount(script), [script]);
  const estMinutes = useMemo(() => formatEstimateMinutes(wordCount), [wordCount]);
  const topic = project?.session.topic || "Untitled Project";
  const scriptName = project?.script?.name || topic;
  const updatedAt = project?.script?.updated_at || project?.session.updated_at || "";
  const outputFilename = project?.artifact?.audio_path?.split("/").pop() || "";

  const audioSrc = useMemo(() => {
    const audioPath = project?.artifact?.audio_path;
    if (!audioPath) return "";
    try {
      return convertFileSrc(audioPath);
    } catch {
      return `file://${audioPath}`;
    }
  }, [project?.artifact?.audio_path]);

  const localEngineDisabled = generating || !capability?.available || isScriptDeleted || isSessionDeleted;
  const cloudEngineDisabled = generating || isScriptDeleted || isSessionDeleted;
  const sessionStateLabel = formatSessionState(project?.session.state);

  const toolbarButtonClass =
    "inline-flex h-10 min-w-10 items-center justify-center rounded-xl border border-outline bg-surface-container-low px-3 text-[12px] font-medium text-secondary transition-colors hover:border-accent-amber/30 hover:text-primary disabled:opacity-50";

  const applyTransform = (transform: EditorTransform) => {
    setScript(transform.nextValue);
    window.requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.setSelectionRange(transform.selectionStart, transform.selectionEnd);
    });
  };

  const applyToolbarAction = (
    formatter: (value: string, selectionStart: number, selectionEnd: number) => EditorTransform,
  ) => {
    const textarea = textareaRef.current;
    if (!textarea || isScriptDeleted || isSessionDeleted) return;
    applyTransform(formatter(script, textarea.selectionStart, textarea.selectionEnd));
  };

  const handleSave = async (): Promise<boolean> => {
    if (!project?.script || isScriptDeleted || isSessionDeleted || !isDirty) return true;
    try {
      setSaving(true);
      setEditorError(null);
      setEditorRequestState({
        operation: "save_script",
        phase: "running",
        progress_percent: 0,
        message: "Saving script...",
      });
      await bridge.saveEditedScript(sessionId, scriptId, script);
      await refreshWorkspace();
      setEditorRequestState(buildRequestState("save_script", "succeeded", "Script saved."));
      return true;
    } catch (err: unknown) {
      setEditorError(getErrorMessage(err, "Failed to save script."));
      setEditorRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("save_script", "failed", "Failed to save script."),
        ),
      );
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteScript = async () => {
    if (!project?.script || isScriptDeleted || isSessionDeleted) return;
    setBusyAction("delete-script");
    setEditorError(null);
    setEditorRequestState({
      operation: "delete_script",
      phase: "running",
      progress_percent: 0,
      message: "Moving script to trash...",
    });
    try {
      await bridge.deleteScript(sessionId, scriptId);
      await refreshWorkspace();
      setEditorRequestState(buildRequestState("delete_script", "succeeded", "Script moved to trash."));
    } catch (err: unknown) {
      setEditorError(getErrorMessage(err, "Failed to delete script."));
      setEditorRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("delete_script", "failed", "Failed to delete script."),
        ),
      );
    } finally {
      setBusyAction(null);
    }
  };

  const handleRestoreScript = async () => {
    if (!isScriptDeleted) return;
    setBusyAction("restore-script");
    setEditorError(null);
    setEditorRequestState({
      operation: "restore_script",
      phase: "running",
      progress_percent: 0,
      message: "Restoring script...",
    });
    try {
      await bridge.restoreScript(sessionId, scriptId);
      await refreshWorkspace();
      setEditorRequestState(buildRequestState("restore_script", "succeeded", "Script restored."));
    } catch (err: unknown) {
      setEditorError(getErrorMessage(err, "Failed to restore script."));
      setEditorRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("restore_script", "failed", "Failed to restore script."),
        ),
      );
    } finally {
      setBusyAction(null);
    }
  };

  const handleRestoreSession = async () => {
    if (!isSessionDeleted) return;
    setBusyAction("restore-session");
    setEditorError(null);
    setEditorRequestState({
      operation: "restore_session",
      phase: "running",
      progress_percent: 0,
      message: "Restoring session...",
    });
    try {
      await bridge.restoreSession(sessionId);
      await refreshWorkspace();
      setEditorRequestState(buildRequestState("restore_session", "succeeded", "Session restored."));
    } catch (err: unknown) {
      setEditorError(getErrorMessage(err, "Failed to restore session."));
      setEditorRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("restore_session", "failed", "Failed to restore session."),
        ),
      );
    } finally {
      setBusyAction(null);
    }
  };

  const handleRollbackRevision = async (revisionId: string) => {
    if (isScriptDeleted || isSessionDeleted) return;
    setBusyAction(revisionId);
    setEditorError(null);
    setEditorRequestState({
      operation: "rollback_script_revision",
      phase: "running",
      progress_percent: 0,
      message: "Rolling back revision...",
    });
    try {
      await bridge.rollbackScriptRevision(sessionId, scriptId, revisionId);
      await refreshWorkspace();
      setEditorRequestState(buildRequestState("rollback_script_revision", "succeeded", "Revision restored."));
    } catch (err: unknown) {
      setEditorError(getErrorMessage(err, "Failed to roll back revision."));
      setEditorRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("rollback_script_revision", "failed", "Failed to roll back revision."),
        ),
      );
    } finally {
      setBusyAction(null);
    }
  };

  const runPendingAction = async () => {
    const pendingAction = pendingActionRef.current;
    pendingActionRef.current = null;
    if (!pendingAction) return;
    await pendingAction();
  };

  const closeDialog = () => {
    pendingActionRef.current = null;
    setDialogState(null);
  };

  const runWithUnsavedCheck = (action: () => Promise<void>) => {
    if (!isDirty) {
      void action();
      return;
    }
    pendingActionRef.current = action;
    setDialogState({ kind: "unsaved" });
  };

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
      const result = await bridge.renderAudio(sessionId, { providerOverride, scriptId });
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
      if (errorState?.phase === "cancelled") {
        setAudioError(null);
      } else {
        setAudioError(getErrorMessage(err, "Failed to render audio."));
      }
      setAudioRequestState(
        withRequestStateFallback(errorState, buildRequestState("render_audio", "failed", "Failed to render audio.")),
      );
      setGenerating(false);
      stopTaskPolling();
    }
  };

  const handleGenerateAudio = () => {
    if (isScriptDeleted || isSessionDeleted || script.trim().length === 0) return;
    runWithUnsavedCheck(async () => {
      await triggerRenderAudio();
    });
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

  const handleRevealInFinder = async () => {
    if (!project?.artifact?.audio_path) return;
    try {
      await revealInFinder(project.artifact.audio_path);
    } catch (err: unknown) {
      setAudioError(getErrorMessage(err, "Failed to reveal audio in Finder."));
    }
  };

  const handleDownloadAudio = () => {
    if (!audioSrc || !outputFilename) return;
    const link = document.createElement("a");
    link.href = audioSrc;
    link.download = outputFilename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const handleShareAudio = async () => {
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
    navigate,
    loading,
    project,
    script,
    setScript,
    capability,
    ttsConfig,
    selectedEngine,
    setSelectedEngine,
    loadingError,
    saving,
    generating,
    busyAction,
    editorError,
    audioError,
    editorRequestState,
    audioRequestState,
    pollWarning,
    audioMessage,
    dialogState,
    setDialogState,
    isAudioPlaying,
    textareaRef,
    audioRef,
    toolbarButtonClass,
    isScriptDeleted,
    isSessionDeleted,
    isDirty,
    topic,
    scriptName,
    updatedAt,
    wordCount,
    estMinutes,
    cloudProvider,
    audioSrc,
    outputFilename,
    localEngineDisabled,
    cloudEngineDisabled,
    sessionStateLabel,
    runWithUnsavedCheck,
    applyToolbarAction,
    handleSave,
    handleDeleteScript,
    handleRestoreScript,
    handleRestoreSession,
    handleRollbackRevision,
    handleGenerateAudio,
    handleCancelAudio,
    handlePreviewAudio,
    handleRevealInFinder,
    handleDownloadAudio,
    handleShareAudio,
    reload,
    refreshWorkspace,
    closeDialog,
    runPendingAction,
  };
}
