import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Loader2, MessageSquare, Send, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useBridge } from "../../lib/BridgeContext";
import { cn } from "../../lib/utils";
import { getErrorMessage } from "../../lib/requestState";
import type { SessionProject, TranscriptTurn } from "../../types";
import { ChatPage } from "../ChatPage";

type FollowUpState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "choice"; newTurns: TranscriptTurn[] };

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
                : "bg-white/4 border border-white/5 text-secondary",
            )}
          >
            <ReactMarkdown>{turn.content}</ReactMarkdown>
          </div>
        </div>
      ))}
    </div>
  );
}

export function ConversationDrawer({
  project,
  onRefresh,
  onNewScript,
}: {
  project: SessionProject | null;
  onRefresh: () => Promise<void>;
  onNewScript: (sessionId: string, scriptId: string) => void;
}) {
  const bridge = useBridge();
  const navigate = useNavigate();
  const [followUpInput, setFollowUpInput] = useState("");
  const [followUpState, setFollowUpState] = useState<FollowUpState>({ kind: "idle" });
  const [followUpError, setFollowUpError] = useState<string | null>(null);
  const [generatingSnapshot, setGeneratingSnapshot] = useState(false);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  const sessionId = project?.session.session_id ?? "";
  const hasScript = Boolean(project?.script && !project.script.deleted_at);
  const turns = project?.transcript?.turns ?? [];

  if (!hasScript) {
    return <ChatPage onRefresh={onRefresh} />;
  }

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

  const handleKeepAsSource = () => {
    setFollowUpState({ kind: "idle" });
  };

  return (
    <div className="flex flex-col h-full w-full">
      {/* Transcript header */}
      <div className="px-4 py-3 border-b border-white/5 shrink-0">
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-secondary/70">
          <MessageSquare className="w-3.5 h-3.5" />
          <span>Interview Transcript</span>
          <span className="ml-auto text-[10px] normal-case font-medium">{turns.length} turns</span>
        </div>
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

      {/* Follow-up choice panel (shown after submitting) */}
      {followUpState.kind === "choice" ? (
        <div className="shrink-0 border-t border-white/5 bg-[rgba(14,14,16,0.95)] p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-bold uppercase tracking-wider text-accent-amber">
              Follow-up added
            </p>
            <button
              type="button"
              onClick={handleKeepAsSource}
              className="p-1 rounded text-secondary hover:text-white hover:bg-white/5 transition-colors"
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
              className="flex items-center gap-2 w-full px-3 py-2.5 rounded-xl bg-accent-amber/10 border border-accent-amber/25 text-sm font-medium text-[#f5c669] hover:bg-accent-amber/15 transition-colors disabled:opacity-50"
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
              className="flex items-center gap-2 w-full px-3 py-2.5 rounded-xl border border-white/5 bg-white/5 text-sm font-medium text-secondary hover:bg-white/8 hover:text-white transition-colors disabled:opacity-50"
            >
              <Check className="w-4 h-4 shrink-0" />
              Keep as source material
            </button>
          </div>
        </div>
      ) : null}

      {/* Follow-up input */}
      {followUpState.kind !== "choice" && (
        <div className="shrink-0 border-t border-white/5 p-3 space-y-2">
          {followUpError ? (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {followUpError}
            </div>
          ) : null}
          <p className="text-[10px] text-secondary/60 px-1">
            Add more detail or ask a follow-up
          </p>
          <div className="flex items-end gap-2 rounded-xl border border-white/5 bg-[rgba(26,26,30,0.55)] px-3 py-2 focus-within:border-accent-amber/25 transition-colors">
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
              className="flex-1 bg-transparent text-[13px] text-white placeholder:text-outline/60 outline-none resize-none leading-relaxed disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => void handleFollowUpSubmit()}
              disabled={!followUpInput.trim() || followUpState.kind === "submitting"}
              className="p-2 bg-gradient-to-b from-[#f2bf57] to-[#d79b2f] text-black rounded-lg hover:scale-105 active:scale-95 transition-all shadow-sm disabled:opacity-30 disabled:scale-100 shrink-0"
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
  );
}
