import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Loader2, MessageSquare, Mic } from "lucide-react";
import { motion } from "framer-motion";
import { useBridge } from "../../lib/BridgeContext";
import { StudioProvider } from "../../lib/StudioContext";
import { cn } from "../../lib/utils";
import { useScriptWorkbench } from "../script-workbench/useScriptWorkbench";
import { ScriptEditorPane } from "../script-workbench/ScriptEditorPane";
import { ScriptWorkbenchHeader } from "../script-workbench/ScriptWorkbenchHeader";
import { ScriptCleanupPreviewDialog } from "../script-workbench/ScriptCleanupPreviewDialog";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ExportPodcastDialog } from "../../components/ExportPodcastDialog";
import { ChatPage } from "../ChatPage";
import { ConversationDrawer } from "./ConversationDrawer";
import { VoiceAudioDrawer } from "./VoiceAudioDrawer";

// Resolves /studio/:sessionId (no scriptId) to the latest script, then redirects
function StudioSessionResolve({
  sessionId,
  onRefresh,
}: {
  sessionId: string;
  onRefresh: () => Promise<void>;
}) {
  const bridge = useBridge();
  const navigate = useNavigate();
  const [noScript, setNoScript] = useState(false);
  const resolvedRef = useRef(false);

  useEffect(() => {
    if (resolvedRef.current) return;
    resolvedRef.current = true;
    void bridge
      .showLatestScript(sessionId)
      .then((project) => {
        if (project.script?.script_id) {
          navigate(`/studio/${sessionId}/${project.script.script_id}`, { replace: true });
        } else {
          setNoScript(true);
        }
      })
      .catch(() => {
        setNoScript(true);
      });
  }, [sessionId, bridge, navigate]);

  if (noScript) {
    return <ChatPage onRefresh={onRefresh} />;
  }

  return (
    <div className="flex h-full items-center justify-center text-secondary text-sm">
      <Loader2 className="w-4 h-4 animate-spin mr-2" />
      Opening studio…
    </div>
  );
}

