import { useRef, useState } from "react";
import { Brain, Check, Loader2, MessageSquare, Send, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useBridge } from "../../lib/BridgeContext";
import { cn } from "../../lib/utils";
import { getErrorMessage } from "../../lib/requestState";
import type { MemoryEntry, SessionProject, TranscriptTurn } from "../../types";

type FollowUpState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "choice"; newTurns: TranscriptTurn[] }
  | { kind: "authorize"; candidates: MemoryEntry[] };

function TranscriptView({ turns }: { turns: TranscriptTurn[] }) {
  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      {turns.map((turn, i) => (
        <div
          key={i}
          className={cn(
            "flex flex-col gap-1",
            turn.speaker === "user" ? "items-end" : "items-start",
          )}
        >
          <div
            className={cn(
              "max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed",
              turn.speaker === "user"
                ? "bg-accent-amber/10 border border-accent-amber/20 text-primary"
                : "bg-primary/4 border border-outline text-secondary",
            )}
          >
            <ReactMarkdown>{turn.content}</ReactMarkdown>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * ConversationDrawer — overlay version.
 * Controlled by `isOpen` / `onClose` from the parent StudioWorkspace.
 * Does not manage its own open/close state.
 */
export function ConversationDrawer({
  project,
  isOpen,
  onClose,
  onRefresh,
  onNewScript,
}: {
  project: SessionProject | null;
  isOpen: boolean;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onNewScript: (sessionId: string, scriptId: string) => void;
}) {
  const bridge = useBridge();
  const [followUpInput, setFollowUpInput] = useState("");
  const [followUpState, setFollowUpState] = useState<FollowUpState>({ kind: "idle" });
  const [followUpError, setFollowUpError] = useState<string | null>(null);
  const [generatingSnapshot, setGeneratingSnapshot] = useState(false);
  const [authorizedIds, setAuthorizedIds] = useState<Set<string>>(new Set());
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  const sessionId = project?.session.session_id ?? "";
  const turns = project?.transcript?.turns ?? [];
  const memoryDisabled = project?.session.memory_mode === "disabled";
  const usageEvents = project?.session.memory_usage_events ?? [];
  const lastReferencedCount =
    usageEvents.length > 0 ? (usageEvents[usageEvents.length - 1].memory_ids?.length ?? 0) : 0;
  const [memoryBusy, setMemoryBusy] = useState(false);

  if (!isOpen) {
    return null;
  }

  const handleToggleMemory = async () => {
    if (!sessionId) return;
    setMemoryBusy(true);
    try {
      await bridge.setSessionMemoryMode(sessionId, memoryDisabled ? "enabled" : "disabled");
      await onRefresh();
    } catch {
      // Non-blocking: leave the toggle as-is on failure.
    } finally {
      setMemoryBusy(false);
    }
  };

  const handleFollowUpSubmit = async () => {
    const content = followUpInput.trim();
    if (!content || !sessionId) return;
    setFollowUpInput("");
    setFollowUpError(null);
    setFollowUpState({ kind: "submitting" });
    try {
      const result = await bridge.submitReplyStream(sessionId, content, () => {});
      const newTurns = result.project.transcript?.turns ?? [];
      setFollowUpState({ kind: "choice", newTurns });
      await onRefresh();
    } catch (err) {
      setFollowUpError(getErrorMessage(err, "Failed to submit follow-up."));
      setFollowUpState({ kind: "idle" });
    }
  };

  const handleGenerateSnapshot = async () => {
    if (!sessionId) return;
    setFollowUpError(null);
    // §14.4: surface relevant past experiences / sensitive memories for explicit
    // current-episode authorization before they can shape the script.
    try {
      const candidates = await bridge.listMemoryCandidates(sessionId);
      if (candidates.length > 0) {
        setAuthorizedIds(new Set());
        setFollowUpState({ kind: "authorize", candidates });
        return;
      }
    } catch {
      // Authorization is best-effort; fall through to generation on failure.
    }
    await doGenerateSnapshot();
  };

  const doGenerateSnapshot = async () => {
    if (!sessionId) return;
    setGeneratingSnapshot(true);
    setFollowUpError(null);
    try {
      await bridge.requestFinish(sessionId);
      const result = await bridge.generateScript(sessionId);
      const newScriptId = result.script_id ?? result.project.script?.script_id;
      if (newScriptId) {
        onNewScript(sessionId, newScriptId);
      }
      setFollowUpState({ kind: "idle" });
      await onRefresh();
    } catch (err) {
      setFollowUpError(getErrorMessage(err, "Failed to generate script snapshot."));
    } finally {
      setGeneratingSnapshot(false);
    }
  };

  const handleAuthorize = async (memoryId: string) => {
    if (!sessionId) return;
    try {
      await bridge.authorizeMemory(sessionId, memoryId);
      setAuthorizedIds((prev) => new Set(prev).add(memoryId));
      await onRefresh();
    } catch (err) {
      setFollowUpError(getErrorMessage(err, "Failed to authorize memory."));
    }
  };

  const handleKeepAsSource = () => {
    setFollowUpState({ kind: "idle" });
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          "transcript-overlay-backdrop",
          "transcript-overlay-backdrop-visible",
        )}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Overlay panel */}
      <div
        className={cn("transcript-overlay", "transcript-overlay-open")}
        aria-label="Interview transcript"
        role="complementary"
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-outline shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-secondary/70">
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Interview Transcript</span>
            <span className="px-1.5 py-0.5 rounded-full text-[9px] font-medium bg-surface-container-high/60 text-secondary">
              {turns.length} turns
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-secondary hover:text-primary hover:bg-surface-container-high/60 transition-colors cursor-pointer"
            aria-label="Close transcript"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Memory status + per-episode toggle */}
        <div className="px-4 py-2 border-b border-outline shrink-0 flex items-center justify-between gap-2 text-[11px]">
          <span className="flex items-center gap-1.5 text-secondary/80 min-w-0">
            <Brain className="w-3 h-3 text-accent-amber shrink-0" />
            {memoryDisabled ? (
              <span className="truncate">本集不使用记忆</span>
            ) : lastReferencedCount > 0 ? (
              <span className="truncate">本轮参考了 {lastReferencedCount} 条记忆</span>
            ) : (
              <span className="truncate">记忆已启用</span>
            )}
          </span>
          <button
            type="button"
            onClick={() => void handleToggleMemory()}
            disabled={memoryBusy}
            className="shrink-0 rounded-md border border-outline px-2 py-0.5 text-[10px] font-medium text-secondary hover:bg-primary/5 hover:text-primary transition-colors cursor-pointer disabled:opacity-50"
          >
            {memoryBusy ? "…" : memoryDisabled ? "启用记忆" : "本次不使用"}
          </button>
        </div>

        {/* Transcript scroll area */}
        <div className="flex-1 overflow-y-auto min-h-0 mac-scrollbar">
          {turns.length === 0 ? (
            <div className="flex items-center justify-center h-full text-secondary text-xs px-4 text-center">
              No conversation yet.
            </div>
          ) : (
            <TranscriptView turns={turns} />
          )}
          <div ref={transcriptEndRef} />
        </div>

        {/* Follow-up choice panel */}
        {followUpState.kind === "choice" ? (
          <div className="shrink-0 border-t border-outline bg-surface-container-high p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-accent-amber">
                Follow-up added
              </p>
              <button
                type="button"
                onClick={handleKeepAsSource}
                className="p-1 rounded text-secondary hover:text-primary hover:bg-primary/5 transition-colors cursor-pointer"
                aria-label="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-xs text-secondary leading-relaxed">
              What would you like to do with this new material?
            </p>
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={() => void handleGenerateSnapshot()}
                disabled={generatingSnapshot}
                className="flex items-center gap-2 w-full px-3 py-2.5 rounded-xl bg-accent-amber/10 border border-accent-amber/25 text-sm font-medium text-accent-amber hover:bg-accent-amber/15 transition-colors disabled:opacity-50 cursor-pointer"
              >
                {generatingSnapshot ? (
                  <Loader2 className="w-4 h-4 animate-spin shrink-0" />
                ) : (
                  <Sparkles className="w-4 h-4 shrink-0" />
                )}
                Generate new script snapshot
              </button>
              <button
                type="button"
                onClick={handleKeepAsSource}
                disabled={generatingSnapshot}
                className="flex items-center gap-2 w-full px-3 py-2.5 rounded-xl border border-outline bg-surface-container-low text-sm font-medium text-secondary hover:bg-primary/8 hover:text-primary transition-colors disabled:opacity-50 cursor-pointer"
              >
                <Check className="w-4 h-4 shrink-0" />
                Keep as source material
              </button>
            </div>
          </div>
        ) : null}

        {/* Memory authorization panel (before generating a snapshot) */}
        {followUpState.kind === "authorize" ? (
          <div className="shrink-0 border-t border-outline bg-surface-container-high p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-accent-amber">
                在脚本中引用这些过往经历?
              </p>
              <button
                type="button"
                onClick={handleKeepAsSource}
                className="p-1 rounded text-secondary hover:text-primary hover:bg-primary/5 transition-colors cursor-pointer"
                aria-label="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-xs text-secondary leading-relaxed">
              这些记忆只有在你授权后,才会被用于本集脚本。
            </p>
            <div className="flex flex-col gap-2 max-h-[240px] overflow-y-auto mac-scrollbar">
              {followUpState.candidates.map((candidate) => {
                const authorized = authorizedIds.has(candidate.id);
                return (
                  <div
                    key={candidate.id}
                    className="flex items-start justify-between gap-2 rounded-xl border border-outline bg-surface-container-low px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-primary truncate">
                        {candidate.sensitive ? "（敏感）" : ""}
                        {candidate.name}
                      </p>
                      <p className="text-[11px] text-secondary/70 truncate">{candidate.description}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleAuthorize(candidate.id)}
                      disabled={authorized}
                      className={
                        "shrink-0 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors cursor-pointer disabled:cursor-default " +
                        (authorized
                          ? "border-accent-amber/25 bg-accent-amber/10 text-accent-amber"
                          : "border-outline text-secondary hover:bg-primary/5 hover:text-primary")
                      }
                    >
                      {authorized ? "已授权" : "授权使用"}
                    </button>
                  </div>
                );
              })}
            </div>
            {followUpError ? (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {followUpError}
              </div>
            ) : null}
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={() => void doGenerateSnapshot()}
                disabled={generatingSnapshot}
                className="flex items-center gap-2 w-full px-3 py-2.5 rounded-xl bg-accent-amber/10 border border-accent-amber/25 text-sm font-medium text-accent-amber hover:bg-accent-amber/15 transition-colors disabled:opacity-50 cursor-pointer"
              >
                {generatingSnapshot ? (
                  <Loader2 className="w-4 h-4 animate-spin shrink-0" />
                ) : (
                  <Sparkles className="w-4 h-4 shrink-0" />
                )}
                生成脚本
              </button>
            </div>
          </div>
        ) : null}

        {/* Follow-up input */}
        {followUpState.kind !== "choice" && followUpState.kind !== "authorize" && (
          <div className="shrink-0 border-t border-outline p-3 space-y-2">
            {followUpError ? (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {followUpError}
              </div>
            ) : null}
            <p className="text-[10px] text-secondary/60 px-1">
              Add more detail or ask a follow-up
            </p>
            <div className="flex items-end gap-2 rounded-xl border border-outline bg-surface-container-low px-3 py-2 focus-within:border-accent-amber/25 transition-colors">
              <textarea
                value={followUpInput}
                onChange={(e) => setFollowUpInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleFollowUpSubmit();
                  }
                }}
                placeholder="Continue the conversation…"
                rows={2}
                disabled={followUpState.kind === "submitting"}
                className="flex-1 bg-transparent text-[13px] text-primary placeholder:text-outline/60 outline-none resize-none leading-relaxed disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => void handleFollowUpSubmit()}
                disabled={!followUpInput.trim() || followUpState.kind === "submitting"}
                className="p-2 theme-accent-gradient text-on-primary rounded-lg hover:scale-105 active:scale-95 transition-all shadow-sm disabled:opacity-30 disabled:scale-100 shrink-0 cursor-pointer"
                aria-label="Submit follow-up"
              >
                {followUpState.kind === "submitting" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
