import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { ArrowLeft, FileText, Loader2, Plus, Send, Square } from "lucide-react";
import { SafeMarkdown } from "../components/SafeMarkdown";
import { ComposerModelPicker } from "../components/ComposerModelPicker";
import {
  PendingAttachmentTray,
  TurnAttachments,
  filesFromDataTransfer,
} from "../components/ChatAttachments";
import { SessionTopicEditor } from "../components/SessionTopicEditor";
import { useBridge } from "../lib/BridgeContext";
import {
  ChatAttachment,
  SessionProject,
  Readiness,
  RequestState,
  TranscriptRecord,
  TranscriptTurn,
} from "../types";
import { cn } from "../lib/utils";
import { createSmoothTextBuffer } from "../lib/smoothText";
import {
  ATTACHMENT_ACCEPT,
  pendingAsChatAttachment,
  rememberAttachmentPreview,
  toPendingAttachments,
  type PendingAttachment,
} from "../lib/chatAttachments";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  isAbortError,
  withRequestStateFallback,
} from "../lib/requestState";

const COVERAGE_ITEMS: { key: "topic_context" | "core_viewpoint" | "example_or_detail" | "conclusion"; label: string }[] = [
  { key: "topic_context", label: "Background" },
  { key: "core_viewpoint", label: "Main point" },
  { key: "example_or_detail", label: "Examples and details" },
  { key: "conclusion", label: "Takeaway" },
];

