import { ArrowLeft, FileText, MessageSquare, RefreshCw, Trash2 } from "lucide-react";
import { OverflowMenu } from "../../components/OverflowMenu";
import { SessionTopicEditor } from "../../components/SessionTopicEditor";
import type { UseScriptWorkbenchResult } from "../script-workbench/useScriptWorkbench";

const headerButtonClass =
  "inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-secondary transition-colors hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50";

export function StudioHeader({
  workbench,
  listTopic,
  onSourceOpen,
  onConversationOpen,
}: {
  workbench: UseScriptWorkbenchResult;
  listTopic?: string;
  onSourceOpen: () => void;
  onConversationOpen: () => void;
}) {
  const project = workbench.project;
  const topic = listTopic?.trim() || project?.session.topic || "Untitled Episode";
  const sessionId = project?.session.session_id ?? "";
  const source = project?.source;
  const turnCount = project?.transcript?.turns.length ?? 0;
  const deleted = workbench.isScriptDeleted || workbench.isSessionDeleted;

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-outline px-3">
      <button
        type="button"
        onClick={() => workbench.navigate("/episodes")}
        aria-label="Back to Episodes"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
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
      </div>

      <div className="flex items-center gap-0.5">
        {source ? (
          <button type="button" onClick={onSourceOpen} className={headerButtonClass}>
            <FileText className="h-4 w-4" />
            <span className="hidden sm:inline">Source</span>
          </button>
        ) : null}
        <button type="button" onClick={onConversationOpen} className={headerButtonClass}>
          <MessageSquare className="h-4 w-4" />
          <span className="hidden sm:inline">Conversation</span>
          {turnCount ? <span className="text-[11px] tabular-nums text-secondary/70">{turnCount}</span> : null}
        </button>
        <OverflowMenu
          label="More script actions"
          items={[
            {
              label: "Reload script",
              icon: RefreshCw,
              onSelect: () => workbench.runWithUnsavedCheck(async () => {
                await workbench.reload();
              }),
            },
            {
              label: "Move script to trash",
              icon: Trash2,
              danger: true,
              disabled: deleted || workbench.busyAction === "delete-script",
              onSelect: () => workbench.setDialogState({ kind: "delete-script" }),
            },
          ]}
        />
      </div>
    </header>
  );
}
