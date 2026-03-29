import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Sparkles, Mic, Send, Lightbulb, User, CheckCircle2, Circle, AlertCircle, Target, BookOpen, Layers, PanelLeft, PanelLeftClose, Plus } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useBridge } from "../lib/BridgeContext";
import { SessionProject, Readiness, PromptInput } from "../types";
import { cn } from "../lib/utils";

export function ChatPage({
  projects,
  onRefresh,
  onCreateSession,
}: {
  projects: SessionProject[];
  onRefresh: () => Promise<void>;
  onCreateSession?: () => void;
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
  const [historyOpen, setHistoryOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const sortedChats = [...projects].sort((a, b) =>
    b.session.updated_at.localeCompare(a.session.updated_at),
  );

  const fetchProject = async () => {
    if (!sessionId) return;
    try {
      setLoading(true);
      const list = await bridge.listProjects();
      const current = list.find((p) => p.session.session_id === sessionId);
      setProject(current ?? null);
    } catch (err) {
      console.error("Failed to fetch project:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!sessionId) {
      setProject(null);
      setLoading(false);
      return;
    }
    void fetchProject();
  }, [sessionId, bridge]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [project?.transcript?.turns]);

  const handleStart = async () => {
    if (!sessionId) return;
    setSubmitting(true);
    try {
      const result = await bridge.startInterview(sessionId);
      setProject(result.project);
      setReadiness(result.readiness);
      setPromptInput(result.prompt_input);
      await onRefresh();
    } catch (err) {
      console.error("Failed to start interview:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    if (!sessionId || !inputValue.trim()) return;
    setSubmitting(true);
    try {
      const result = await bridge.submitReply(sessionId, inputValue.trim(), false);
      setProject(result.project);
      setReadiness(result.readiness);
      setPromptInput(result.prompt_input);
      setInputValue("");
      await onRefresh();
    } catch (err) {
      console.error("Failed to submit reply:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleFinish = async () => {
    if (!sessionId) return;
    setSubmitting(true);
    try {
      const result = await bridge.requestFinish(sessionId);
      setProject(result.project);
      setReadiness(result.readiness);
      setPromptInput(result.prompt_input);
      await onRefresh();
    } catch (err) {
      console.error("Failed to finish interview:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const historyAside =
    historyOpen && (
      <aside className="w-[260px] shrink-0 border-r border-outline bg-surface flex flex-col min-h-0">
        <div className="p-3 border-b border-outline flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold text-secondary uppercase tracking-wider">Chats</span>
          <button
            type="button"
            onClick={() => setHistoryOpen(false)}
            className="p-1.5 rounded-md text-secondary hover:bg-surface-container-high hover:text-primary"
            aria-label="Hide history"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5 mac-scrollbar">
          {sortedChats.length === 0 ? (
            <p className="px-2 py-4 text-xs text-secondary text-center">No chats yet.</p>
          ) : (
            sortedChats.map((p) => (
              <button
                key={p.session.session_id}
                type="button"
                onClick={() => {
                  navigate(`/chat/${p.session.session_id}`);
                  setHistoryOpen(false);
                }}
                className={cn(
                  "w-full text-left rounded-md px-2 py-2 transition-colors",
                  p.session.session_id === sessionId
                    ? "bg-primary/10 text-primary"
                    : "text-secondary hover:bg-surface-container-high hover:text-primary",
                )}
              >
                <p className="text-[13px] font-medium truncate">{p.session.topic || "Untitled"}</p>
                <p className="text-[10px] text-outline truncate mt-0.5">
                  {new Date(p.session.updated_at).toLocaleDateString()}
                </p>
              </button>
            ))
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
      {onCreateSession && (
        <button
          type="button"
          onClick={onCreateSession}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[12px] font-medium text-secondary hover:bg-surface-container-high hover:text-primary transition-colors"
        >
          <Plus className="w-4 h-4" />
          New chat
        </button>
      )}
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
          <div className="flex-1 flex flex-col items-center justify-center text-secondary gap-4 px-6">
            <Mic className="w-12 h-12 text-outline-variant mb-2" />
            <div className="text-center max-w-sm">
              <h2 className="text-lg font-semibold text-primary mb-1">Chat</h2>
              <p className="text-sm">What you want to talk about today</p>
            </div>
            {onCreateSession && (
              <button
                type="button"
                onClick={onCreateSession}
                className="px-4 py-2 bg-accent-amber hover:bg-accent-amber/90 text-black rounded-lg text-sm font-medium transition-colors shadow-sm"
              >
                New chat
              </button>
            )}
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
            <p className="text-sm">Session not found.</p>
            <button
              type="button"
              onClick={() => navigate("/chat")}
              className="text-sm font-medium text-accent-amber hover:underline"
            >
              Back to chat
            </button>
          </div>
        </div>
      </div>
    );
  }

  const turns = project.transcript?.turns || [];
  const state = project.session.state;
  const isFinished = state === "ready_to_generate" || state === "script_generated" || state === "script_edited" || state === "completed";

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

            {turns.length === 0 && state === "topic_defined" && (
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

            {/* Chat History */}
            <div className="flex flex-col gap-6">
              {turns.map((turn, i) => {
                const isAgent = turn.speaker === "agent";
                
                let cleanContent = turn.content;
                let insight = null;
                const insightMatch = cleanContent.match(/<insight>(.*?)<\/insight>/);
                if (insightMatch) {
                  insight = insightMatch[1];
                  cleanContent = cleanContent.replace(/<insight>.*?<\/insight>/, '').trim();
                }

                return (
                  <div key={i} className="flex gap-4 animate-in fade-in duration-300">
                    <div className="w-8 h-8 rounded-full border border-outline flex items-center justify-center shrink-0 bg-surface-container mt-1">
                      {isAgent ? (
                        <Sparkles className="w-4 h-4 text-accent-amber" />
                      ) : (
                        <User className="w-4 h-4 text-secondary" />
                      )}
                    </div>
                    <div className="flex-1 space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-[13px] text-primary">
                          {isAgent ? "The Archivist" : "You"}
                        </span>
                      </div>
                      
                      {/* Content Block */}
                      <div className={cn(
                        "text-[14px] leading-relaxed",
                        isAgent ? "text-on-surface" : "text-secondary"
                      )}>
                        <div className="prose prose-sm prose-invert max-w-none">
                          <ReactMarkdown>{cleanContent}</ReactMarkdown>
                        </div>
                      </div>

                      {/* AI Insights block styled as a sub-note */}
                      {insight && (
                        <div className="mt-3 bg-accent-amber-container text-primary text-[13px] px-4 py-3 rounded-lg border border-accent-amber/20 flex items-start gap-3">
                          <Lightbulb className="w-4 h-4 mt-0.5 text-accent-amber shrink-0" />
                          <p className="italic opacity-90">{insight}</p>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Loading Indicator */}
              {submitting && state === "interview_in_progress" && (
                <div className="flex gap-4">
                  <div className="w-8 h-8 rounded-full border border-outline flex items-center justify-center shrink-0 bg-surface-container mt-1">
                    <Sparkles className="w-4 h-4 text-accent-amber" />
                  </div>
                  <div className="flex-1 flex items-center gap-2 pt-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-outline-variant animate-bounce" />
                    <div className="w-1.5 h-1.5 rounded-full bg-outline-variant animate-bounce [animation-delay:0.2s]" />
                    <div className="w-1.5 h-1.5 rounded-full bg-outline-variant animate-bounce [animation-delay:0.4s]" />
                  </div>
                </div>
              )}
            </div>

            {/* Finished State Action */}
            {isFinished && (
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
        {!isFinished && state === "interview_in_progress" && (
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
                  The Archivist is listening. You can dictate or type your thoughts.
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