export function ChatPage({
  onRefresh,
}: {
  onRefresh: () => Promise<void>;
}) {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const bridge = useBridge();

  const [project, setProject] = useState<SessionProject | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [loading, setLoading] = useState(Boolean(sessionId));
  const [inputValue, setInputValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, setRequestState] = useState<RequestState | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const landingInputRef = useRef<HTMLDivElement>(null);
  const composerInputRef = useRef<HTMLDivElement>(null);
  const landingFileInputRef = useRef<HTMLInputElement>(null);
  const composerFileInputRef = useRef<HTMLInputElement>(null);
  const [landingAttachments, setLandingAttachments] = useState<PendingAttachment[]>([]);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);

  const [landingInput, setLandingInput] = useState("");
  const [landingSubmitting, setLandingSubmitting] = useState(false);
  const [landingError, setLandingError] = useState<string | null>(null);
  const [showLlmSetupAction, setShowLlmSetupAction] = useState(false);
  const [streamingMessage, setStreamingMessage] = useState<string | null>(null);
  const submittingRef = useRef(false);
  // True only while submitReplyStream is in flight — drives Send↔Stop (not generate_script).
  const [replyStreaming, setReplyStreaming] = useState(false);
  const [generatingScript, setGeneratingScript] = useState(false);
  const replyStreamAbortRef = useRef<AbortController | null>(null);
  const replyRunRef = useRef(0);
  const consumedInitialReplyRef = useRef<string | null>(null);
  const optimisticTranscriptRef = useRef<TranscriptRecord | null>(null);

  const routeState = location.state as { initialReply?: string; initialAttachments?: ChatAttachment[] } | null;
  const initialReply = typeof routeState?.initialReply === "string" ? routeState.initialReply : "";
  const initialAttachments = Array.isArray(routeState?.initialAttachments) ? routeState.initialAttachments : [];

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

  const ensureLlmReady = async (): Promise<boolean> => {
    try {
      const preflight = await bridge.checkLLMConfig();
      if (preflight.ready) {
        setShowLlmSetupAction(false);
        return true;
      }
      setShowLlmSetupAction(true);
      setLandingError(preflight.message);
      setError(preflight.message);
      setRequestState(buildRequestState("check_llm_config", "failed", preflight.message));
      return false;
    } catch (err) {
      const message = getErrorMessage(err, "Failed to check language model settings.");
      setShowLlmSetupAction(true);
      setLandingError(message);
      setError(message);
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("check_llm_config", "failed", message),
        ),
      );
      return false;
    }
  };

  const refreshWorkspace = async () => {
    await Promise.allSettled([fetchProject(), onRefresh()]);
  };

  /** Align transcript after Stop without flipping the page into the loading shell. */
  const syncSessionQuietly = async (replyRun: number) => {
    if (!sessionId) return;
    try {
      const current = await bridge.showSession(sessionId, { includeDeleted: true });
      if (replyRun === replyRunRef.current) setProject(current);
    } catch {
      /* keep optimistic transcript if quiet sync fails */
    }
  };

  const uploadPendingAttachments = async (
    targetSessionId: string,
    items: PendingAttachment[],
  ): Promise<ChatAttachment[]> => {
    const uploaded: ChatAttachment[] = [];
    for (const item of items) {
      const attachment = await bridge.uploadAttachment(targetSessionId, item.file, item.name);
      // Reuse the local thumbnail so the saved turn does not refetch the image.
      if (item.previewUrl) rememberAttachmentPreview(attachment.attachment_id, item.previewUrl);
      uploaded.push(attachment);
    }
    return uploaded;
  };

  const addAttachments = (target: "landing" | "composer", files: File[]) => {
    if (files.length === 0) return;
    const setItems = target === "landing" ? setLandingAttachments : setPendingAttachments;
    const existing = target === "landing" ? landingAttachments : pendingAttachments;
    const { accepted, error: rejection } = toPendingAttachments(files, existing.length);
    setAttachmentError(rejection);
    if (accepted.length) setItems((prev) => [...prev, ...accepted]);
  };

  const removeAttachment = (target: "landing" | "composer", localId: string) => {
    const setItems = target === "landing" ? setLandingAttachments : setPendingAttachments;
    setItems((prev) => {
      const removed = prev.find((item) => item.localId === localId);
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
      return prev.filter((item) => item.localId !== localId);
    });
    setAttachmentError(null);
  };

  const attachmentDropProps = (target: "landing" | "composer") => ({
    onDragOver: (e: React.DragEvent<HTMLDivElement>) => {
      if (e.dataTransfer.types.includes("Files")) e.preventDefault();
    },
    onDrop: (e: React.DragEvent<HTMLDivElement>) => {
      const files = filesFromDataTransfer(e.dataTransfer);
      if (files.length === 0) return;
      e.preventDefault();
      addAttachments(target, files);
    },
  });

  const handleLandingCreate = async () => {
    const message = landingInput.trim();
    if ((!message && landingAttachments.length === 0) || landingSubmitting) return;
    setLandingSubmitting(true);
    setLandingError(null);
    setShowLlmSetupAction(false);
    try {
      const topicSource = message || landingAttachments.map((item) => item.name).join(", ");
      const topic = topicSource.length > 200 ? `${topicSource.slice(0, 197)}…` : topicSource;
      const created = await bridge.createSession({
        topic,
        creationIntent: `Discuss ${topicSource}`,
      });
      const sid = created.session.session_id;
      const uploaded = await uploadPendingAttachments(sid, landingAttachments);
      await onRefresh();
      navigate(`/studio/${sid}?panel=conversation`, {
        state: { initialReply: message, initialAttachments: uploaded },
      });
      setLandingInput("");
      setLandingAttachments([]);
      setAttachmentError(null);
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

  const handlePaste = (target: "landing" | "composer") => (e: React.ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault();
    const files = filesFromDataTransfer(e.clipboardData);
    if (files.length > 0) {
      addAttachments(target, files);
      return;
    }
    const text = e.clipboardData.getData("text/plain");
    document.execCommand("insertText", false, text);
  };

  // Caret-safe synchronization for landing input
  useEffect(() => {
    const el = landingInputRef.current;
    if (el && el.innerText !== landingInput) {
      el.innerText = landingInput;
    }
  }, [landingInput]);

  // Caret-safe synchronization for active Chat Composer
  useEffect(() => {
    const el = composerInputRef.current;
    if (el && el.innerText !== inputValue) {
      el.innerText = inputValue;
    }
  }, [inputValue]);

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
      const ready = await ensureLlmReady();
      if (!ready) return;
      const result = await bridge.startInterview(sessionId);
      setProject(result.project);
      setReadiness(result.readiness);
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

  const submitReplyContent = async (
    content: string,
    pending: PendingAttachment[] = [],
    preUploaded: ChatAttachment[] = [],
  ) => {
    if (!sessionId || submittingRef.current) return;
    if (!content.trim() && pending.length === 0 && preUploaded.length === 0) return;
    const replyRun = ++replyRunRef.current;
    content = content.trim();

    submittingRef.current = true;
    setSubmitting(true);
    setError(null);

    // Render the sent turn and assistant placeholder before the preflight request.
    // The first visible response to Send should not wait on a network round trip.
    const previousTranscript = project
      ? {
          session_id: project.transcript?.session_id ?? project.session.session_id,
          turns: [...(project.transcript?.turns ?? [])],
        }
      : null;
    const previousSessionState = project?.session.state;
    const optimisticTurn: TranscriptTurn = {
      speaker: "user",
      content,
      created_at: new Date().toISOString(),
      attachments: [...preUploaded, ...pending.map(pendingAsChatAttachment)],
    };

    setStreamingMessage("");
    setInputValue("");
    setPendingAttachments([]);
    setAttachmentError(null);
    optimisticTranscriptRef.current = previousTranscript;
    setProject((prev) => {
      if (!prev) return prev;
      const newTranscript: TranscriptRecord = {
        session_id: prev.transcript?.session_id ?? prev.session.session_id,
        turns: [...(prev.transcript?.turns ?? []), optimisticTurn],
      };
      // Leave topic_defined immediately so the composer dock stays mounted
      // while the first streamed reply is still in flight.
      const nextSession =
        prev.session.state === "topic_defined"
          ? { ...prev.session, state: "interview_in_progress" as const }
          : prev.session;
      return { ...prev, session: nextSession, transcript: newTranscript };
    });

    const replyText = createSmoothTextBuffer(setStreamingMessage);
    try {
      const ready = await ensureLlmReady();
      if (!ready) {
        setProject((prev) => (
          prev && previousTranscript
            ? {
                ...prev,
                session: previousSessionState
                  ? { ...prev.session, state: previousSessionState }
                  : prev.session,
                transcript: previousTranscript,
              }
            : prev
        ));
        setInputValue(content);
        setPendingAttachments(pending);
        return;
      }

      const attachments = [...preUploaded, ...(await uploadPendingAttachments(sessionId, pending))];

      replyStreamAbortRef.current?.abort();
      const replyAbort = new AbortController();
      replyStreamAbortRef.current = replyAbort;
      // Stop must also discard any pending animation frames.
      replyAbort.signal.addEventListener("abort", () => replyText.cancel());
      setReplyStreaming(true);

      const result = await bridge.submitReplyStream(
        sessionId,
        content,
        (delta) => replyText.push(delta),
        {
          signal: replyAbort.signal,
          attachmentIds: attachments.map((item) => item.attachment_id),
        },
      );
      // A completed reply must not wait for animation frames, which WebViews can suspend.
      replyText.finish();
      setProject(result.project);
      setReadiness(result.readiness);
      setRequestState(
        withRequestStateFallback(
          result.request_state,
          buildRequestState("submit_reply", "succeeded", "Reply accepted."),
        ),
      );
      optimisticTranscriptRef.current = null;
      // The SSE final payload is already the source of truth for this turn.
      // Refresh the episode list in the background so a slow ancillary request
      // cannot keep the composer stuck on its Stop state.
      void onRefresh();
    } catch (err) {
      // Stop generation: keep user turn, drop partial assistant, sync from server.
      if (isAbortError(err)) {
        optimisticTranscriptRef.current = null;
        setRequestState(buildRequestState("submit_reply", "cancelled", "Generation stopped."));
        void syncSessionQuietly(replyRun);
        return;
      }

      setError(getErrorMessage(err, "Failed to submit reply."));
      const rollbackTranscript = optimisticTranscriptRef.current;
      if (rollbackTranscript) {
        setProject((prev) => (
          prev
            ? {
                ...prev,
                session: previousSessionState
                  ? { ...prev.session, state: previousSessionState }
                  : prev.session,
                transcript: rollbackTranscript,
              }
            : prev
        ));
      }
      // Prefer an in-progress draft over restoring the already-sent text.
      setInputValue((prev) => (prev.trim() ? prev : content));
      setPendingAttachments((prev) => (prev.length ? prev : pending));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("submit_reply", "failed", "Failed to submit reply."),
        ),
      );
    } finally {
      replyText.cancel();
      replyStreamAbortRef.current = null;
      optimisticTranscriptRef.current = null;
      setStreamingMessage(null);
      submittingRef.current = false;
      setReplyStreaming(false);
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    await submitReplyContent(inputValue, pendingAttachments);
  };

  const handleStopReply = () => {
    replyStreamAbortRef.current?.abort();
  };

  useEffect(() => {
    if (!sessionId || loading || submitting) return;
    if (!initialReply.trim() && initialAttachments.length === 0) return;
    const key = `${sessionId}:${initialReply}:${initialAttachments.map((item) => item.attachment_id).join(",")}`;
    if (consumedInitialReplyRef.current === key) return;
    consumedInitialReplyRef.current = key;
    navigate(`/studio/${sessionId}?panel=conversation`, { replace: true, state: null });
    void submitReplyContent(initialReply, [], initialAttachments);
  }, [sessionId, loading, submitting, initialReply, initialAttachments]);

  const handleGenerateScript = async () => {
    if (!sessionId || submitting) return;

    setSubmitting(true);
    setGeneratingScript(true);
    setError(null);
    setRequestState({
      operation: "generate_script",
      phase: "running",
      progress_percent: 0,
      message: "Preparing script generation...",
    });
    try {
      const ready = await ensureLlmReady();
      if (!ready) return;
      await bridge.requestFinish(sessionId);
      setRequestState({
        operation: "generate_script",
        phase: "running",
        progress_percent: 45,
        message: "Generating script from chat...",
      });
      const result = await bridge.generateScript(sessionId);
      setProject(result.project);
      const newScriptId = result.script_id ?? result.project.script?.script_id;
      setRequestState(
        withRequestStateFallback(
          result.request_state,
          buildRequestState("generate_script", "succeeded", "Script generated from this chat."),
        ),
      );
      await refreshWorkspace();
      if (newScriptId) {
        navigate(`/studio/${sessionId}/${newScriptId}`);
      } else {
        navigate(`/studio/${sessionId}`);
      }
    } catch (err) {
      setError(getErrorMessage(err, "Failed to generate script from chat."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("generate_script", "failed", "Failed to generate script."),
        ),
      );
    } finally {
      setSubmitting(false);
      setGeneratingScript(false);
    }
  };

  if (loading && sessionId) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        <Loader2 className="w-4 h-4 animate-spin mr-2" />
        Loading conversation…
      </div>
    );
  }

  if (!sessionId) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center px-6 py-10">
        <div className="w-full max-w-2xl flex flex-col items-center gap-8">
          <h1 className="text-3xl font-headline font-semibold text-center text-primary select-none">
            What’s this episode about?
          </h1>

          <div className="w-full flex flex-col gap-3">
            {landingError ? (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-center text-sm text-red-700 dark:text-red-300">
                <p>{landingError}</p>
                {showLlmSetupAction ? (
                  <button
                    type="button"
                    onClick={() => navigate("/settings")}
                    className="mt-3 rounded-lg border border-outline px-3 py-1.5 text-[12px] font-medium text-primary hover:bg-primary/5"
                  >
                    Open Settings
                  </button>
                ) : null}
              </div>
            ) : null}
            <div
              {...attachmentDropProps("landing")}
              className="flex flex-col gap-2 rounded-2xl border border-outline bg-surface-container-low px-3.5 pt-3 pb-2 transition-colors focus-within:border-primary/20"
            >
              <PendingAttachmentTray
                items={landingAttachments}
                onRemove={(localId) => removeAttachment("landing", localId)}
                disabled={landingSubmitting}
              />
              <div
                ref={landingInputRef}
                contentEditable={!landingSubmitting}
                suppressContentEditableWarning
                onInput={(e) => setLandingInput(e.currentTarget.innerText)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleLandingCreate();
                  }
                }}
                onPaste={handlePaste("landing")}
                data-placeholder="An idea, a story, or a question you want to talk through"
                aria-label="Episode idea"
                className="w-full min-h-[52px] max-h-[200px] overflow-y-auto bg-transparent border-none focus:ring-0 text-[15px] text-primary py-1 px-1 outline-none leading-normal composer-editable select-text text-left"
              />
              {attachmentError ? (
                <p className="px-1 text-[12px] text-red-600 dark:text-red-400">{attachmentError}</p>
              ) : null}
              <div className="flex items-center justify-between gap-2">
                <input
                  ref={landingFileInputRef}
                  type="file"
                  multiple
                  accept={ATTACHMENT_ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    addAttachments("landing", Array.from(e.target.files ?? []));
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  onClick={() => landingFileInputRef.current?.click()}
                  disabled={landingSubmitting}
                  className="p-1.5 text-secondary hover:text-primary hover:bg-primary/5 rounded-lg transition-colors shrink-0 disabled:opacity-30"
                  aria-label="Attach images or files"
                  title="Attach images or files"
                >
                  <Plus className="w-4 h-4" />
                </button>
                <div className="flex items-center gap-1.5 shrink-0">
                  <ComposerModelPicker
                    disabled={landingSubmitting}
                    onConfigChange={() => void ensureLlmReady()}
                  />
                  <button
                    type="button"
                    onClick={() => void handleLandingCreate()}
                    disabled={(!landingInput.trim() && landingAttachments.length === 0) || landingSubmitting}
                    className="p-2 bg-primary text-background rounded-full transition-opacity disabled:opacity-20 disabled:cursor-not-allowed shrink-0"
                    aria-label="Start chat"
                  >
                    {landingSubmitting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Send className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => navigate("/episodes/new/markdown")}
              className="mx-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] text-secondary transition-colors hover:bg-primary/5 hover:text-primary"
            >
              <FileText className="h-4 w-4" />
              Already written it? Import Markdown
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-secondary gap-4 px-6">
        {error ? (
          <>
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            <button
              type="button"
              onClick={() => void fetchProject()}
              className="text-sm font-medium text-primary hover:underline"
            >
              Retry
            </button>
          </>
        ) : (
          <>
            <p className="text-sm">Episode not found.</p>
            <button
              type="button"
              onClick={() => navigate("/episodes")}
              className="text-sm font-medium text-primary hover:underline"
            >
              Back to Episodes
            </button>
          </>
        )}
      </div>
    );
  }

  const turns = Array.isArray(project.transcript?.turns) ? project.transcript.turns : [];
  const state = project.session.state;
  const isFinished = state === "ready_to_generate" || state === "script_generated" || state === "script_edited" || state === "completed";
  const hasGeneratedScript = state === "script_generated" || state === "script_edited" || state === "completed";
  const isDeletedSession = Boolean(project.session.deleted_at);
  const hasUserTurns = turns.some((turn) => turn.speaker === "user");
  // Keep the dock visible during the first reply stream: landing → studio leaves
  // session.state as topic_defined until submit_reply finishes, which previously hid
  // both the composer and the Stop control for the entire first generation.
  const showStartInterview =
    !isDeletedSession
    && state === "topic_defined"
    && turns.length === 0
    && !submitting
    && streamingMessage === null;
  const showChatComposer = !isDeletedSession && !showStartInterview;
  // Source-backed episodes can generate before any reply; interviews need at least one answer.
  const canGenerateScript = hasUserTurns || isFinished;
  const scriptOffered = !isDeletedSession && Boolean(readiness?.can_offer_script) && state === "interview_in_progress";
  const coverage = readiness
    ? COVERAGE_ITEMS.map((item) => ({ ...item, done: Boolean(readiness[item.key]) }))
    : [];
  const coveredCount = coverage.filter((item) => item.done).length;

  const openLatestScript = async () => {
    if (!sessionId) return;
    setError(null);
    setRequestState({
      operation: "show_latest_script",
      phase: "running",
      progress_percent: 0,
      message: "Opening latest script...",
    });
    try {
      const p = await bridge.showLatestScript(sessionId);
      if (p.script?.script_id) {
        navigate(`/studio/${sessionId}/${p.script.script_id}`);
      } else {
        navigate(`/studio/${sessionId}`);
      }
      setRequestState(buildRequestState("show_latest_script", "succeeded", "Script opened."));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to open the latest script."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(err),
          buildRequestState("show_latest_script", "failed", "Failed to open the latest script."),
        ),
      );
    }
  };

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-outline px-3">
        <button
          type="button"
          onClick={() => navigate("/episodes")}
          aria-label="Back to Episodes"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-primary/5 hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0 flex-1">
          <SessionTopicEditor
            sessionId={project.session.session_id}
            topic={project.session.topic || "Untitled Episode"}
            density="header"
            disabled={isDeletedSession || submitting}
            onRenamed={async (updated) => {
              setProject(updated);
              await onRefresh();
            }}
          />
        </div>
        {coverage.length ? (
          <span
            className="hidden shrink-0 items-center gap-1.5 text-[12px] text-secondary sm:inline-flex"
            title={coverage.map((item) => `${item.done ? "✓" : "·"} ${item.label}`).join("\n")}
          >
            <span className="flex gap-0.5" aria-hidden="true">
              {coverage.map((item) => (
                <span
                  key={item.key}
                  className={cn("h-1.5 w-3 rounded-full", item.done ? "bg-accent-amber" : "bg-primary/10")}
                />
              ))}
            </span>
            {coveredCount} of {coverage.length} points covered
          </span>
        ) : null}
      </header>

      <div className="relative flex-1 min-h-0">
        <div ref={scrollRef} className="h-full overflow-y-auto w-full px-6 lg:px-12 scroll-smooth chat-container">
          <div className="max-w-3xl flex flex-col pt-6 gap-6 pb-56 mx-auto">
            {project.source ? (
              <details className="rounded-xl border border-outline px-3 py-2 text-xs text-secondary">
                <summary className="flex min-h-7 cursor-pointer items-center gap-1.5 font-medium text-primary">
                  <FileText className="h-3.5 w-3.5 text-secondary" />
                  Source: {project.source.title} · v{project.source.version}
                  <span className="font-normal text-secondary">(the script stays faithful to it)</span>
                </summary>
                <div className="mt-2 max-h-64 overflow-y-auto border-t border-outline pt-3 mac-scrollbar">
                  <div className="prose prose-sm prose-theme max-w-none text-[12px] leading-5">
                    <SafeMarkdown>{project.source.raw_markdown}</SafeMarkdown>
                  </div>
                </div>
              </details>
            ) : null}

            {showStartInterview && (
              <div className="py-8">
                <button
                  onClick={handleStart}
                  disabled={submitting}
                  className="px-5 py-2.5 bg-primary text-background rounded-xl text-sm font-semibold transition-opacity disabled:opacity-50"
                >
                  Start interview
                </button>
              </div>
            )}

            {/* Chat History: user bubbles right, assistant plain left */}
            <div className="flex flex-col gap-6">
              {error && (
                <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
                  {error}
                  {showLlmSetupAction ? (
                    <button
                      type="button"
                      onClick={() => navigate("/settings")}
                      className="ml-3 rounded-md border border-outline px-2 py-1 text-[12px] font-medium text-primary hover:bg-primary/5"
                    >
                      Open Settings
                    </button>
                  ) : null}
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
                    <div key={i} className="flex w-full justify-end">
                      <div className="max-w-[min(85%,32rem)] rounded-2xl rounded-tr-md bg-primary/[0.05] px-4 py-2.5">
                        <TurnAttachments sessionId={project.session.session_id} attachments={turn.attachments} />
                        {cleanContent ? (
                          <div
                            className={cn(
                              "text-[14px] leading-relaxed text-primary prose prose-sm prose-theme max-w-none [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0",
                              turn.attachments?.length ? "mt-2" : "",
                            )}
                          >
                            <SafeMarkdown>{cleanContent}</SafeMarkdown>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  );
                }

                return (
                  <div key={i} className="w-full">
                    <div className="text-[14px] leading-relaxed text-on-surface prose prose-sm prose-theme max-w-none [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
                      <SafeMarkdown>{cleanContent}</SafeMarkdown>
                    </div>
                    {insight ? (
                      <p className="mt-3 border-l-2 border-accent-amber/50 pl-3 text-[13px] text-secondary">{insight}</p>
                    ) : null}
                  </div>
                );
              })}

              {/* Streaming Content */}
              {streamingMessage !== null && (
                <div className="w-full text-[14px] leading-relaxed text-on-surface prose prose-sm prose-theme max-w-none [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
                  {streamingMessage ? (
                    <SafeMarkdown>{streamingMessage}</SafeMarkdown>
                  ) : (
                    <span className="flex items-center gap-1.5 h-6" aria-label="Thinking">
                      <span className="w-1.5 h-1.5 rounded-full bg-secondary/50 animate-bounce" />
                      <span className="w-1.5 h-1.5 rounded-full bg-secondary/50 animate-bounce [animation-delay:0.2s]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-secondary/50 animate-bounce [animation-delay:0.4s]" />
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Soft script offer and post-generation hint; generation itself stays in the composer. */}
            {scriptOffered || (isFinished && !isDeletedSession) ? (
              <div className="flex flex-wrap items-center gap-3 border-t border-outline pt-4">
                <p className="text-xs text-secondary flex-1 min-w-[200px]">
                  {scriptOffered
                    ? "There’s enough here for a script. Keep talking to go deeper, or generate it now."
                    : state === "ready_to_generate"
                      ? "Ready for a script. You can also keep talking and generate one later."
                      : "Keep talking any time. Each generation adds a new script without replacing earlier ones."}
                </p>
                {hasGeneratedScript ? (
                  <button
                    type="button"
                    onClick={() => void openLatestScript()}
                    className="px-3 py-1.5 border border-outline rounded-lg text-xs font-semibold text-primary hover:bg-primary/5 transition-colors shrink-0"
                  >
                    Open script
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        {/* Persistent Bottom Input Dock */}
        {showChatComposer && (
          <div className="absolute bottom-0 inset-x-0 z-20 bg-gradient-to-t from-background via-background to-transparent px-4 pb-5 pt-6">
            <div
              {...attachmentDropProps("composer")}
              className="mx-auto flex max-w-3xl flex-col gap-2 rounded-2xl border border-outline bg-surface-container-low p-3 shadow-[0_8px_24px_rgba(0,0,0,0.06)] transition-colors focus-within:border-primary/20"
            >
              <PendingAttachmentTray
                items={pendingAttachments}
                onRemove={(localId) => removeAttachment("composer", localId)}
                disabled={submitting}
              />
              <div
                ref={composerInputRef}
                contentEditable
                suppressContentEditableWarning
                onInput={(e) => setInputValue(e.currentTarget.innerText)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    // Block send while any chat action is in flight; drafts may still be typed.
                    if (submitting) return;
                    e.preventDefault();
                    handleSubmit();
                  }
                }}
                onPaste={handlePaste("composer")}
                className="w-full bg-transparent border-none focus:ring-0 overflow-y-auto text-[14px] text-primary py-1 px-1.5 max-h-[160px] min-h-[28px] outline-none leading-relaxed composer-editable select-text text-left"
                data-placeholder="Reply… (Shift+Enter for a new line)"
                aria-label="Reply"
              />

              {attachmentError ? (
                <p className="px-2 text-[12px] text-red-600 dark:text-red-400">{attachmentError}</p>
              ) : null}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1">
                  <input
                    ref={composerFileInputRef}
                    type="file"
                    multiple
                    accept={ATTACHMENT_ACCEPT}
                    className="hidden"
                    onChange={(e) => {
                      addAttachments("composer", Array.from(e.target.files ?? []));
                      e.target.value = "";
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => composerFileInputRef.current?.click()}
                    disabled={submitting}
                    className="p-1.5 text-secondary hover:text-primary hover:bg-primary/5 rounded-lg transition-colors shrink-0 disabled:opacity-30"
                    aria-label="Attach images or files"
                    title="Attach images or files"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleGenerateScript()}
                    disabled={submitting || !canGenerateScript}
                    title={!canGenerateScript ? "Answer a few questions before generating a script" : undefined}
                    className={cn(
                      "px-3 py-1.5 rounded-lg text-[12px] font-semibold transition-colors disabled:opacity-30",
                      scriptOffered || state === "ready_to_generate"
                        ? "bg-accent-amber/12 text-accent-amber hover:bg-accent-amber/18"
                        : "text-secondary hover:text-primary hover:bg-primary/5",
                    )}
                  >
                    {generatingScript ? "Generating…" : "Generate script"}
                  </button>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <ComposerModelPicker
                    disabled={submitting}
                    onConfigChange={() => void ensureLlmReady()}
                  />
                  {replyStreaming ? (
                    <button
                      type="button"
                      onClick={handleStopReply}
                      title="Stop"
                      aria-label="Stop"
                      className="p-2 bg-primary text-background rounded-full transition-opacity"
                    >
                      <Square className="w-3.5 h-3.5 fill-current" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleSubmit}
                      disabled={(!inputValue.trim() && pendingAttachments.length === 0) || submitting}
                      title={submitting ? "Working…" : "Send"}
                      aria-label={submitting ? "Working…" : "Send"}
                      className="p-2 bg-primary text-background rounded-full transition-opacity disabled:opacity-20 disabled:cursor-not-allowed"
                    >
                      {submitting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
