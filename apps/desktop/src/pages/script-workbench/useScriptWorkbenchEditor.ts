import { useRef, useState, type RefObject } from "react";
import type { DesktopBridge } from "../../lib/desktopBridge";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  withRequestStateFallback,
} from "../../lib/requestState";
import type { RequestState, SessionProject } from "../../types";
import type { EditorTransform } from "./workbenchUtils";
import type { PendingDialogState } from "./workbenchTypes";

type AsyncAction = () => Promise<void>;

type UseScriptWorkbenchEditorArgs = {
  bridge: DesktopBridge;
  sessionId: string;
  scriptId: string;
  project: SessionProject | null;
  script: string;
  setScript: (value: string) => void;
  refreshWorkspace: () => Promise<void>;
  isScriptDeleted: boolean;
  isSessionDeleted: boolean;
  isDirty: boolean;
};

type UseScriptWorkbenchEditorResult = {
  saving: boolean;
  busyAction: string | null;
  editorError: string | null;
  editorRequestState: RequestState | null;
  dialogState: PendingDialogState;
  setDialogState: (state: PendingDialogState) => void;
  textareaRef: RefObject<HTMLTextAreaElement>;
  toolbarButtonClass: string;
  runWithUnsavedCheck: (action: AsyncAction) => void;
  applyToolbarAction: (
    formatter: (value: string, selectionStart: number, selectionEnd: number) => EditorTransform,
  ) => void;
  handleSave: () => Promise<boolean>;
  handleDeleteScript: () => Promise<void>;
  handleRestoreScript: () => Promise<void>;
  handleRestoreSession: () => Promise<void>;
  handleRollbackRevision: (revisionId: string) => Promise<void>;
  closeDialog: () => void;
  runPendingAction: () => Promise<void>;
};

export function useScriptWorkbenchEditor({
  bridge,
  sessionId,
  scriptId,
  project,
  script,
  setScript,
  refreshWorkspace,
  isScriptDeleted,
  isSessionDeleted,
  isDirty,
}: UseScriptWorkbenchEditorArgs): UseScriptWorkbenchEditorResult {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingActionRef = useRef<AsyncAction | null>(null);

  const [saving, setSaving] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [editorRequestState, setEditorRequestState] = useState<RequestState | null>(null);
  const [dialogState, setDialogState] = useState<PendingDialogState>(null);

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

  const runWithUnsavedCheck = (action: AsyncAction) => {
    if (!isDirty) {
      void action();
      return;
    }
    pendingActionRef.current = action;
    setDialogState({ kind: "unsaved" });
  };

  return {
    saving,
    busyAction,
    editorError,
    editorRequestState,
    dialogState,
    setDialogState,
    textareaRef,
    toolbarButtonClass,
    runWithUnsavedCheck,
    applyToolbarAction,
    handleSave,
    handleDeleteScript,
    handleRestoreScript,
    handleRestoreSession,
    handleRollbackRevision,
    closeDialog,
    runPendingAction,
  };
}
