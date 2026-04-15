import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Circle,
  Lightbulb,
  Loader2,
  Layers,
  Mic,
  PanelLeft,
  PanelLeftClose,
  PencilLine,
  Plus,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  Target,
  Trash2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useBridge } from "../lib/BridgeContext";
import { SessionProject, Readiness, PromptInput, RequestState } from "../types";
import { cn } from "../lib/utils";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  withRequestStateFallback,
} from "../lib/requestState";

export function ChatPage({
  onRefresh,
}: {
  onRefresh: () => Promise<void>;
}) {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();
  const bridge = useBridge();

  const [project, setProject] = useState<SessionProject | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [promptInput, setPromptInput] = useState<PromptInput | null>(null);
  const [loading, setLoading] = useState(Boolean(sessionId));
  const [inputValue, setInputValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestState, setRequestState] = useState<RequestState | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyProjects, setHistoryProjects] = useState<SessionProject[]>([]);
  const [historyQuery, setHistoryQuery] = useState("");
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTopic, setEditingTopic] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyActionId, setHistoryActionId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const landingInputRef = useRef<HTMLTextAreaElement>(null);

  const [landingInput, setLandingInput] = useState("");
  const [landingSubmitting, setLandingSubmitting] = useState(false);
  const [landingError, setLandingError] = useState<string | null>(null);
  const [streamingMessage, setStreamingMessage] = useState<string | null>(null);
  const submittingRef = useRef(false);
  const replyStreamAbortRef = useRef<AbortController | null>(null);

  const toDisplayText = (value: unknown): string => {
    if (typeof value === "string") return value;
    if (value == null) return "";
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    return "";
  };

  const fetchProject = async () => {
    if (!sessionId) return;
    try {
      setLoading(true);
      setError(null);
      const current = await bridge.showSession(sessionId, { includeDeleted: true });
      setProject(current);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load the chat session."));
      setRequestState(getErrorRequestState(err));
      setProject(null);
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async () => {
    try {
      setHistoryLoading(true);
      const list = await bridge.listProjects({
        search: historyQuery.trim() || undefined,
        includeDeleted: false,
      });
      setHistoryProjects(
        list.filter((entry) => !entry.session.deleted_at),
      );
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load chat history."));
      setRequestState(getErrorRequestState(err));
    } finally {
      setHistoryLoading(false);
    }
  };

  const refreshWorkspace = async () => {
    await Promise.allSettled([fetchProject(), loadHistory(), onRefresh()]);
  };

  const handleLandingCreate = async () => {
    const message = landingInput.trim();
    if (!message || landingSubmitting) return;
    setLandingSubmitting(true);
    setLandingError(null);
    try {
      const topic = message.length > 200 ? `${message.slice(0, 197)}…` : message;
      const created = await bridge.createSession({
        topic,
        creationIntent: `Discuss ${message}`,
      });
      const sid = created.session.session_id;
      await bridge.submitReply(sid, message, false);
      await onRefresh();
      navigate(`/chat/${sid}`);
      setLandingInput("");
    } catch (err) {
      setLandingError(getErrorMessage(err, "Failed to start conversation."));
    } finally {
      setLandingSubmitting(false);
    }
  };

  useEffect(() => {
    if (!sessionId) {
      setProject(null);
      setLoading(false);
      setError(null);
      setRequestState(null);
      return;
    }
    void fetchProject();
  }, [sessionId, bridge]);

  useEffect(() => {
    void loadHistory();
  }, [bridge, historyQuery]);

  useEffect(() => {
    submittingRef.current = submitting;
  }, [submitting]);

  /** WebView / browser often suspends SSE while the app is in the background; the stream may never finish, leaving `submitting` true forever. Abort after resume so the textarea re-enables. */
  useEffect(() => {
    let resumeTimer: ReturnType<typeof setTimeout> | undefined;
    const onVisibility = () => {
      clearTimeout(resumeTimer);
      if (document.visibilityState !== "visible") return;
      resumeTimer = window.setTimeout(() => {
        if (submittingRef.current) replyStreamAbortRef.current?.abort();
      }, 2000);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearTimeout(resumeTimer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [project?.transcript?.turns]);

  const handleStart = async () => {
    if (!sessionId) return;
    setSubmitting(true);
    setError(null);
    setRequestState({
      operation: "start_interview",
      phase: "running",
      progress_percent: 0,
      message: "Starting interview...",
    });
    try {
      const result = await bridge.startInterview(sessionId);
      setProject(result.project);
      setReadiness(result.readiness);
      setPromptInput(result.prompt_input);
      setRequestState(
        withRequestStateFallback(
          result.request_state,
          buildRequestState("start_interview", "succeeded", "Interview started."),
        ),
      );
      await refreshWorkspace();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to start interview."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("start_interview", "failed", "Failed to start interview."),
        ),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    if (!sessionId || !inputValue.trim()) return;
    const content = inputValue.trim();
    setSubmitting(true);
    setError(null);
    setStreamingMessage("");
    setInputValue("");
    setRequestState({
      operation: "submit_reply",
      phase: "running",
      progress_percent: 0,
      message: "Submitting reply...",
    });

    // Optimistic UI update so the user's message appears immediately
    setProject((prev) => {
      if (!prev) return prev;
      const optimisticTurn = {
        speaker: "user",
        content: content,
        created_at: new Date().toISOString(),
      };
      
      const prevTurns = prev.transcript?.turns || [];
      const newTranscript = {
        ...(prev.transcript || { session_id: prev.session.session_id }),
        turns: [...prevTurns, optimisticTurn],
      };
      return { ...prev, transcript: newTranscript as any };
    });

    replyStreamAbortRef.current?.abort();
    const replyAbort = new AbortController();
    replyStreamAbortRef.current = replyAbort;

    try {
      const result = await bridge.submitReplyStream(
        sessionId,
        content,
        (delta) => {
          setStreamingMessage((prev) => (prev ?? "") + delta);
        },
        false,
        replyAbort.signal,
      );
      setProject(result.project);
      setReadiness(result.readiness);
      setPromptInput(result.prompt_input);
      setRequestState(
        withRequestStateFallback(
          result.request_state,
          buildRequestState("submit_reply", "succeeded", "Reply accepted."),
        ),
      );
      await refreshWorkspace();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to submit reply."));
      if (!inputValue) setInputValue(content);
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("submit_reply", "failed", "Failed to submit reply."),
        ),
      );
    } finally {
      replyStreamAbortRef.current = null;
      setStreamingMessage(null);
      setSubmitting(false);
    }
  };

  const handleFinish = async () => {
    if (!sessionId) return;
    setSubmitting(true);
    setError(null);
    setRequestState({
      operation: "request_finish",
      phase: "running",
      progress_percent: 0,
      message: "Evaluating readiness...",
    });
    try {
      const result = await bridge.requestFinish(sessionId);
      setProject(result.project);
      setReadiness(result.readiness);
      setPromptInput(result.prompt_input);
      setRequestState(
        withRequestStateFallback(
          result.request_state,
          buildRequestState("request_finish", "succeeded", "Interview is ready for script generation."),
        ),
      );
      await refreshWorkspace();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to finish interview."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("request_finish", "failed", "Failed to finish interview."),
        ),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleRenameSession = async (targetSessionId: string, nextTopic: string) => {
    if (!nextTopic.trim()) {
      setEditingSessionId(null);
      return;
    }
    setHistoryActionId(targetSessionId);
    setError(null);
    setRequestState({
      operation: "rename_session",
      phase: "running",
      progress_percent: 0,
      message: "Renaming chat...",
    });
    try {
      const updated = await bridge.renameSession(targetSessionId, nextTopic.trim());
      if (updated.session.session_id === sessionId) {
        setProject(updated);
      }
      await refreshWorkspace();
      setRequestState(buildRequestState("rename_session", "succeeded", "Chat renamed."));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to rename chat."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("rename_session", "failed", "Failed to rename chat."),
        ),
      );
    } finally {
      setHistoryActionId(null);
      setEditingSessionId(null);
    }
  };

  const handleDeleteSession = async (target: SessionProject) => {
    if (!window.confirm(`Delete chat "${target.session.topic}"?`)) return;
    setHistoryActionId(target.session.session_id);
    setError(null);
    setRequestState({
      operation: "delete_session",
      phase: "running",
      progress_percent: 0,
      message: "Deleting chat...",
    });
    try {
      const updated = await bridge.deleteSession(target.session.session_id);
      if (updated.session.session_id === sessionId) {
        navigate("/chat");
      } else {
        await refreshWorkspace();
      }
      setRequestState(buildRequestState("delete_session", "succeeded", "Chat deleted."));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete chat."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("delete_session", "failed", "Failed to delete chat."),
        ),
      );
    } finally {
      setHistoryActionId(null);
    }
  };

  const historyAside =
    historyOpen && (
      <aside className="w-[300px] shrink-0 border-r border-outline bg-surface flex flex-col min-h-0">
        <div className="p-3 border-b border-outline space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
              Chats
            </span>
            <button
              type="button"
              onClick={() => setHistoryOpen(false)}
              className="p-1.5 rounded-md text-secondary hover:bg-surface-container-high hover:text-primary"
              aria-label="Hide history"
            >
              <PanelLeftClose className="w-4 h-4" />
            </button>
          </div>
          <label className="flex items-center gap-2 rounded-md border border-outline bg-background px-2.5 py-2">
            <Search className="w-4 h-4 text-secondary shrink-0" />
            <input
              value={historyQuery}
              onChange={(event) => setHistoryQuery(event.target.value)}
              placeholder="Search chats"
              className="w-full bg-transparent text-[13px] outline-none placeholder:text-outline"
            />
          </label>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1 mac-scrollbar">
          {historyLoading ? (
            <div className="flex items-center gap-2 px-2 py-4 text-xs text-secondary">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading chats...
            </div>
          ) : historyProjects.length === 0 ? (
            <p className="px-2 py-4 text-xs text-secondary text-center">
              No chats yet.
            </p>
          ) : (
            historyProjects.map((p) => {
              const isCurrent = p.session.session_id === sessionId;
              const isEditing = editingSessionId === p.session.session_id;

              return (
                <div
                  key={p.session.session_id}
                  className={cn(
                    "rounded-md border px-2 py-2 transition-colors",
                    isCurrent ? "border-primary/20 bg-primary/5" : "border-transparent hover:bg-surface-container-high",
                  )}
                >
                  {isEditing ? (
                    <div className="w-full flex items-center gap-2 mb-2">
                      <input
                        autoFocus
                        value={editingTopic}
                        onChange={(e) => setEditingTopic(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void handleRenameSession(p.session.session_id, editingTopic);
                          } else if (e.key === "Escape") {
                            setEditingSessionId(null);
                          }
                        }}
                        onBlur={() => setEditingSessionId(null)}
                        className="flex-1 min-w-0 bg-background text-[13px] text-primary border border-primary/30 rounded px-2 py-1 outline-none focus:border-primary"
                      />
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        navigate(`/chat/${p.session.session_id}`);
                        setHistoryOpen(false);
                      }}
                      className="w-full text-left"
                    >
                      <p className="text-[13px] font-medium truncate text-primary">{p.session.topic || "Untitled"}</p>
                      <p className="text-[10px] text-outline truncate mt-0.5">
                        {new Date(p.session.updated_at).toLocaleDateString()}
                      </p>
                    </button>
                  )}
                  <div className="mt-2 flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingSessionId(p.session.session_id);
                        setEditingTopic(p.session.topic);
                      }}
                      disabled={historyActionId === p.session.session_id}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-secondary hover:bg-surface-container-high hover:text-primary disabled:opacity-50"
                    >
                      <PencilLine className="w-3.5 h-3.5" />
                      Rename
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDeleteSession(p)}
                      disabled={historyActionId === p.session.session_id}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-secondary hover:bg-surface-container-high hover:text-primary disabled:opacity-50 text-red-500/80 hover:text-red-500"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Delete
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>
    );

  const chatToolbar = (
    <div className="h-11 shrink-0 border-b border-outline flex items-center gap-2 px-3 bg-background/90 backdrop-blur-md">
      <button
        type="button"
        onClick={() => setHistoryOpen((v) => !v)}
        className="p-2 rounded-md text-secondary hover:bg-surface-container-high hover:text-primary transition-colors"
        aria-label={historyOpen ? "Hide chat history" : "Show chat history"}
        title="Chat history"
      >
        {historyOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
      </button>
      <button
        type="button"
        onClick={() => navigate("/chat")}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[12px] font-medium text-secondary hover:bg-surface-container-high hover:text-primary transition-colors"
      >
        <Plus className="w-4 h-4" />
        New chat
      </button>
    </div>
  );

  if (loading && sessionId) {
    return (
      <div className="flex h-full w-full overflow-hidden">
        {historyAside}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {chatToolbar}
          <div className="flex-1 flex items-center justify-center text-secondary text-sm">Loading workspace…</div>
        </div>
      </div>
    );
  }

  if (!sessionId) {
    return (
      <div className="flex h-full w-full overflow-hidden">
        {historyAside}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {chatToolbar}
          <div className="flex-1 flex flex-col items-center justify-center px-6 py-10">
            <div className="w-full max-w-2xl flex flex-col items-center gap-8">
              <h2 className="text-2xl sm:text-3xl font-medium text-primary text-center tracking-tight">
                我们先从哪里开始呢？
              </h2>
              <div className="w-full flex flex-col gap-2">
                {landingError ? (
                  <p className="text-sm text-red-400 text-center">{landingError}</p>
                ) : null}
                <div
                  className={cn(
                    "flex items-end gap-2 rounded-full border border-outline bg-surface-container px-3 py-2 pl-4 shadow-sm",
                    "focus-within:border-accent-amber/30 transition-colors",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => landingInputRef.current?.focus()}
                    className="p-2 text-on-surface hover:bg-surface-container-high rounded-full transition-colors shrink-0 mb-0.5"
                    aria-label="Focus input"
                  >
                    <Plus className="w-5 h-5" />
                  </button>
                  <textarea
                    ref={landingInputRef}
                    value={landingInput}
                    onChange={(e) => setLandingInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void handleLandingCreate();
                      }
                    }}
                    disabled={landingSubmitting}
                    placeholder="今天你想聊什么?"
                    rows={1}
                    className="flex-1 min-h-[44px] max-h-[200px] resize-none bg-transparent border-none focus:ring-0 text-[15px] text-on-surface placeholder:text-outline py-2.5 outline-none leading-relaxed"
                  />
                  <button
                    type="button"
                    className="p-2 text-secondary hover:bg-surface-container-high rounded-full transition-colors shrink-0 mb-0.5"
                    aria-label="Voice input"
                  >
                    <Mic className="w-5 h-5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleLandingCreate()}
                    disabled={!landingInput.trim() || landingSubmitting}
                    className="p-2.5 bg-primary text-background rounded-full hover:opacity-90 transition-opacity disabled:opacity-30 disabled:cursor-not-allowed shrink-0 mb-0.5"
                    aria-label="Start chat"
                  >
                    {landingSubmitting ? (
                      <Loader2 className="w-5 h-5 animate-spin" />
                    ) : (
                      <Send className="w-5 h-5" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex h-full w-full overflow-hidden">
        {historyAside}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {chatToolbar}
          <div className="flex-1 flex flex-col items-center justify-center text-secondary gap-4 px-6">
            {error ? (
              <>
                <p className="text-sm text-red-400">{error}</p>
                <button
                  type="button"
                  onClick={() => void fetchProject()}
                  className="text-sm font-medium text-accent-amber hover:underline"
                >
                  Retry
                </button>
              </>
            ) : (
              <>
                <p className="text-sm">Session not found.</p>
                <button
                  type="button"
                  onClick={() => navigate("/chat")}
                  className="text-sm font-medium text-accent-amber hover:underline"
                >
                  Back to chat
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  const turns = Array.isArray(project.transcript?.turns) ? project.transcript.turns : [];
  const state = project.session.state;
  const isFinished = state === "ready_to_generate" || state === "script_generated" || state === "script_edited" || state === "completed";
  const isDeletedSession = Boolean(project.session.deleted_at);
  return (
    <div className="flex flex-row h-full w-full relative overflow-hidden">
      {historyAside}
      {/* 1. Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 relative min-h-0">
        {chatToolbar}
        <div ref={scrollRef} className="flex-1 overflow-y-auto w-full px-6 lg:px-12 scroll-smooth chat-container">
          <div className="max-w-4xl flex flex-col py-8 gap-6 pb-40 mx-auto">
            
            {/* Header Area (Left-aligned, document style) */}
            <div className="pb-6 border-b border-outline">
              <h1 className="text-2xl font-headline font-bold text-primary mb-2">Chat</h1>
              <p className="text-secondary text-sm">
                Shape your episode through conversation; the script is summarized from this chat.
              </p>
            </div>

            {turns.length === 0 && state === "topic_defined" && !isDeletedSession && (
              <div className="py-8">
                <button
                  onClick={handleStart}
                  disabled={submitting}
                  className="px-5 py-2.5 bg-accent-amber hover:bg-accent-amber/90 text-black rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50"
                >
                  Start Interview Process
                </button>
              </div>
            )}

            {/* Chat History: user bubbles right, assistant plain left */}
            <div className="flex flex-col gap-5">
              {error && (
                <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {error}
                </div>
              )}
              {turns.map((turn, i) => {
                const isAgent = turn.speaker === "agent";

                let cleanContent = toDisplayText(turn.content);
                let insight = null;
                const insightMatch = cleanContent.match(/<insight>(.*?)<\/insight>/);
                if (insightMatch) {
                  insight = insightMatch[1];
                  cleanContent = cleanContent.replace(/<insight>.*?<\/insight>/, "").trim();
                }

                if (!isAgent) {
                  return (
                    <div
                      key={i}
                      className="flex w-full justify-end animate-in fade-in duration-300"
                    >
                      <div
                        className={cn(
                          "max-w-[min(85%,28rem)] rounded-3xl rounded-br-md",
                          "border border-outline/60 bg-surface-container-high px-4 py-2.5 shadow-sm",
                        )}
                      >
                        <div className="text-[14px] leading-relaxed text-on-surface prose prose-sm prose-invert max-w-none [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
                          <ReactMarkdown>{cleanContent}</ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  );
                }

                return (
                  <div
                    key={i}
                    className="flex w-full justify-start animate-in fade-in duration-300"
                  >
                    <div className="max-w-[min(92%,40rem)] space-y-2">
                      <div className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-accent-amber shrink-0" />
                        <span className="font-medium text-[13px] text-primary">The Archivist</span>
                      </div>
                      <div className="text-[14px] leading-relaxed text-on-surface pl-0.5">
                        <div className="prose prose-sm prose-invert max-w-none [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
                          <ReactMarkdown>{cleanContent}</ReactMarkdown>
                        </div>
                      </div>
                      {insight ? (
                        <div className="mt-2 bg-accent-amber-container text-primary text-[13px] px-4 py-3 rounded-lg border border-accent-amber/20 flex items-start gap-3">
                          <Lightbulb className="w-4 h-4 mt-0.5 text-accent-amber shrink-0" />
                          <p className="italic opacity-90">{insight}</p>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}

              {/* Streaming Content */}
              {streamingMessage !== null && (
                <div className="flex w-full justify-start animate-in fade-in duration-300">
                  <div className="max-w-[min(92%,40rem)] space-y-2">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-accent-amber shrink-0" />
                      <span className="font-medium text-[13px] text-primary">The Archivist</span>
                    </div>
                    <div className="text-[14px] leading-relaxed text-on-surface pl-0.5">
                      <div className="prose prose-sm prose-invert max-w-none [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
                        <ReactMarkdown>{streamingMessage || "..."}</ReactMarkdown>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Loading Indicator — left-aligned like assistant */}
              {submitting && state === "interview_in_progress" && streamingMessage === null && (
                <div className="flex w-full justify-start gap-3 pt-1">
                  <div className="flex items-center gap-2 text-secondary">
                    <Sparkles className="w-4 h-4 text-accent-amber shrink-0" />
                    <div className="flex items-center gap-1.5 h-6">
                      <div className="w-1.5 h-1.5 rounded-full bg-outline-variant animate-bounce" />
                      <div className="w-1.5 h-1.5 rounded-full bg-outline-variant animate-bounce [animation-delay:0.2s]" />
                      <div className="w-1.5 h-1.5 rounded-full bg-outline-variant animate-bounce [animation-delay:0.4s]" />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Finished State Action */}
            {isFinished && !isDeletedSession && (
              <div className="py-8 border-t border-outline mt-4">
                <p className="text-sm text-secondary mb-4">Interview complete. Ready to move to the next phase.</p>
                <button
                  onClick={() => navigate(`/script/${sessionId}`)}
                  className="px-5 py-2.5 bg-surface-container-high hover:bg-surface-container-highest border border-outline rounded-lg text-sm font-medium transition-colors"
                >
                  Review Generated Script
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Persistent Bottom Input Dock */}
        {!isDeletedSession && !isFinished && state === "interview_in_progress" && (
          <div className="absolute bottom-0 left-0 w-full bg-background/60 backdrop-blur-2xl border-t border-outline p-4 lg:px-12">
            <div className="max-w-4xl mx-auto flex flex-col gap-2">
              <div className="bg-surface-container border border-outline rounded-lg p-2 flex items-end gap-2 focus-within:border-accent-amber/30 transition-colors shadow-sm">
                <textarea 
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit();
                    }
                  }}
                  className="flex-1 bg-transparent border-none focus:ring-0 resize-none text-[14px] text-on-surface placeholder:text-outline py-1.5 px-2 max-h-[200px] min-h-[44px] outline-none leading-relaxed" 
                  placeholder="Type your response... (Shift+Enter for newline)" 
                  rows={1}
                  disabled={submitting}
                />
                <div className="flex items-center gap-1 shrink-0 p-1">
                  <button 
                    onClick={handleFinish}
                    disabled={submitting}
                    className="px-3 py-1.5 text-secondary hover:bg-surface-container-high hover:text-primary transition-colors rounded text-[12px] font-medium"
                  >
                    Finish
                  </button>
                  <button className="p-2 text-secondary hover:bg-surface-container-high transition-colors rounded">
                    <Mic className="w-4 h-4" />
                  </button>
                  <button 
                    onClick={handleSubmit}
                    disabled={!inputValue.trim() || submitting}
                    className="p-2 bg-primary text-background hover:opacity-90 rounded transition-opacity disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div className="flex justify-between items-center px-1">
                <p className="text-[11px] text-outline">
                  {requestState?.phase === "running"
                    ? requestState.message
                    : "The Archivist is listening. You can dictate or type your thoughts."}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 2. AI Guidance Side Panel */}
      <aside className="w-[300px] border-l border-outline bg-surface/50 flex flex-col shrink-0 overflow-y-auto hidden xl:flex">
        <div className="p-5 space-y-8">
          
          {/* Interview Stage */}
          <section>
            <div className="flex items-center gap-2 mb-4 text-secondary">
               <Layers className="w-4 h-4" />
               <span className="text-[11px] font-bold uppercase tracking-wider">Interview Stage</span>
            </div>
            <div className="space-y-3">
              {[
                { label: 'Topic Defined', state: 'topic_defined' },
                { label: 'Deep Dive', state: 'interview_in_progress' },
                { label: 'Evaluation', state: 'readiness_evaluation' },
                { label: 'Ready', state: 'ready_to_generate' }
              ].map((s, idx) => (
                <div key={idx} className="flex items-center gap-3">
                  <div className={cn(
                    "w-2 h-2 rounded-full",
                    state === s.state ? "bg-accent-amber animate-pulse shadow-[0_0_8px_rgba(212,163,75,0.5)]" : "bg-outline"
                  )} />
                  <span className={cn(
                    "text-[13px] transition-colors",
                    state === s.state ? "text-primary font-semibold" : "text-secondary font-medium"
                  )}>
                    {s.label}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* Exposed Topics */}
          <section>
            <div className="flex items-center gap-2 mb-4 text-secondary">
               <BookOpen className="w-4 h-4" />
               <span className="text-[11px] font-bold uppercase tracking-wider">Exposed Topics</span>
            </div>
            <div className="space-y-2">
              <div className="bg-surface-container rounded-lg p-3 border border-outline">
                <p className="text-[13px] text-primary leading-relaxed">
                  {project.session.topic}
                </p>
              </div>
              {/* Dummy topics if none extracted yet */}
              {turns.length > 2 ? (
                <div className="flex flex-wrap gap-2">
                  <span className="px-2 py-1 rounded bg-accent-amber/10 border border-accent-amber/20 text-[10px] text-accent-amber font-bold uppercase">Context Established</span>
                  <span className="px-2 py-1 rounded bg-primary/10 border border-outline text-[10px] text-primary font-bold uppercase">Core Perspective</span>
                </div>
              ) : (
                <p className="text-[11px] text-outline italic">Analyzing conversation...</p>
              )}
            </div>
          </section>

          {/* Missing Information (Readiness) */}
          <section>
            <div className="flex items-center gap-2 mb-4 text-secondary">
               <AlertCircle className="w-4 h-4" />
               <span className="text-[11px] font-bold uppercase tracking-wider">Gap Analysis</span>
            </div>
            <div className="space-y-4">
               {[
                 { key: 'topic_context', label: 'Context & Background' },
                 { key: 'core_viewpoint', label: 'Core Narrative' },
                 { key: 'example_or_detail', label: 'Anecdotes & Details' },
                 { key: 'conclusion', label: 'Summary & Wrap' }
               ].map((item) => (
                 <div key={item.key} className="flex items-center justify-between group">
                    <span className={cn(
                      "text-[12px] transition-colors",
                      readiness?.[item.key as keyof Readiness] ? "text-secondary" : "text-primary font-medium"
                    )}>
                      {item.label}
                    </span>
                    {readiness?.[item.key as keyof Readiness] ? (
                      <CheckCircle2 className="w-4 h-4 text-accent-amber" />
                    ) : (
                      <Circle className="w-4 h-4 text-outline group-hover:text-secondary transition-colors" />
                    )}
                 </div>
               ))}
            </div>
          </section>

          {/* AI Intent */}
          <section>
            <div className="flex items-center gap-2 mb-4 text-secondary">
               <Target className="w-4 h-4" />
               <span className="text-[11px] font-bold uppercase tracking-wider">AI Strategy</span>
            </div>
            <div className="bg-primary/5 rounded-xl p-4 border border-outline/50 relative overflow-hidden group">
               <div className="absolute right-0 top-0 p-2 opacity-10 group-hover:scale-125 transition-transform">
                  <Sparkles className="w-8 h-8 text-primary" />
               </div>
               <p className="text-[12px] text-on-surface leading-relaxed relative z-10">
                  {promptInput?.suggested_focus || promptInput?.strategy_instruction || "Initializing strategy based on your topic definition..."}
               </p>
            </div>
          </section>

        </div>
      </aside>

    </div>
  );
}
