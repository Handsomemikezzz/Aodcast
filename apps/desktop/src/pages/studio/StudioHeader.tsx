import { ArrowLeft, FileText, MessageSquare } from "lucide-react";
import { SessionTopicEditor } from "../../components/SessionTopicEditor";
import { episodeStatusTone, type EpisodeProductStatus } from "../../lib/episodeStatus";
import type { UseScriptWorkbenchResult } from "../script-workbench/useScriptWorkbench";

export function StudioHeader({
  workbench,
  listTopic,
  status,
  onSourceOpen,
  onConversationOpen,
}: {
  workbench: UseScriptWorkbenchResult;
  listTopic?: string;
  status: EpisodeProductStatus;
  onSourceOpen: () => void;
  onConversationOpen: () => void;
}) {
  const project = workbench.project;
  const topic = listTopic?.trim() || project?.session.topic || "Untitled Episode";
  const sessionId = project?.session.session_id ?? "";
  const source = project?.source;
  const turnCount = project?.transcript?.turns.length ?? 0;

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-outline bg-surface-container-low/72 px-4 py-3 backdrop-blur-sm lg:flex-nowrap lg:px-5">
      <button
        type="button"
        onClick={() => workbench.navigate("/episodes")}
        aria-label="Back to Episodes"
        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-secondary transition-colors hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
      >
        <ArrowLeft className="h-4 w-4" />
      </button>

      <div className="min-w-0 flex-1">
        {sessionId ? (
          <SessionTopicEditor
            sessionId={sessionId}
            topic={topic}
            density="header"
            disabled={workbench.isSessionDeleted || workbench.generating}
            onRenamed={workbench.handleRenameTopic}
          />
        ) : (
          <h1 className="truncate text-sm font-semibold text-primary">{topic}</h1>
        )}
        <p className={`mt-0.5 text-[11px] font-medium ${episodeStatusTone(status.kind)}`} aria-live="polite">
          {status.label}
        </p>
      </div>

      <div className="flex items-center gap-2">
        {source ? (
          <button
            type="button"
            onClick={onSourceOpen}
            className="inline-flex h-11 items-center gap-2 rounded-xl border border-outline bg-surface-container-low px-3 text-xs font-semibold text-secondary transition-colors hover:bg-surface-container-high hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
          >
            <FileText className="h-4 w-4" />
            <span className="hidden sm:inline">Source</span>
          </button>
        ) : null}
        <button
          type="button"
          onClick={onConversationOpen}
          className="inline-flex h-11 items-center gap-2 rounded-xl border border-outline bg-surface-container-low px-3 text-xs font-semibold text-secondary transition-colors hover:bg-surface-container-high hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
        >
          <MessageSquare className="h-4 w-4" />
          <span className="hidden sm:inline">Conversation</span>
          {turnCount ? (
            <span className="rounded-full bg-primary/7 px-1.5 py-0.5 text-[9px] tabular-nums text-secondary">{turnCount}</span>
          ) : null}
        </button>
      </div>
    </header>
  );
}
