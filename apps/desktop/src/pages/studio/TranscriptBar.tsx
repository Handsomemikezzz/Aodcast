import { MessageSquare, ChevronRight } from "lucide-react";

export function TranscriptBar({
  turnCount,
  onOpen,
}: {
  turnCount: number;
  onOpen: () => void;
}) {
  if (turnCount === 0) {
    return (
      <div className="shrink-0 px-4 py-2 flex items-center gap-2 border-b border-outline bg-surface-container-low/40">
        <MessageSquare className="w-3.5 h-3.5 text-secondary/50 shrink-0" />
        <span className="text-[11px] text-secondary/50">No interview transcript yet.</span>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      className="shrink-0 w-full px-4 py-2 flex items-center gap-2 border-b border-outline bg-surface-container-low/40 hover:bg-surface-container-high/50 transition-colors group cursor-pointer text-left"
      title="View interview transcript"
    >
      <MessageSquare className="w-3.5 h-3.5 text-accent-amber shrink-0" />
      <span className="text-[11px] font-medium text-secondary">
        Interview complete
        <span className="mx-1.5 text-outline">·</span>
        <span className="text-primary font-semibold">{turnCount} turn{turnCount !== 1 ? "s" : ""}</span>
      </span>
      <span className="ml-auto flex items-center gap-0.5 text-[10px] font-semibold text-accent-amber group-hover:text-accent-amber/80 transition-colors">
        View transcript
        <ChevronRight className="w-3 h-3" />
      </span>
    </button>
  );
}
