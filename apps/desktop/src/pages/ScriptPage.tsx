import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronRight, Trash2 } from "lucide-react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { SessionProject } from "../types";
import { useBridge } from "../lib/BridgeContext";
import { ScriptWorkbench } from "./ScriptWorkbench";

type ScriptListDeleteTarget = {
  project: SessionProject;
  kind: "script" | "session";
};

export function ScriptPage({
  projects,
  onRefresh,
}: {
  projects: SessionProject[];
  onRefresh: () => Promise<void>;
}) {
  const { sessionId, scriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const navigate = useNavigate();
  const bridge = useBridge();
  const [deleteTarget, setDeleteTarget] = useState<ScriptListDeleteTarget | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState("");

  const handleOpenLatestScript = async (targetSessionId: string) => {
    try {
      const project = await bridge.showLatestScript(targetSessionId);
      if (project.script?.script_id) {
        navigate(`/script/${targetSessionId}/${project.script.script_id}`);
        return;
      }
    } catch {
      // Fall through to Chat when no latest script is available.
    }
    navigate(`/chat/${targetSessionId}`);
  };

  const handleDeleteTarget = async (target: ScriptListDeleteTarget) => {
    const targetSessionId = target.project.session.session_id;
    const targetScriptId = target.project.script?.script_id ?? "";
    setDeletingId(target.kind === "script" ? targetScriptId : targetSessionId);
    setListError(null);
    try {
      if (target.kind === "script" && targetScriptId) {
        await bridge.deleteScript(targetSessionId, targetScriptId);
      } else {
        await bridge.deleteSession(targetSessionId);
      }
      await onRefresh();
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Failed to move item to trash.");
    } finally {
      setDeletingId("");
    }
  };

  const sorted = [...projects].sort((a, b) =>
    b.session.updated_at.localeCompare(a.session.updated_at),
  );

  if (!sessionId) {
    return (
      <>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col h-full w-full overflow-y-auto px-6 lg:px-12 py-8"
        >
          <div className="max-w-2xl mx-auto w-full">
            <div className="mb-8 border-b border-outline pb-6">
              <h1 className="text-2xl font-headline font-bold text-primary mb-2">Script</h1>
              <p className="text-secondary text-sm">
                Open generated scripts, or continue unfinished chats before they become scripts.
              </p>
            </div>
            {listError ? (
              <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {listError}
              </div>
            ) : null}
            <div className="rounded-xl border border-outline bg-surface-container-low overflow-hidden divide-y divide-outline-variant">
              {sorted.length === 0 ? (
                <div className="p-8 text-center text-secondary text-sm">
                  No sessions yet. Start a chat to create one.
                </div>
              ) : (
                sorted.map((p) => {
                  const hasScript = Boolean(p.script?.script_id);
                  const title = p.session.topic || "Untitled";
                  const rowId = hasScript ? p.script?.script_id ?? "" : p.session.session_id;
                  return (
                    <div
                      key={p.session.session_id}
                      className="flex items-center gap-2 px-4 py-3 hover:bg-surface-container transition-colors"
                    >
                      <button
                        type="button"
                        onClick={() => void handleOpenLatestScript(p.session.session_id)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <p className="font-medium text-[14px] text-primary truncate">
                          {title}
                        </p>
                        <p className="text-[12px] text-secondary truncate">
                          {hasScript ? p.session.state.replace(/_/g, " ") : "未生成脚本 · 点击继续对话"}
                        </p>
                      </button>
                      <button
                        type="button"
                        aria-label={hasScript ? `Move script ${title} to trash` : `Move chat ${title} to trash`}
                        disabled={deletingId === rowId}
                        onClick={() => setDeleteTarget({ project: p, kind: hasScript ? "script" : "session" })}
                        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                      <ChevronRight className="w-4 h-4 text-outline shrink-0" />
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </motion.div>
        <ConfirmDialog
          open={deleteTarget !== null}
          title={deleteTarget?.kind === "script" ? "Move script to trash?" : "Move unfinished chat to trash?"}
          message={
            deleteTarget
              ? `Move "${deleteTarget.project.session.topic || "Untitled"}" to trash?`
              : ""
          }
          onClose={() => setDeleteTarget(null)}
          actions={[
            {
              label: "Cancel",
              onClick: () => setDeleteTarget(null),
            },
            {
              label: "Move to trash",
              onClick: () => {
                const target = deleteTarget;
                setDeleteTarget(null);
                if (!target) return;
                void handleDeleteTarget(target);
              },
              variant: "danger",
            },
          ]}
        />
      </>
    );
  }

  if (!scriptId) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center">
        <div className="max-w-sm rounded-2xl border border-outline bg-surface p-6">
          <p className="text-sm text-secondary">Missing script id. Use the script list or open from chat.</p>
          <button
            type="button"
            onClick={() => navigate("/script")}
            className="mt-4 rounded-xl border border-outline bg-surface-container-low px-4 py-2 text-sm font-medium text-primary hover:border-accent-amber/30"
          >
            返回脚本列表
          </button>
        </div>
      </div>
    );
  }

  return <ScriptWorkbench key={`${sessionId}-${scriptId}`} sessionId={sessionId} scriptId={scriptId} onRefresh={onRefresh} />;
}