// Inner studio with workbench hoisted so both editor and voice drawer share state
function StudioWorkspace({
  sessionId,
  scriptId,
  onRefresh,
  initialLeftOpen,
  initialRightOpen,
}: {
  sessionId: string;
  scriptId: string;
  onRefresh: () => Promise<void>;
  initialLeftOpen: boolean;
  initialRightOpen: boolean;
}) {
  const bridge = useBridge();
  const navigate = useNavigate();
  const workbench = useScriptWorkbench(sessionId, scriptId, onRefresh);
  const [leftOpen, setLeftOpen] = useState(initialLeftOpen);
  const [rightOpen, setRightOpen] = useState(initialRightOpen);

  if (workbench.loading) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        <Loader2 className="w-4 h-4 animate-spin mr-2" />
        Loading studio…
      </div>
    );
  }

  if (!workbench.project) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        {workbench.loadingError || "Studio unavailable for this episode."}
      </div>
    );
  }

  return (
    <>
      <div className="flex h-full w-full overflow-hidden">
        {/* Left drawer: Conversation */}
        <div
          className={cn(
            "flex-shrink-0 flex flex-col border-r border-white/5 bg-[rgba(14,14,16,0.85)] transition-all duration-300 overflow-hidden",
            leftOpen ? "w-[340px] xl:w-[380px]" : "w-0",
          )}
        >
          {leftOpen && (
            <div className="flex flex-col h-full w-full">
              <div className="h-9 shrink-0 flex items-center justify-between px-3 border-b border-white/5">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-secondary/70">
                  <MessageSquare className="w-3.5 h-3.5" />
                  Conversation
                </div>
                <button
                  type="button"
                  onClick={() => setLeftOpen(false)}
                  className="p-1 rounded-md text-secondary hover:text-white hover:bg-white/5 transition-colors"
                  aria-label="Close conversation panel"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 min-h-0 overflow-hidden">
                <ConversationDrawer
                  project={workbench.project}
                  onRefresh={onRefresh}
                  onNewScript={(sid, scriptId) =>
                    navigate(`/studio/${sid}/${scriptId}`)
                  }
                />
              </div>
            </div>
          )}
        </div>

        {/* Left drawer toggle (when closed) */}
        {!leftOpen && (
          <button
            type="button"
            onClick={() => setLeftOpen(true)}
            className="flex-shrink-0 w-8 flex items-center justify-center border-r border-white/5 text-secondary hover:text-white hover:bg-white/3 transition-colors group"
            aria-label="Open conversation panel"
            title="Conversation"
          >
            <div className="flex flex-col items-center gap-1">
              <MessageSquare className="w-3.5 h-3.5 group-hover:text-accent-amber transition-colors" />
              <ChevronRight className="w-3 h-3" />
            </div>
          </button>
        )}

        {/* Center: Script editor */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex h-full min-h-0 w-full overflow-y-auto px-4 py-5 lg:px-6"
          >
            <div className="mx-auto flex w-full max-w-[920px] flex-col gap-5">
              <ScriptWorkbenchHeader workbench={workbench} />
              {workbench.isSessionDeleted ? (
                <div className="rounded-2xl border border-accent-amber/25 bg-accent-amber/10 px-4 py-3 text-sm text-primary">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <p className="font-medium">This session is in trash.</p>
                      <p className="mt-1 text-xs text-secondary">Restore it before editing the script or rendering audio.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void workbench.handleRestoreSession()}
                      disabled={workbench.busyAction === "restore-session"}
                      className="inline-flex h-10 items-center justify-center rounded-xl border border-outline bg-surface-container px-4 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high disabled:opacity-50"
                    >
                      Restore Session
                    </button>
                  </div>
                </div>
              ) : null}
              {workbench.isScriptDeleted ? (
                <div className="rounded-2xl border border-accent-amber/25 bg-accent-amber/10 px-4 py-3 text-sm text-primary">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <p className="font-medium">This script snapshot is in trash.</p>
                      <p className="mt-1 text-xs text-secondary">Restore it to resume editing or render audio.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void workbench.handleRestoreScript()}
                      disabled={workbench.busyAction === "restore-script" || workbench.isSessionDeleted}
                      className="inline-flex h-10 items-center justify-center rounded-xl border border-outline bg-surface-container px-4 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high disabled:opacity-50"
                    >
                      Restore Script
                    </button>
                  </div>
                </div>
              ) : null}
              <ScriptEditorPane workbench={workbench} />
            </div>
          </motion.div>
        </div>

        {/* Right drawer toggle (when closed) */}
        {!rightOpen && (
          <button
            type="button"
            onClick={() => setRightOpen(true)}
            className="flex-shrink-0 w-8 flex items-center justify-center border-l border-white/5 text-secondary hover:text-white hover:bg-white/3 transition-colors group"
            aria-label="Open voice & audio panel"
            title="Voice & Audio"
          >
            <div className="flex flex-col items-center gap-1">
              <ChevronLeft className="w-3 h-3" />
              <Mic className="w-3.5 h-3.5 group-hover:text-accent-amber transition-colors" />
            </div>
          </button>
        )}

        {/* Right drawer: Voice & Audio */}
        <div
          className={cn(
            "flex-shrink-0 flex flex-col border-l border-white/5 bg-[rgba(14,14,16,0.85)] transition-all duration-300 overflow-hidden",
            rightOpen ? "w-[360px] xl:w-[400px]" : "w-0",
          )}
        >
          {rightOpen && (
            <VoiceAudioDrawer
              workbench={workbench}
              onClose={() => setRightOpen(false)}
            />
          )}
        </div>
      </div>

      {/* Dialogs (mounted at workspace level, not inside drawers) */}
      <ConfirmDialog
        open={workbench.dialogState?.kind === "delete-script"}
        title="Move script to trash?"
        message="The current script snapshot will be moved to trash, but its revision history stays available."
        onClose={workbench.closeDialog}
        actions={[
          { label: "Cancel", onClick: workbench.closeDialog },
          {
            label: "Move to trash",
            onClick: () => {
              workbench.setDialogState(null);
              void workbench.handleDeleteScript();
            },
            variant: "danger",
            disabled: workbench.busyAction === "delete-script",
          },
        ]}
      />
      <ConfirmDialog
        open={workbench.dialogState?.kind === "rollback"}
        title="Roll back revision?"
        message="The selected script snapshot will replace the current script content."
        onClose={workbench.closeDialog}
        actions={[
          { label: "Cancel", onClick: workbench.closeDialog },
          {
            label: "Roll back",
            onClick: () => {
              const revisionId = workbench.dialogState?.kind === "rollback" ? workbench.dialogState.revisionId : "";
              workbench.setDialogState(null);
              if (!revisionId) return;
              void workbench.handleRollbackRevision(revisionId);
            },
            variant: "primary",
            disabled: workbench.dialogState?.kind === "rollback" && workbench.busyAction === workbench.dialogState.revisionId,
          },
        ]}
      />
      <ConfirmDialog
        open={workbench.dialogState?.kind === "unsaved"}
        title="Unsaved changes"
        message="Save the current script before continuing, or discard these edits for this action."
        onClose={workbench.closeDialog}
        actions={[
          { label: "Cancel", onClick: workbench.closeDialog },
          {
            label: "Discard changes",
            onClick: () => {
              workbench.setScript(workbench.project?.script?.final || workbench.project?.script?.draft || "");
              workbench.setDialogState(null);
              void workbench.runPendingAction();
            },
            variant: "danger",
            disabled: workbench.saving,
          },
          {
            label: workbench.saving ? "Saving..." : "Save and continue",
            onClick: () => {
              void (async () => {
                const saved = await workbench.handleSave();
                if (!saved) return;
                workbench.setDialogState(null);
                await workbench.runPendingAction();
              })();
            },
            variant: "primary",
            disabled: workbench.saving,
          },
        ]}
      />
      <ScriptCleanupPreviewDialog
        open={workbench.dialogState?.kind === "cleanup-preview"}
        preview={workbench.dialogState?.kind === "cleanup-preview" ? workbench.dialogState.preview : null}
        onClose={workbench.closeDialog}
        onApply={workbench.handleApplyCleanup}
      />
      <ExportPodcastDialog
        open={workbench.isExportDialogOpen}
        audioPath={workbench.project?.artifact?.audio_path || ""}
        sessionTopic={workbench.project?.session?.topic || ""}
        bridge={bridge}
        onClose={workbench.closeExportDialog}
      />
    </>
  );
}

export function StudioPage({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const { sessionId, scriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const [searchParams] = useSearchParams();

  // Determine initial drawer states from URL params
  const panelParam = searchParams.get("panel");
  const initialLeftOpen = panelParam === "conversation";
  // Right drawer open by default on wide screens (handled via CSS), closed by default when entering from non-voice routes
  const initialRightOpen = panelParam === "voice";

  if (!sessionId) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        No episode selected. Open an episode from the Episodes list.
      </div>
    );
  }

  if (!scriptId) {
    return (
      <StudioProvider>
        <StudioSessionResolve sessionId={sessionId} onRefresh={onRefresh} />
      </StudioProvider>
    );
  }

  return (
    <StudioProvider>
      <StudioWorkspace
        key={`${sessionId}-${scriptId}`}
        sessionId={sessionId}
        scriptId={scriptId}
        onRefresh={onRefresh}
        initialLeftOpen={initialLeftOpen}
        initialRightOpen={initialRightOpen}
      />
    </StudioProvider>
  );
}
