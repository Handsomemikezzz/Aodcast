import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Clock3, Edit3, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useBridge } from "../lib/BridgeContext";
import type { RequestState, ScriptRecord, ScriptRevisionRecord, SessionProject } from "../types";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  withRequestStateFallback,
} from "../lib/requestState";
import { cn } from "../lib/utils";

export function EditPage({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const { sessionId, scriptId } = useParams<{ sessionId: string; scriptId: string }>();
  const navigate = useNavigate();
  const bridge = useBridge();

  const [project, setProject] = useState<SessionProject | null>(null);
  const [topic, setTopic] = useState("Untitled Project");
  const [script, setScript] = useState("");
  const [revisions, setRevisions] = useState<ScriptRevisionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requestState, setRequestState] = useState<RequestState | null>(null);
  const [scriptSnapshots, setScriptSnapshots] = useState<ScriptRecord[]>([]);
  const [dialogState, setDialogState] = useState<
    | { kind: "delete-script" }
    | { kind: "rollback"; revisionId: string }
    | { kind: "unsaved" }
    | null
  >(null);
  const pendingActionRef = useRef<(() => Promise<void>) | null>(null);
  const sortedRevisions = useMemo(
    () => revisions.slice().sort((left, right) => right.created_at.localeCompare(left.created_at)),
    [revisions],
  );

  const reload = async () => {
    if (!sessionId || !scriptId) return;
    const [loadedProject, loadedRevisions, listed] = await Promise.all([
      bridge.showScript(sessionId, scriptId),
      bridge.listScriptRevisions(sessionId, scriptId),
      bridge.listScripts(sessionId),
    ]);
    setProject(loadedProject);
    setTopic(loadedProject.session.topic || "Untitled Project");
    setScript(loadedProject.script?.final || loadedProject.script?.draft || "");
    setRevisions(loadedRevisions);
    setScriptSnapshots(listed);
  };

  const refreshWorkspace = async () => {
    await Promise.allSettled([reload(), onRefresh()]);
  };

  useEffect(() => {
    const loadProject = async () => {
      if (!sessionId || !scriptId) return;
      try {
        setLoading(true);
        setError(null);
        await reload();
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load the script project."));
        setRequestState(getErrorRequestState(err));
      } finally {
        setLoading(false);
      }
    };

    void loadProject();
  }, [sessionId, scriptId, bridge]);

  const handleSave = async (): Promise<boolean> => {
    if (!sessionId || !scriptId || project?.script?.deleted_at || project?.session.deleted_at) return false;
    if (!isDirty) return true;
    try {
      setSaving(true);
      setError(null);
      setRequestState({
        operation: "save_script",
        phase: "running",
        progress_percent: 0,
        message: "Saving script...",
      });
      await bridge.saveEditedScript(sessionId, scriptId, script);
      await refreshWorkspace();
      setRequestState(buildRequestState("save_script", "succeeded", "Script saved."));
      return true;
    } catch (err) {
      setError(getErrorMessage(err, "Failed to save script."));
      setRequestState(
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
    if (!sessionId || !scriptId || !project || project.script?.deleted_at || project.session.deleted_at) return;
    setBusyAction("delete-script");
    setError(null);
    setRequestState({
      operation: "delete_script",
      phase: "running",
      progress_percent: 0,
      message: "Moving script to trash...",
    });
    try {
      await bridge.deleteScript(sessionId, scriptId);
      await refreshWorkspace();
      setRequestState(buildRequestState("delete_script", "succeeded", "Script moved to trash."));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete script."));
      setRequestState(
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
    if (!sessionId || !scriptId || !project?.script?.deleted_at) return;
    setBusyAction("restore-script");
    setError(null);
    setRequestState({
      operation: "restore_script",
      phase: "running",
      progress_percent: 0,
      message: "Restoring script...",
    });
    try {
      await bridge.restoreScript(sessionId, scriptId);
      await refreshWorkspace();
      setRequestState(buildRequestState("restore_script", "succeeded", "Script restored."));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to restore script."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("restore_script", "failed", "Failed to restore script."),
        ),
      );
    } finally {
      setBusyAction(null);
    }
  };

  const handleRollbackRevision = async (revisionId: string) => {
    if (!sessionId || !scriptId || project?.script?.deleted_at || project?.session.deleted_at) return;
    setBusyAction(revisionId);
    setError(null);
    setRequestState({
      operation: "rollback_script_revision",
      phase: "running",
      progress_percent: 0,
      message: "Rolling back revision...",
    });
    try {
      await bridge.rollbackScriptRevision(sessionId, scriptId, revisionId);
      await refreshWorkspace();
      setRequestState(buildRequestState("rollback_script_revision", "succeeded", "Revision restored."));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to roll back revision."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("rollback_script_revision", "failed", "Failed to roll back revision."),
        ),
      );
    } finally {
      setBusyAction(null);
    }
  };

  const handleRestoreSession = async () => {
    if (!sessionId || !project?.session.deleted_at) return;
    setBusyAction("restore-session");
    setError(null);
    setRequestState({
      operation: "restore_session",
      phase: "running",
      progress_percent: 0,
      message: "Restoring session...",
    });
    try {
      await bridge.restoreSession(sessionId);
      await refreshWorkspace();
      setRequestState(buildRequestState("restore_session", "succeeded", "Session restored."));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to restore session."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("restore_session", "failed", "Failed to restore session."),
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

  if (loading) {
    return <div className="flex h-full items-center justify-center text-secondary text-sm">Loading editor...</div>;
  }

  const isScriptDeleted = Boolean(project?.script?.deleted_at);
  const isSessionDeleted = Boolean(project?.session.deleted_at);
  const serverScript = project?.script?.final || project?.script?.draft || "";
  const isDirty = !isScriptDeleted && !isSessionDeleted && script !== serverScript;

  const renderWithDialogs = (content: JSX.Element) => (
    <>
      {content}
      <ConfirmDialog
        open={dialogState?.kind === "delete-script"}
        title="Move script to trash?"
        message="The current script snapshot will be moved to trash, but its revision history remains available."
        onClose={closeDialog}
        actions={[
          {
            label: "Cancel",
            onClick: closeDialog,
          },
          {
            label: "Move to trash",
            onClick: () => {
              setDialogState(null);
              void handleDeleteScript();
            },
            variant: "danger",
            disabled: busyAction === "delete-script",
          },
        ]}
      />
      <ConfirmDialog
        open={dialogState?.kind === "rollback"}
        title="Roll back revision?"
        message="The selected revision will replace the current script content and create a new revision entry."
        onClose={closeDialog}
        actions={[
          {
            label: "Cancel",
            onClick: closeDialog,
          },
          {
            label: "Roll back",
            onClick: () => {
              const revisionId = dialogState?.kind === "rollback" ? dialogState.revisionId : "";
              setDialogState(null);
              if (!revisionId) return;
              void handleRollbackRevision(revisionId);
            },
            variant: "primary",
            disabled: dialogState?.kind === "rollback" && busyAction === dialogState.revisionId,
          },
        ]}
      />
      <ConfirmDialog
        open={dialogState?.kind === "unsaved"}
        title="Unsaved changes"
        message="Save the current script before continuing, or discard these edits for this action."
        onClose={closeDialog}
        actions={[
          {
            label: "Cancel",
            onClick: closeDialog,
          },
          {
            label: "Discard changes",
            onClick: () => {
              setScript(serverScript);
              setDialogState(null);
              void runPendingAction();
            },
            variant: "danger",
            disabled: saving,
          },
          {
            label: saving ? "Saving..." : "Save and continue",
            onClick: () => {
              void (async () => {
                const saved = await handleSave();
                if (!saved) return;
                setDialogState(null);
                await runPendingAction();
              })();
            },
            variant: "primary",
            disabled: saving,
          },
        ]}
      />
    </>
  );

  return renderWithDialogs(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col h-full w-full relative"
    >
      <div className="flex-1 overflow-y-auto px-6 lg:px-12 py-8">
        <div className="max-w-6xl mx-auto w-full flex flex-col lg:flex-row gap-6">
          <div className="flex-1 min-w-0 flex flex-col">
            <div className="mb-6 flex justify-between items-end border-b border-outline pb-4">
              <div>
                <h1 className="text-2xl font-headline font-bold text-primary mb-1">{topic}</h1>
                {project?.script?.name ? (
                  <p className="text-[13px] text-secondary font-medium mb-1">{project.script.name}</p>
                ) : null}
                <p className="text-secondary text-sm">
                  Review and refine this script snapshot. Each chat generation adds another snapshot; switch below if this
                  session has more than one.
                </p>
                {scriptSnapshots.length > 0 && (
                  <div className="mt-3">
                    <p className="text-[11px] uppercase tracking-wider text-secondary mb-2">
                      Script snapshots ({scriptSnapshots.length})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {scriptSnapshots.map((snap) => {
                        const active = snap.script_id === scriptId;
                        const deleted = Boolean(snap.deleted_at);
                        return (
                          <button
                            key={snap.script_id}
                            type="button"
                            onClick={() => {
                              if (active) return;
                              runWithUnsavedCheck(async () => {
                                navigate(`/script/${sessionId}/${snap.script_id}`);
                              });
                            }}
                            disabled={active}
                            title={snap.name}
                            className={cn(
                              "max-w-full truncate rounded-md border px-2.5 py-1 text-left text-[12px] font-medium transition-colors",
                              active
                                ? "border-accent-amber/50 bg-accent-amber/10 text-primary cursor-default"
                                : "border-outline bg-surface-container-low text-secondary hover:border-accent-amber/30 hover:text-primary",
                              deleted && "opacity-60",
                            )}
                          >
                            {snap.name || snap.script_id.slice(0, 8)}
                            {deleted ? " · trash" : ""}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
                {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
                {!error && requestState?.phase === "running" && (
                  <p className="mt-2 text-xs text-secondary">{requestState.message}</p>
                )}
                {isDirty && !saving && (
                  <p className="mt-2 text-xs font-medium text-accent-amber">Unsaved changes</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {saving && <span className="text-xs text-secondary font-medium animate-pulse">Saving...</span>}
                {project?.script?.updated_at && (
                  <span className="text-[10px] uppercase tracking-wider text-secondary">
                    Updated {new Date(project.script.updated_at).toLocaleDateString()}
                  </span>
                )}
              </div>
            </div>

            {isSessionDeleted && (
              <div className="mb-6 rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100 flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-primary">This session is in trash.</p>
                  <p className="text-[12px] text-secondary">Restore it to keep working on the script.</p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleRestoreSession()}
                  disabled={busyAction === "restore-session"}
                  className="px-3 py-1.5 rounded-md bg-surface-container text-primary text-[12px] font-medium hover:bg-surface-container-high transition-colors disabled:opacity-50"
                >
                  Restore session
                </button>
              </div>
            )}

            {isScriptDeleted && (
              <div className="mb-6 rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100 flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-primary">This script is in trash.</p>
                  <p className="text-[12px] text-secondary">
                    {isSessionDeleted
                      ? "Restore the session first, then restore the script."
                      : "Restore it before editing or rolling back revisions."}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleRestoreScript()}
                  disabled={busyAction === "restore-script" || isSessionDeleted}
                  className="px-3 py-1.5 rounded-md bg-surface-container text-primary text-[12px] font-medium hover:bg-surface-container-high transition-colors disabled:opacity-50"
                >
                  Restore script
                </button>
              </div>
            )}

            <textarea
              value={script}
              onChange={(event) => setScript(event.target.value)}
              disabled={isScriptDeleted || isSessionDeleted}
              className="w-full min-h-[480px] flex-1 bg-transparent resize-none outline-none text-[15px] leading-relaxed text-on-surface placeholder:text-outline/40 pb-20 focus:ring-0 border-none disabled:opacity-60"
              placeholder={script ? "" : "No script generated yet. Write yours here or go back to chat to generate one."}
              spellCheck="false"
            />
          </div>

          <aside className="w-full lg:w-[340px] shrink-0 flex flex-col gap-4">
            <div className="rounded-xl border border-outline bg-surface-container-low p-4">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="w-4 h-4 text-accent-amber" />
                <span className="text-xs font-semibold text-secondary uppercase tracking-wider">Script State</span>
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-primary font-medium">Current status</span>
                  <span className="text-[11px] uppercase tracking-wider text-secondary">
                    {isScriptDeleted ? "In trash" : project?.session.state?.replace(/_/g, " ") || "Draft"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {isScriptDeleted ? (
                    <button
                      type="button"
                      onClick={() => void handleRestoreScript()}
                      disabled={busyAction === "restore-script" || isSessionDeleted}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-[12px] font-medium bg-primary/10 text-primary hover:bg-primary/15 transition-colors disabled:opacity-50"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      Restore script
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => runWithUnsavedCheck(async () => {
                        setDialogState({ kind: "delete-script" });
                      })}
                      disabled={busyAction === "delete-script"}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-[12px] font-medium bg-surface-container-high text-primary hover:bg-surface-container-highest transition-colors disabled:opacity-50"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Move to trash
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => runWithUnsavedCheck(async () => {
                      await reload();
                    })}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-[12px] font-medium text-secondary hover:bg-surface-container-high hover:text-primary transition-colors"
                  >
                    <Clock3 className="w-3.5 h-3.5" />
                    Refresh
                  </button>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-outline bg-surface-container-low p-4 flex-1 min-h-0">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-2">
                  <Edit3 className="w-4 h-4 text-accent-amber" />
                  <span className="text-xs font-semibold text-secondary uppercase tracking-wider">Revision History</span>
                </div>
                <span className="text-[11px] text-secondary">{revisions.length} revisions</span>
              </div>
              <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1 mac-scrollbar">
                {revisions.length === 0 ? (
                  <div className="rounded-lg border border-outline bg-background px-3 py-4 text-xs text-secondary">
                    No revisions yet.
                  </div>
                ) : (
                  sortedRevisions.map((revision) => {
                      const isBusy = busyAction === revision.revision_id;
                      return (
                        <div
                          key={revision.revision_id}
                          className="rounded-lg border border-outline bg-background px-3 py-3"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-[13px] font-medium text-primary">
                                {revision.label || revision.kind || "Revision"}
                              </p>
                              <p className="text-[11px] text-secondary mt-0.5">
                                {new Date(revision.created_at).toLocaleString()}
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() => runWithUnsavedCheck(async () => {
                                setDialogState({
                                  kind: "rollback",
                                  revisionId: revision.revision_id,
                                });
                              })}
                              disabled={isBusy || isScriptDeleted || isSessionDeleted}
                              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium text-secondary hover:bg-surface-container-high hover:text-primary transition-colors disabled:opacity-50"
                            >
                              <RotateCcw className="w-3.5 h-3.5" />
                              Roll back
                            </button>
                          </div>
                          <p className="mt-2 text-[12px] text-secondary whitespace-pre-wrap break-words max-h-20 overflow-hidden">
                            {revision.content || " "}
                          </p>
                        </div>
                      );
                    })
                )}
              </div>
            </div>
          </aside>
        </div>
      </div>

      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-surface-container/60 backdrop-blur-2xl border border-outline rounded-full px-4 py-2 flex items-center gap-4 shadow-lg shadow-black/20">
        <div className="flex items-center gap-2 border-r border-outline pr-4">
          <Sparkles className="w-4 h-4 text-accent-amber" />
          <span className="text-xs font-semibold text-primary">Script Editor</span>
        </div>

        <button
          onClick={() => void handleSave()}
          disabled={saving || isScriptDeleted || isSessionDeleted || !isDirty}
          className="text-xs font-medium text-secondary hover:text-primary transition-colors flex items-center gap-1 disabled:opacity-50"
        >
          <Edit3 className="w-3.5 h-3.5" />
          {saving ? "Saving..." : isDirty ? "Save script" : "Saved"}
        </button>
      </div>
    </motion.div>,
  );
}
