import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronRight, PlusCircle, Trash2 } from "lucide-react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import type { SessionProject } from "../types";
import { useBridge } from "../lib/BridgeContext";

type DeleteTarget = {
  project: SessionProject;
  kind: "script" | "session";
};

export function EpisodesPage({
  projects,
  onRefresh,
}: {
  projects: SessionProject[];
  onRefresh: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const bridge = useBridge();
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState("");
  const openEpisode = async (project: SessionProject) => {
    const sid = project.session.session_id;
    if (project.script?.script_id) {
      navigate(`/studio/${sid}/${project.script.script_id}`);
      return;
    }
    try {
      const latest = await bridge.showLatestScript(sid);
      if (latest.script?.script_id) {
        navigate(`/studio/${sid}/${latest.script.script_id}`);
        return;
      }
    } catch {
      // session has no script yet
    }
    navigate(`/studio/${sid}`);
  };

  const handleNewEpisode = () => {
    navigate("/studio");
  };

  const handleDeleteTarget = async (target: DeleteTarget) => {
    const sid = target.project.session.session_id;
    const scriptId = target.project.script?.script_id ?? "";
    setDeletingId(target.kind === "script" ? scriptId : sid);
    setListError(null);
    try {
      if (target.kind === "script" && scriptId) {
        await bridge.deleteScript(sid, scriptId);
      } else {
        await bridge.deleteSession(sid);
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

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col h-full w-full overflow-y-auto px-6 lg:px-12 py-8"
      >
        <div className="max-w-2xl mx-auto w-full">
          <div className="mb-8 border-b border-outline pb-6 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-headline font-bold text-primary mb-2">Episodes</h1>
              <p className="text-secondary text-sm">
                Create and manage your podcast episodes.
              </p>
            </div>
            <button
              type="button"
              onClick={handleNewEpisode}
              className="flex items-center gap-2 rounded-xl bg-accent-amber/10 border border-accent-amber/30 px-4 py-2 text-sm font-medium text-accent-amber hover:bg-accent-amber/15 transition-colors shrink-0"
            >
              <PlusCircle className="w-4 h-4" />
              New Episode
            </button>
          </div>

          {listError ? (
            <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {listError}
            </div>
          ) : null}

          <div className="rounded-xl border border-outline bg-surface-container-low overflow-hidden divide-y divide-outline-variant">
            {sorted.length === 0 ? (
              <div className="p-8 text-center text-secondary text-sm">
                No episodes yet. Create your first one above.
              </div>
            ) : (
              sorted.map((p) => {
                const hasScript = Boolean(p.script?.script_id);
                const title = p.session.topic || "Untitled Episode";
                const rowId = hasScript ? (p.script?.script_id ?? "") : p.session.session_id;
                const statusLabel = p.session.state.replace(/_/g, " ");
                return (
                  <div
                    key={p.session.session_id}
                    className="flex items-center gap-2 px-4 py-3 hover:bg-surface-container transition-colors"
                  >
                    <button
                      type="button"
                      onClick={() => void openEpisode(p)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <p className="font-medium text-[14px] text-primary truncate">{title}</p>
                      <p className="text-[12px] text-secondary truncate capitalize">{statusLabel}</p>
                    </button>
                    <button
                      type="button"
                      aria-label={`Move "${title}" to trash`}
                      disabled={deletingId === rowId}
                      onClick={() =>
                        setDeleteTarget({ project: p, kind: hasScript ? "script" : "session" })
                      }
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
        title={
          deleteTarget?.kind === "script"
            ? "Move episode to trash?"
            : "Move unfinished episode to trash?"
        }
        message={
          deleteTarget
            ? `Move "${deleteTarget.project.session.topic || "Untitled Episode"}" to trash?`
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
