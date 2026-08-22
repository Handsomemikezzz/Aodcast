import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useBridge } from "../../lib/BridgeContext";
import type { SessionProject } from "../../types";
import { useScriptWorkbench } from "../script-workbench/useScriptWorkbench";
import { ScriptEditorPane } from "../script-workbench/ScriptEditorPane";
import { ScriptCleanupPreviewDialog } from "../script-workbench/ScriptCleanupPreviewDialog";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ChatPage } from "../ChatPage";
import { ConversationDrawer } from "./ConversationDrawer";
import { VoiceAudioPanel } from "./VoiceAudioDrawer";
import { StudioHeader } from "./StudioHeader";
import { TranscriptBar } from "./TranscriptBar";
import { SourceBar, SourceDrawer } from "./SourceDrawer";
import { buildVoiceFreshnessKey, deriveAudioFreshness } from "./studioWorkflow";
import { isProjectSourceOutOfDate } from "../../lib/deriveStudioState";

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
  listTopic,
  initialTranscriptOpen,
  initialSourceOpen,
}: {
  sessionId: string;
  scriptId: string;
  onRefresh: () => Promise<void>;
  listTopic?: string;
  initialTranscriptOpen: boolean;
  initialSourceOpen: boolean;
}) {
  const bridge = useBridge();
  const navigate = useNavigate();
  const workbench = useScriptWorkbench(sessionId, scriptId, onRefresh);

  useEffect(() => {
    if (listTopic) workbench.applyLocalTopic(listTopic);
  }, [listTopic, workbench.applyLocalTopic]);

  const regenerationDialog = workbench.dialogState?.kind === "regenerate-window" ? workbench.dialogState : null;
  const regenerationPositions = regenerationDialog?.windowSegmentIds.map((segmentId) => {
    const segment = workbench.project?.speech_plan?.segments.find((item) => item.segment_id === segmentId);
    return segment ? segment.position + 1 : null;
  }).filter((position): position is number => position !== null) ?? [];

  // Transcript overlay state
  const [transcriptOpen, setTranscriptOpen] = useState(initialTranscriptOpen);
  const [sourceOpen, setSourceOpen] = useState(initialSourceOpen);

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
  const sourceOutOfDate = isProjectSourceOutOfDate(workbench.project);

  useEffect(() => {
    const hasAudio = Boolean(workbench.audioSrc);
    if (!hasAudio) {
      setAudioOutOfDate(false);
      setAudioOutOfDateReason(undefined);
      prevScriptRef.current = serverScript;
      prevVoiceKeyRef.current = voiceFreshnessKey;
      return;
    }
    if (sourceOutOfDate) {
      setAudioOutOfDate(true);
      setAudioOutOfDateReason("The imported source changed after this script and audio were generated.");
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
    sourceOutOfDate,
    voiceFreshnessKey,
    workbench.audioSrc,
    workbench.generating,
    workbench.isDirty,
    workbench.script,
  ]);

  // Clear out-of-date state when a new audio render completes
  useEffect(() => {
    if (workbench.audioSrc && workbench.audioSrc !== prevAudioSrcRef.current) {
      setAudioOutOfDate(sourceOutOfDate);
      setAudioOutOfDateReason(
        sourceOutOfDate ? "The imported source changed after this script and audio were generated." : undefined,
      );
      prevScriptRef.current = serverScript;
      prevVoiceKeyRef.current = voiceFreshnessKey;
    }
    prevAudioSrcRef.current = workbench.audioSrc;
  }, [serverScript, sourceOutOfDate, voiceFreshnessKey, workbench.audioSrc]);

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
          listTopic={listTopic}
          audioOutOfDate={audioOutOfDate}
          sourceOutOfDate={sourceOutOfDate}
          onMaterialOpen={() => {
            if (workbench.project?.source) setSourceOpen(true);
            else setTranscriptOpen(true);
          }}
          onScriptFocus={handleScriptFocus}
          onVoiceNavigate={handleVoiceNavigate}
          onAudioFocus={handleAudioFocus}
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
          <SourceDrawer
            project={workbench.project}
            isOpen={sourceOpen}
            onClose={() => setSourceOpen(false)}
            onDiscuss={() => {
              setSourceOpen(false);
              setTranscriptOpen(true);
            }}
            onUpdated={async () => {
              await Promise.all([workbench.reload(), onRefresh()]);
            }}
            onGenerateScript={async () => {
              const result = await bridge.generateScript(sessionId);
              const nextScriptId = result.script_id ?? result.project.script?.script_id;
              await onRefresh();
              if (nextScriptId) navigate(`/studio/${sessionId}/${nextScriptId}`);
            }}
          />

          {/* ── Left column: transcript bar + script editor ── */}
          <div className="flex flex-col w-full lg:flex-1 min-w-0 min-h-[560px] lg:min-h-0 overflow-hidden">

            {/* Transcript collapsed bar */}
            {workbench.project.source ? (
              <SourceBar project={workbench.project} onOpen={() => setSourceOpen(true)} />
            ) : (
              <TranscriptBar
                turnCount={turns.length}
                onOpen={() => setTranscriptOpen(true)}
              />
            )}

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
        open={regenerationDialog !== null}
        title="重新生成上下文窗口？"
        message={
          regenerationPositions.length
            ? `将重新生成第 ${regenerationPositions.join("、")} 段。相邻段会一起生成以保持语气连续；全部成功前，当前音频保持不变。`
            : "将重新生成目标段及其相邻上下文。全部成功前，当前音频保持不变。"
        }
        onClose={workbench.closeDialog}
        actions={[
          { label: "取消", onClick: workbench.closeDialog },
          {
            label: "重新生成窗口",
            onClick: () => {
              const targetSegmentId = regenerationDialog?.targetSegmentId ?? "";
              workbench.setDialogState(null);
              if (targetSegmentId) void workbench.handleRegenerateAudioWindow(targetSegmentId);
            },
            variant: "primary",
            disabled: workbench.generating || workbench.speechPlanStale,
          },
        ]}
      />

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
    </>
  );
}

// ── Entry Point ──────────────────────────────────────────────────────────────
export function StudioPage({
  projects = [],
  onRefresh,
}: {
  projects?: SessionProject[];
  onRefresh: () => Promise<void>;
}) {
  const { sessionId, scriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const [searchParams] = useSearchParams();

  const panelParam = searchParams.get("panel");
  const initialTranscriptOpen = panelParam === "conversation";
  const initialSourceOpen = panelParam === "source";
  const listTopic = projects.find((item) => item.session.session_id === sessionId)?.session.topic;

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
      listTopic={listTopic}
      initialTranscriptOpen={initialTranscriptOpen}
      initialSourceOpen={initialSourceOpen}
    />
  );
}
