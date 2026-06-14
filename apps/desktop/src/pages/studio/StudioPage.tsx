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
  const [focusedCard, setFocusedCard] = useState<"chat" | "edit" | "generate">(
    initialLeftOpen ? "chat" : initialRightOpen ? "generate" : "edit"
  );
  const [chatState, setChatState] = useState<"open" | "collapsed">(
    initialLeftOpen ? "open" : "collapsed"
  );
  const [generateState, setGenerateState] = useState<"open" | "collapsed">(
    initialRightOpen ? "open" : "collapsed"
  );

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
      <div className="flex h-full w-full overflow-hidden p-4 gap-4 bg-gradient-to-b from-[#121214] to-[#0a0a0c] relative items-stretch">
        
        {/* Left collapsed strip */}
        {chatState === "collapsed" && (
          <div
            onClick={() => {
              setChatState("open");
              setFocusedCard("chat");
            }}
            className="w-11 shrink-0 glass-edge-strip rounded-2xl flex flex-col items-center justify-between py-4 cursor-pointer"
            title="Expand Conversation"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-xl bg-accent-amber/10 border border-accent-amber/25 text-accent-amber shrink-0">
              <MessageSquare className="w-3.5 h-3.5" />
            </div>
            <span className="writing-mode-vertical text-[10px] font-bold uppercase tracking-wider text-secondary/70 my-4 select-none">
              Conversation
            </span>
            <div className="h-7 w-7 flex items-center justify-center text-secondary/40 shrink-0">
              <ChevronRight className="w-3.5 h-3.5" />
            </div>
          </div>
        )}

        {/* Chat Card (if open) */}
        {chatState === "open" && (
          <div
            className={cn(
              "glass-deck-card rounded-3xl overflow-hidden flex flex-col relative",
              focusedCard === "chat"
                ? "flex-[3.5] glass-deck-card-focused opacity-100"
                : "flex-[0.8] glass-deck-card-inactive opacity-60 hover:opacity-85 hover:scale-[1.005]"
            )}
          >
            <ConversationDrawer
              project={workbench.project}
              onRefresh={onRefresh}
              onNewScript={(sid, scriptId) =>
                navigate(`/studio/${sid}/${scriptId}`)
              }
              isFocused={focusedCard === "chat"}
              onFocus={() => setFocusedCard("chat")}
              onClose={() => {
                setChatState("collapsed");
                if (focusedCard === "chat") {
                  setFocusedCard("edit");
                }
              }}
            />
          </div>
        )}

        {/* Center: Script Editor Card (always open in deck) */}
        <div
          className={cn(
            "glass-deck-card rounded-3xl overflow-hidden flex flex-col relative",
            focusedCard === "edit"
              ? "flex-[3.5] glass-deck-card-focused opacity-100"
              : "flex-[0.8] glass-deck-card-inactive opacity-60 hover:opacity-85 hover:scale-[1.005]"
          )}
        >
          {focusedCard === "edit" ? (
            <div className="flex-1 flex flex-col min-w-0 overflow-y-auto px-5 py-5 lg:px-6 mac-scrollbar">
              <div className="mx-auto flex w-full max-w-[840px] flex-col gap-4">
                <ScriptWorkbenchHeader workbench={workbench} />
                {workbench.isSessionDeleted && (
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
                )}
                {workbench.isScriptDeleted && (
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
                )}
                <ScriptEditorPane
                  workbench={workbench}
                  isFocused={true}
                />
              </div>
            </div>
          ) : (
            <ScriptEditorPane
              workbench={workbench}
              isFocused={false}
              onFocus={() => setFocusedCard("edit")}
            />
          )}
        </div>

        {/* Voice & Audio Card (if open) */}
        {generateState === "open" && (
          <div
            className={cn(
              "glass-deck-card rounded-3xl overflow-hidden flex flex-col relative",
              focusedCard === "generate"
                ? "flex-[3.5] glass-deck-card-focused opacity-100"
                : "flex-[0.8] glass-deck-card-inactive opacity-60 hover:opacity-85 hover:scale-[1.005]"
            )}
          >
            <VoiceAudioDrawer
              workbench={workbench}
              isFocused={focusedCard === "generate"}
              onFocus={() => setFocusedCard("generate")}
              onClose={() => {
                setGenerateState("collapsed");
                if (focusedCard === "generate") {
                  setFocusedCard("edit");
                }
              }}
            />
          </div>
        )}

        {/* Right collapsed strip */}
        {generateState === "collapsed" && (
          <div
            onClick={() => {
              setGenerateState("open");
              setFocusedCard("generate");
            }}
            className="w-11 shrink-0 glass-edge-strip rounded-2xl flex flex-col items-center justify-between py-4 cursor-pointer"
            title="Expand Voice & Audio"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-xl bg-accent-amber/10 border border-accent-amber/25 text-accent-amber shrink-0">
              <Mic className="w-3.5 h-3.5" />
            </div>
            <span className="writing-mode-vertical text-[10px] font-bold uppercase tracking-wider text-secondary/70 my-4 select-none">
              Voice &amp; Audio
            </span>
            <div className="h-7 w-7 flex items-center justify-center text-secondary/40 shrink-0">
              <ChevronLeft className="w-3.5 h-3.5" />
            </div>
          </div>
        )}

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
