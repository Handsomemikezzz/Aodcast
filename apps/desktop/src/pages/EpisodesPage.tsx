import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, MessageSquare, Plus, Trash2 } from "lucide-react";
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
      <div className="flex flex-col h-full w-full overflow-y-auto px-6 lg:px-10 py-8">
        <div className="max-w-3xl mx-auto w-full">
          <div className="mb-6 flex items-center justify-between gap-4">
            <h1 className="text-2xl font-headline font-semibold text-primary">Episodes</h1>
            <button
              type="button"
              onClick={handleNewEpisode}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-[13px] font-semibold text-background transition-opacity hover:opacity-90 shrink-0"
            >
              <Plus className="w-4 h-4" />
              New episode
            </button>
          </div>

          {listError ? (
            <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
              {listError}
            </div>
          ) : null}

          {sorted.length === 0 ? (
            <div className="rounded-xl border border-dashed border-outline px-6 py-14 text-center">
              <p className="text-sm font-medium text-primary">No episodes yet</p>
              <p className="mt-1 text-[13px] text-secondary">
                Start from an idea you want to talk through, or import an article you have written.
              </p>
              <button
                type="button"
                onClick={handleNewEpisode}
                className="mt-4 inline-flex h-9 items-center gap-1.5 rounded-lg border border-outline px-3.5 text-[13px] font-medium text-primary hover:bg-primary/5"
              >
                <Plus className="w-4 h-4" />
                New episode
              </button>
            </div>
          ) : (
            <ul className="-mx-3">
              {sorted.map((p) => {
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
                  <li
                    key={p.session.session_id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Open "${title}"`}
                    onClick={() => void openEpisode(displayProject)}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget) return;
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        void openEpisode(displayProject);
                      }
                    }}
                    className="group flex cursor-pointer items-center gap-3 rounded-lg px-3 py-3 transition-colors hover:bg-primary/[0.035] focus-visible:bg-primary/[0.035] focus-visible:outline-none"
                  >
                    <OriginIcon
                      className="h-4 w-4 shrink-0 text-secondary/70"
                      aria-label={isMarkdown ? "From Markdown" : "From conversation"}
                    />
                    <div className="min-w-0 flex-1">
                      <SessionTopicEditor
                        sessionId={displayProject.session.session_id}
                        topic={title}
                        disabled={busy}
                        density="list"
                        onRenamed={async () => {
                          setRenamingId(displayProject.session.session_id);
                          try {
                            await onRefresh();
                          } finally {
                            setRenamingId("");
                          }
                        }}
                      />
                      <div className="mt-0.5 flex items-center gap-1.5 truncate text-[12px] text-secondary">
                        <span className={episodeStatusTone(status.kind)}>{status.label}</span>
                        {duration ? <><span aria-hidden>·</span><span className="tabular-nums">{duration}</span></> : null}
                        {updated ? <><span aria-hidden>·</span><span>{updated}</span></> : null}
                      </div>
                    </div>
                    <button
                      type="button"
                      aria-label={`Move "${title}" to trash`}
                      title="Move to trash"
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        setDeleteTarget({ project: displayProject, kind: hasScript ? "script" : "session" });
                      }}
                      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-secondary opacity-0 transition hover:bg-red-500/10 hover:text-red-600 focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100 disabled:opacity-50 dark:hover:text-red-300"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

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
