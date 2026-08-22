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
import { EpisodeInspector } from "./EpisodeInspector";
import { EpisodeAudioDock } from "./EpisodeAudioDock";
import { StudioHeader } from "./StudioHeader";
import { SourceDrawer } from "./SourceDrawer";
import {
  buildPreviewExcerpt,
  buildVoiceFreshnessKey,
  deriveAudioFreshness,
  deriveEpisodeRenderReadiness,
} from "./studioWorkflow";
import {
  deriveEpisodeProductStatus,
  isProjectAudioOutOfDate,
  isProjectSourceOutOfDate,
  projectHasSelectedVoice,
} from "../../lib/episodeStatus";

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
      Opening episode…
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

  const [transcriptOpen, setTranscriptOpen] = useState(initialTranscriptOpen);
  const [sourceOpen, setSourceOpen] = useState(initialSourceOpen);
  const [previewLabel, setPreviewLabel] = useState("Current paragraph");

  // Audio out-of-date: set when script or voice inputs change after audio exists.
  const [audioOutOfDate, setAudioOutOfDate] = useState(false);
  const [audioOutOfDateReason, setAudioOutOfDateReason] = useState<string | undefined>(undefined);
  const prevAudioSrcRef = useRef(workbench.audioSrc);
  const prevScriptRef = useRef<string | null>(null);
  const prevVoiceKeyRef = useRef<string | null>(null);

  const serverScript = workbench.project?.script?.final ?? workbench.project?.script?.draft ?? "";
  const voiceFreshnessKey = buildVoiceFreshnessKey(workbench.project, scriptId, workbench.voiceSettings);
  const sourceOutOfDate = isProjectSourceOutOfDate(workbench.project);
  const persistedAudioOutOfDate = isProjectAudioOutOfDate(workbench.project, scriptId, workbench.isDirty);

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
    if (persistedAudioOutOfDate) {
      setAudioOutOfDate(true);
      setAudioOutOfDateReason("This audio was generated from an earlier version of the script.");
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
    persistedAudioOutOfDate,
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
      setAudioOutOfDate(sourceOutOfDate || persistedAudioOutOfDate);
      setAudioOutOfDateReason(
        sourceOutOfDate
          ? "The imported source changed after this script and audio were generated."
          : persistedAudioOutOfDate
            ? "This audio was generated from an earlier version of the script."
            : undefined,
      );
      prevScriptRef.current = serverScript;
      prevVoiceKeyRef.current = voiceFreshnessKey;
    }
    prevAudioSrcRef.current = workbench.audioSrc;
  }, [persistedAudioOutOfDate, serverScript, sourceOutOfDate, voiceFreshnessKey, workbench.audioSrc]);

  const readiness = deriveEpisodeRenderReadiness({
    scriptReady: workbench.scriptCheck.canRender,
    hasSelectedVoice: projectHasSelectedVoice(workbench.project, scriptId),
    selectedEngine: workbench.selectedEngine,
    selectedModelId: workbench.selectedModelId,
    capability: workbench.capability,
    ttsConfig: workbench.ttsConfig,
  });
  const productStatus = deriveEpisodeProductStatus({
    project: workbench.project,
    scriptId,
    isDirty: workbench.isDirty,
    generating: workbench.generating,
    generationFailed: workbench.audioRequestState?.phase === "failed",
    audioOutOfDate: audioOutOfDate || persistedAudioOutOfDate,
    readyToGenerate: readiness.ready && !sourceOutOfDate,
  });

  const handlePreview = () => {
    const textarea = workbench.textareaRef.current;
    const excerpt = buildPreviewExcerpt(
      workbench.script,
      textarea?.selectionStart ?? 0,
      textarea?.selectionEnd ?? textarea?.selectionStart ?? 0,
    );
    setPreviewLabel(excerpt.label);
    void workbench.handleRenderPreview(excerpt.text);
  };

  if (workbench.loading) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        <Loader2 className="w-4 h-4 animate-spin mr-2" />
        Loading episode…
      </div>
    );
  }

  if (!workbench.project) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        {workbench.loadingError || "This episode workspace is unavailable."}
      </div>
    );
  }

  return (
    <>
      {/* ── Full-height studio layout ──────────────────────── */}
      <div className="flex flex-col h-full w-full overflow-hidden bg-background">

        <StudioHeader
          workbench={workbench}
          listTopic={listTopic}
          status={productStatus}
          onSourceOpen={() => {
            setTranscriptOpen(false);
            setSourceOpen(true);
          }}
          onConversationOpen={() => {
            setSourceOpen(false);
            setTranscriptOpen(true);
          }}
        />

        {/* Script remains the primary canvas; supporting material and settings stay peripheral. */}
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

          <div className="flex flex-col w-full lg:flex-1 min-w-0 min-h-[560px] lg:min-h-0 overflow-hidden">
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
              <ScriptEditorPane workbench={workbench} />
            </div>
          </div>

          <div className="w-full shrink-0 border-t border-outline lg:w-[300px] lg:overflow-hidden lg:border-l lg:border-t-0 xl:w-[320px]">
            <EpisodeInspector
              workbench={workbench}
              scriptId={scriptId}
              readiness={readiness}
            />
          </div>
        </div>

        <EpisodeAudioDock
          workbench={workbench}
          status={productStatus}
          readiness={readiness}
          audioOutOfDate={audioOutOfDate || persistedAudioOutOfDate}
          audioOutOfDateReason={audioOutOfDateReason}
          sourceOutOfDate={sourceOutOfDate}
          previewLabel={previewLabel}
          onPreview={handlePreview}
          onReviewSource={() => {
            setTranscriptOpen(false);
            setSourceOpen(true);
          }}
        />
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
