import type { RefObject } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { useBridge } from "../../lib/BridgeContext";
import type { ModelStatus, RequestState, SessionProject, SpeakerReference, TTSCapability, TTSProviderConfig } from "../../types";
import { contextWindowSegmentIds, type EditorTransform } from "./workbenchUtils";
import { useScriptWorkbenchAudio } from "./useScriptWorkbenchAudio";
import { useScriptWorkbenchData } from "./useScriptWorkbenchData";
import { useScriptWorkbenchEditor } from "./useScriptWorkbenchEditor";
import { useSpokenScriptChecks } from "./useSpokenScriptChecks";
import { getPersistedScriptText } from "./spokenScriptChecks";
import { buildScriptCleanupPreview } from "./spokenScriptCleanup";
import type { ScriptCheckResult } from "./spokenScriptTypes";
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
  speakerReferences: SpeakerReference[];
  models: ModelStatus[];
  selectedModelId: string;
  setSelectedModelId: (value: string) => void;
  voiceSelectionError: string | null;
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
  affectedSegmentIds: string[];
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
  handleAudioLoadError: () => void;
  handleRevealInFinder: () => Promise<void>;
  handleExportMp3: () => Promise<void>;
  handleDeleteAudio: () => Promise<void>;
  handleSelectSpeakerReference: (referenceId: string) => Promise<void>;
  requestSegmentRegeneration: (segmentId: string) => void;
  handleRegenerateAudioWindow: (segmentId: string) => Promise<void>;
  reload: () => Promise<void>;
  refreshWorkspace: () => Promise<void>;
  closeDialog: () => void;
  runPendingAction: () => Promise<void>;
  exportingMp3: boolean;
  scriptCheck: ScriptCheckResult;
  handleOpenCleanupPreview: () => void;
  handleApplyCleanup: () => void;
  speechPlanStale: boolean;
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
    setProject: data.setProject,
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
    refreshProject: data.refreshProject,
    project: data.project,
    setProject: data.setProject,
    selectedEngine: data.selectedEngine,
    cloudProvider: data.cloudProvider,
    selectedModelId: data.selectedModelId,
  });

  const scriptCheck = useSpokenScriptChecks(data.script);

  const localEngineDisabled = audio.generating || !data.capability?.available || data.isScriptDeleted || data.isSessionDeleted;
  const cloudEngineDisabled = audio.generating || data.isScriptDeleted || data.isSessionDeleted;

  const runRenderAudioGuarded = async () => {
    const latestProject = await bridge.showScript(sessionId, scriptId);
    const scriptToRender = getPersistedScriptText(latestProject.script?.final, latestProject.script?.draft);
    await audio.triggerRenderAudio({ scriptToRender });
  };

  const handleGenerateAudio = () => {
    if (data.isScriptDeleted || data.isSessionDeleted || !scriptCheck.canRender) return;
    editor.runWithUnsavedCheck(runRenderAudioGuarded);
  };

  const handleOpenCleanupPreview = () => {
    const preview = buildScriptCleanupPreview(data.script);
    editor.setDialogState({ kind: "cleanup-preview", preview });
  };

  const handleApplyCleanup = () => {
    if (editor.dialogState?.kind !== "cleanup-preview") return;
    data.setScript(editor.dialogState.preview.cleaned);
    editor.setDialogState(null);
  };

  const speechPlanStale = (() => {
    const plan = data.project?.speech_plan;
    const manifest = data.project?.render_manifest;
    if (!plan) return false;
    if (data.isDirty) return true;
    if (manifest && (manifest.speech_plan.plan_id !== plan.plan_id || manifest.speech_plan.plan_hash !== plan.plan_hash)) return true;
    const scriptUpdatedAt = Date.parse(data.project?.script?.updated_at || "");
    const planCreatedAt = Date.parse(plan.created_at);
    return Number.isFinite(scriptUpdatedAt) && Number.isFinite(planCreatedAt) && scriptUpdatedAt > planCreatedAt;
  })();

  const requestSegmentRegeneration = (segmentId: string) => {
    const segments = data.project?.speech_plan?.segments ?? [];
    const windowSegmentIds = contextWindowSegmentIds(segments, segmentId);
    if (!windowSegmentIds.length) return;
    editor.setDialogState({ kind: "regenerate-window", targetSegmentId: segmentId, windowSegmentIds });
  };

  const handleRegenerateAudioWindow = async (segmentId: string) => {
    if (data.isDirty || speechPlanStale || audio.generating) return;
    await audio.triggerRegenerateAudioWindow(segmentId);
  };

  return {
    navigate,
    loading: data.loading,
    project: data.project,
    script: data.script,
    setScript: data.setScript,
    capability: data.capability,
    ttsConfig: data.ttsConfig,
    speakerReferences: data.speakerReferences,
    models: data.models,
    selectedModelId: data.selectedModelId,
    setSelectedModelId: data.setSelectedModelId,
    voiceSelectionError: data.voiceSelectionError,
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
    affectedSegmentIds: audio.affectedSegmentIds,
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
    handleAudioLoadError: audio.handleAudioLoadError,
    handleRevealInFinder: audio.handleRevealInFinder,
    handleExportMp3: audio.handleExportMp3,
    handleDeleteAudio: audio.handleDeleteAudio,
    handleSelectSpeakerReference: data.handleSelectSpeakerReference,
    requestSegmentRegeneration,
    handleRegenerateAudioWindow,
    reload: data.reload,
    refreshWorkspace: data.refreshWorkspace,
    closeDialog: editor.closeDialog,
    runPendingAction: editor.runPendingAction,
    exportingMp3: audio.exportingMp3,
    scriptCheck,
    handleOpenCleanupPreview,
    handleApplyCleanup,
    speechPlanStale,
  };
}
