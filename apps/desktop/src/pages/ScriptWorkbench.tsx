import { motion } from "framer-motion";
import { useParams } from "react-router-dom";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ScriptCleanupPreviewDialog } from "./script-workbench/ScriptCleanupPreviewDialog";
import { ScriptAudioSidebar } from "./script-workbench/ScriptAudioSidebar";
import { ScriptEditorPane } from "./script-workbench/ScriptEditorPane";
import { ScriptWorkbenchHeader } from "./script-workbench/ScriptWorkbenchHeader";
import { useScriptWorkbench } from "./script-workbench/useScriptWorkbench";

function ScriptStateBanner({
  title,
  description,
  actionLabel,
  disabled,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel: string;
  disabled?: boolean;
  onAction: () => Promise<void>;
}) {
  return (
    <div className="rounded-2xl border border-accent-amber/25 bg-accent-amber/10 px-4 py-3 text-sm text-primary">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="font-medium">{title}</p>
          <p className="mt-1 text-xs text-secondary">{description}</p>
        </div>
        <button
          type="button"
          onClick={() => void onAction()}
          disabled={disabled}
          className="inline-flex min-h-11 items-center justify-center rounded-xl border border-outline bg-surface-container px-4 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 disabled:opacity-50"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}

export function ScriptWorkbench({
  sessionId,
  scriptId,
  onRefresh,
}: {
  sessionId: string;
  scriptId: string;
  onRefresh: () => Promise<void>;
}) {
  const { sessionId: routeSessionId, scriptId: routeScriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const workbench = useScriptWorkbench(sessionId || routeSessionId || "", scriptId || routeScriptId || "", onRefresh);
  const regenerationDialog = workbench.dialogState?.kind === "regenerate-window" ? workbench.dialogState : null;
  const regenerationPositions = regenerationDialog?.windowSegmentIds.map((segmentId) => {
    const segment = workbench.project?.speech_plan?.segments.find((item) => item.segment_id === segmentId);
    return segment ? segment.position + 1 : null;
  }).filter((position): position is number => position !== null) ?? [];

  if (workbench.loading) {
    return <div className="flex h-full items-center justify-center text-secondary text-sm">Loading script workspace...</div>;
  }

  if (!workbench.project) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        {workbench.loadingError || "Script workspace is unavailable for this session."}
      </div>
    );
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex h-full min-h-0 w-full overflow-y-auto px-4 py-5 lg:px-6"
      >
        <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-5">
          <ScriptWorkbenchHeader workbench={workbench} />

          {workbench.isSessionDeleted ? (
            <ScriptStateBanner
              title="This session is in trash."
              description="Restore it before editing the script or rendering audio."
              actionLabel="Restore Session"
              disabled={workbench.busyAction === "restore-session"}
              onAction={workbench.handleRestoreSession}
            />
          ) : null}

          {workbench.isScriptDeleted ? (
            <ScriptStateBanner
              title="This script snapshot is in trash."
              description="Restore it to resume editing or render audio."
              actionLabel="Restore Script"
              disabled={workbench.busyAction === "restore-script" || workbench.isSessionDeleted}
              onAction={workbench.handleRestoreScript}
            />
          ) : null}

          <div className="flex flex-col gap-5">
            <ScriptEditorPane workbench={workbench} />
            <ScriptAudioSidebar workbench={workbench} />
          </div>
        </div>
      </motion.div>

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

      <ScriptCleanupPreviewDialog
        open={workbench.dialogState?.kind === "cleanup-preview"}
        preview={workbench.dialogState?.kind === "cleanup-preview" ? workbench.dialogState.preview : null}
        onClose={workbench.closeDialog}
        onApply={workbench.handleApplyCleanup}
      />
    </>
  );
}
