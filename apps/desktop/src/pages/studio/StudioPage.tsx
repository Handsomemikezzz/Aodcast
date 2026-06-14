import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useBridge } from "../../lib/BridgeContext";
import { useScriptWorkbench } from "../script-workbench/useScriptWorkbench";
import { ScriptEditorPane } from "../script-workbench/ScriptEditorPane";
import { ScriptCleanupPreviewDialog } from "../script-workbench/ScriptCleanupPreviewDialog";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ExportPodcastDialog } from "../../components/ExportPodcastDialog";
import { ChatPage } from "../ChatPage";
import { ConversationDrawer } from "./ConversationDrawer";
import { VoiceAudioPanel } from "./VoiceAudioDrawer";
import { StudioHeader } from "./StudioHeader";
import { TranscriptBar } from "./TranscriptBar";
import { buildVoiceFreshnessKey, deriveAudioFreshness } from "./studioWorkflow";

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

// ── Main Studio Workspace ────────────────────────────────────────────────────
function StudioWorkspace({
  sessionId,
  scriptId,
  onRefresh,
  initialTranscriptOpen,
}: {
  sessionId: string;
  scriptId: string;
  onRefresh: () => Promise<void>;
  initialTranscriptOpen: boolean;
}) {
  const bridge = useBridge();
  const navigate = useNavigate();
  const workbench = useScriptWorkbench(sessionId, scriptId, onRefresh);

  // Transcript overlay state
  const [transcriptOpen, setTranscriptOpen] = useState(initialTranscriptOpen);

  // Ref to scroll the audio section into view when the Audio stepper step is clicked
  const audioSectionRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Audio out-of-date: set when script or voice inputs change after audio exists.
  const [audioOutOfDate, setAudioOutOfDate] = useState(false);
  const [audioOutOfDateReason, setAudioOutOfDateReason] = useState<string | undefined>(undefined);
  const prevAudioSrcRef = useRef(workbench.audioSrc);
  const prevScriptRef = useRef<string | null>(null);
  const prevVoiceKeyRef = useRef<string | null>(null);

  const serverScript = workbench.project?.script?.final ?? workbench.project?.script?.draft ?? "";
  const voiceFreshnessKey = buildVoiceFreshnessKey(workbench.project, scriptId);

  useEffect(() => {
    const hasAudio = Boolean(workbench.audioSrc);
    if (!hasAudio) {
      setAudioOutOfDate(false);
      setAudioOutOfDateReason(undefined);
      prevScriptRef.current = serverScript;
      prevVoiceKeyRef.current = voiceFreshnessKey;
      return;
    }

    const previousServerScript = prevScriptRef.current ?? serverScript;
    const previousVoiceKey = prevVoiceKeyRef.current ?? voiceFreshnessKey;
    const freshness = deriveAudioFreshness({
      hasAudio,
      generating: workbench.generating,
      isDirty: workbench.isDirty,
      serverScript,
      currentScript: workbench.script,
      previousServerScript,
      voiceKey: voiceFreshnessKey,
      previousVoiceKey,
    });

    if (freshness.outOfDate) {
      setAudioOutOfDate(true);
      setAudioOutOfDateReason(freshness.reason);
    }

    prevScriptRef.current = serverScript;
    prevVoiceKeyRef.current = voiceFreshnessKey;
  }, [
    serverScript,
    scriptId,
    voiceFreshnessKey,
    workbench.audioSrc,
    workbench.generating,
    workbench.isDirty,
    workbench.script,
  ]);

  // Clear out-of-date state when a new audio render completes
  useEffect(() => {
    if (workbench.audioSrc && workbench.audioSrc !== prevAudioSrcRef.current) {
      setAudioOutOfDate(false);
      setAudioOutOfDateReason(undefined);
      prevScriptRef.current = serverScript;
      prevVoiceKeyRef.current = voiceFreshnessKey;
    }
    prevAudioSrcRef.current = workbench.audioSrc;
  }, [serverScript, voiceFreshnessKey, workbench.audioSrc]);

  // Navigate to Voice Studio with return context
  const handleVoiceNavigate = () => {
    const path = workbench.project?.script
      ? `/voice-studio/${workbench.project.session.session_id}/${workbench.project.script.script_id}?returnTo=${encodeURIComponent(`/studio/${sessionId}/${scriptId}`)}`
      : "/voice-studio";
    navigate(path);
  };

  const handleScriptFocus = () => {
    textareaRef.current?.focus();
    textareaRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const handleAudioFocus = () => {
    audioSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

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

  const turns = workbench.project.transcript?.turns ?? [];

  return (
    <>
      {/* ── Full-height studio layout ──────────────────────── */}
      <div className="flex flex-col h-full w-full overflow-hidden bg-background">

        {/* Header: title + stepper + global CTA */}
        <StudioHeader
          workbench={workbench}
          audioOutOfDate={audioOutOfDate}
          onTranscriptOpen={() => setTranscriptOpen(true)}
          onScriptFocus={handleScriptFocus}
          onVoiceNavigate={handleVoiceNavigate}
          onAudioFocus={handleAudioFocus}
          onExport={workbench.handleDownloadAudio}
        />

        {/* Main two-column body — relative container for transcript overlay */}
        <div className="flex-1 flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden relative mac-scrollbar">

          {/* Transcript overlay drawer */}
          <ConversationDrawer
            project={workbench.project}
            isOpen={transcriptOpen}
            onClose={() => setTranscriptOpen(false)}
            onRefresh={onRefresh}
            onNewScript={(sid, newScriptId) =>
              navigate(`/studio/${sid}/${newScriptId}`)
            }
          />

          {/* ── Left column: transcript bar + script editor ── */}
          <div className="flex flex-col w-full lg:flex-1 min-w-0 min-h-[560px] lg:min-h-0 overflow-hidden">

            {/* Transcript collapsed bar */}
            <TranscriptBar
              turnCount={turns.length}
              onOpen={() => setTranscriptOpen(true)}
            />

            {/* Deleted session / script warnings */}
            {(workbench.isSessionDeleted || workbench.isScriptDeleted) && (
              <div className="mx-4 mt-3 rounded-2xl border border-accent-amber/25 bg-accent-amber/10 px-4 py-3 text-sm text-primary shrink-0">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    {workbench.isSessionDeleted ? (
                      <>
                        <p className="font-medium">This session is in trash.</p>
                        <p className="mt-1 text-xs text-secondary">Restore it before editing the script or rendering audio.</p>
                      </>
                    ) : (
                      <>
                        <p className="font-medium">This script snapshot is in trash.</p>
                        <p className="mt-1 text-xs text-secondary">Restore it to resume editing or render audio.</p>
                      </>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      workbench.isSessionDeleted
                        ? void workbench.handleRestoreSession()
                        : void workbench.handleRestoreScript()
                    }
                    disabled={
                      workbench.busyAction === "restore-session" ||
                      workbench.busyAction === "restore-script"
                    }
                    className="inline-flex h-10 items-center justify-center rounded-xl border border-outline bg-surface-container px-4 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high disabled:opacity-50 shrink-0"
                  >
                    {workbench.isSessionDeleted ? "Restore Session" : "Restore Script"}
                  </button>
                </div>
              </div>
            )}

            {/* Script editor — takes remaining height */}
            <div className="flex-1 overflow-hidden p-4">
              <ScriptEditorPane
                workbench={workbench}
                textareaRef={textareaRef}
              />
            </div>
          </div>

          {/* ── Right column: Voice & Audio panel ────────────── */}
          <div className="w-full lg:w-[280px] xl:w-[300px] shrink-0 border-t lg:border-t-0 lg:border-l border-outline overflow-visible lg:overflow-hidden flex flex-col bg-surface-container-low/30">
            <div className="px-4 py-2.5 border-b border-outline shrink-0">
              <p className="text-[10px] font-bold uppercase tracking-wider text-secondary/60">Voice & Audio</p>
            </div>
            <VoiceAudioPanel
              workbench={workbench}
              audioOutOfDate={audioOutOfDate}
              audioOutOfDateReason={audioOutOfDateReason}
              audioSectionRef={audioSectionRef}
            />
          </div>
        </div>
      </div>

      {/* ── Dialogs ─────────────────────────────────────────── */}
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
              const revisionId =
                workbench.dialogState?.kind === "rollback"
                  ? workbench.dialogState.revisionId
                  : "";
              workbench.setDialogState(null);
              if (!revisionId) return;
              void workbench.handleRollbackRevision(revisionId);
            },
            variant: "primary",
            disabled:
              workbench.dialogState?.kind === "rollback" &&
              workbench.busyAction === workbench.dialogState.revisionId,
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
              workbench.setScript(
                workbench.project?.script?.final || workbench.project?.script?.draft || "",
              );
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
        preview={
          workbench.dialogState?.kind === "cleanup-preview" ? workbench.dialogState.preview : null
        }
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

// ── Entry Point ──────────────────────────────────────────────────────────────
export function StudioPage({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const { sessionId, scriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const [searchParams] = useSearchParams();

  const panelParam = searchParams.get("panel");
  const initialTranscriptOpen = panelParam === "conversation";

  if (!sessionId) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        No episode selected. Open an episode from the Episodes list.
      </div>
    );
  }

  if (!scriptId) {
    return <StudioSessionResolve sessionId={sessionId} onRefresh={onRefresh} />;
  }

  return (
    <StudioWorkspace
      key={`${sessionId}-${scriptId}`}
      sessionId={sessionId}
      scriptId={scriptId}
      onRefresh={onRefresh}
      initialTranscriptOpen={initialTranscriptOpen}
    />
  );
}
