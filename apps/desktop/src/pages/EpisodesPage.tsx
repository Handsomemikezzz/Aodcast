import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronRight, FileText, MessageSquare, PlusCircle, Trash2 } from "lucide-react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { SessionTopicEditor } from "../components/SessionTopicEditor";
import type { SessionProject } from "../types";
import { useBridge } from "../lib/BridgeContext";
import {
  deriveEpisodeProductStatus,
  episodeStatusTone,
  formatEpisodeDuration,
  formatRelativeEpisodeTime,
} from "../lib/episodeStatus";

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
  const [renamingId, setRenamingId] = useState("");
  const [projectDetails, setProjectDetails] = useState<Record<string, SessionProject>>({});

  useEffect(() => {
    let cancelled = false;
    void Promise.all(
      projects.map(async (project) => {
        try {
          return await bridge.showLatestScript(project.session.session_id);
        } catch {
          return project;
        }
      }),
    ).then((items) => {
      if (!cancelled) {
        setProjectDetails(Object.fromEntries(items.map((item) => [item.session.session_id, item])));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [bridge, projects]);
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
    navigate("/episodes/new");
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
        <div className="max-w-3xl mx-auto w-full">
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
              className="flex h-11 items-center gap-2 rounded-xl bg-accent-amber/10 border border-accent-amber/30 px-4 text-sm font-medium text-accent-amber hover:bg-accent-amber/15 transition-colors shrink-0"
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
                const displayProject = projectDetails[p.session.session_id] ?? p;
                const hasScript = Boolean(displayProject.script?.script_id);
                const title = displayProject.session.topic || "Untitled Episode";
                const rowId = hasScript ? (displayProject.script?.script_id ?? "") : displayProject.session.session_id;
                const status = deriveEpisodeProductStatus({
                  project: displayProject,
                  scriptId: displayProject.script?.script_id,
                });
                const duration = formatEpisodeDuration(displayProject);
                const updated = formatRelativeEpisodeTime(displayProject.session.updated_at);
                const isMarkdown = displayProject.session.creation_mode === "markdown";
                const OriginIcon = isMarkdown ? FileText : MessageSquare;
                const busy = deletingId === rowId || renamingId === displayProject.session.session_id;
                return (
                  <div
                    key={p.session.session_id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Open "${title}"`}
                    onClick={() => void openEpisode(displayProject)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        void openEpisode(displayProject);
                      }
                    }}
                    className="flex cursor-pointer items-center gap-2 px-4 py-3 hover:bg-surface-container transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1 min-w-0">
                        <SessionTopicEditor
                          sessionId={displayProject.session.session_id}
                          topic={title}
                          disabled={busy}
                          density="list"
                          className="flex-1"
                          onRenamed={async () => {
                            setRenamingId(displayProject.session.session_id);
                            try {
                              await onRefresh();
                            } finally {
                              setRenamingId("");
                            }
                          }}
                        />
                      </div>
                      <div className="mt-1 flex w-full items-center gap-1.5 truncate text-left text-[12px]">
                        <span className={episodeStatusTone(status.kind)}>{status.label}</span>
                        {duration ? <><span className="text-outline">·</span><span className="tabular-nums text-secondary">{duration}</span></> : null}
                      </div>
                      <div className="mt-1 flex items-center gap-1.5 text-[11px] text-secondary/75">
                        <OriginIcon className="h-3 w-3 shrink-0" aria-hidden="true" />
                        <span>{isMarkdown ? "Markdown" : "Conversation"}</span>
                        {updated ? <><span className="text-outline">·</span><span>{updated}</span></> : null}
                      </div>
                    </div>
                    <button
                      type="button"
                      aria-label={`Move "${title}" to trash`}
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        setDeleteTarget({ project: displayProject, kind: hasScript ? "script" : "session" });
                      }}
                      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                    <span
                      aria-hidden
                      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-outline"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </span>
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
