import type { RefObject } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { useBridge } from "../../lib/BridgeContext";
import type { RequestState, SessionProject, TTSCapability, TTSProviderConfig } from "../../types";
import type { EditorTransform } from "./workbenchUtils";
import { useScriptWorkbenchAudio } from "./useScriptWorkbenchAudio";
import { useScriptWorkbenchData } from "./useScriptWorkbenchData";
import { useScriptWorkbenchEditor } from "./useScriptWorkbenchEditor";
import type { PendingDialogState } from "./workbenchTypes";

export type { PendingDialogState } from "./workbenchTypes";

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

  const data = useScriptWorkbenchData({ bridge, sessionId, scriptId, onRefresh });
  const editor = useScriptWorkbenchEditor({
    bridge,
    sessionId,
    scriptId,
    project: data.project,
    script: data.script,
    setScript: data.setScript,
    refreshWorkspace: data.refreshWorkspace,
    isScriptDeleted: data.isScriptDeleted,
    isSessionDeleted: data.isSessionDeleted,
    isDirty: data.isDirty,
  });
  const audio = useScriptWorkbenchAudio({
    bridge,
    sessionId,
    scriptId,
    onRefresh,
    reload: data.reload,
    project: data.project,
    setProject: data.setProject,
    selectedEngine: data.selectedEngine,
    cloudProvider: data.cloudProvider,
  });

  const localEngineDisabled = audio.generating || !data.capability?.available || data.isScriptDeleted || data.isSessionDeleted;
  const cloudEngineDisabled = audio.generating || data.isScriptDeleted || data.isSessionDeleted;

  const handleGenerateAudio = () => {
    if (data.isScriptDeleted || data.isSessionDeleted || data.script.trim().length === 0) return;
    editor.runWithUnsavedCheck(async () => {
      await audio.triggerRenderAudio();
    });
  };

  const handleShareAudio = async () => {
    await audio.handleShareAudio(data.scriptName);
  };

  return {
    navigate,
    loading: data.loading,
    project: data.project,
    script: data.script,
    setScript: data.setScript,
    capability: data.capability,
    ttsConfig: data.ttsConfig,
    selectedEngine: data.selectedEngine,
    setSelectedEngine: data.setSelectedEngine,
    loadingError: data.loadingError,
    saving: editor.saving,
    generating: audio.generating,
    busyAction: editor.busyAction,
    editorError: editor.editorError,
    audioError: audio.audioError,
    editorRequestState: editor.editorRequestState,
    audioRequestState: audio.audioRequestState,
    pollWarning: audio.pollWarning,
    audioMessage: audio.audioMessage,
    dialogState: editor.dialogState,
    setDialogState: editor.setDialogState,
    isAudioPlaying: audio.isAudioPlaying,
    textareaRef: editor.textareaRef,
    audioRef: audio.audioRef,
    toolbarButtonClass: editor.toolbarButtonClass,
    isScriptDeleted: data.isScriptDeleted,
    isSessionDeleted: data.isSessionDeleted,
    isDirty: data.isDirty,
    topic: data.topic,
    scriptName: data.scriptName,
    updatedAt: data.updatedAt,
    wordCount: data.wordCount,
    estMinutes: data.estMinutes,
    cloudProvider: data.cloudProvider,
    audioSrc: audio.audioSrc,
    outputFilename: data.outputFilename,
    localEngineDisabled,
    cloudEngineDisabled,
    sessionStateLabel: data.sessionStateLabel,
    runWithUnsavedCheck: editor.runWithUnsavedCheck,
    applyToolbarAction: editor.applyToolbarAction,
    handleSave: editor.handleSave,
    handleDeleteScript: editor.handleDeleteScript,
    handleRestoreScript: editor.handleRestoreScript,
    handleRestoreSession: editor.handleRestoreSession,
    handleRollbackRevision: editor.handleRollbackRevision,
    handleGenerateAudio,
    handleCancelAudio: audio.handleCancelAudio,
    handlePreviewAudio: audio.handlePreviewAudio,
    handleRevealInFinder: audio.handleRevealInFinder,
    handleDownloadAudio: audio.handleDownloadAudio,
    handleShareAudio,
    reload: data.reload,
    refreshWorkspace: data.refreshWorkspace,
    closeDialog: editor.closeDialog,
    runPendingAction: editor.runPendingAction,
  };
}
