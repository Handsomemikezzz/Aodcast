import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from 'framer-motion';
import { Timer, FileText, Mic, CloudDownload, Cpu, CheckCircle2, PlayCircle, Settings, Wand2 } from 'lucide-react';
import { useBridge } from "../lib/BridgeContext";
import { RequestState, SessionProject, TTSCapability, TTSProviderConfig } from "../types";
import { cn } from "../lib/utils";
import { convertFileSrc } from "@tauri-apps/api/core";
import { revealInFinder } from "../lib/shellOps";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  isActiveRequestState,
  isTerminalRequestState,
  withRequestStateFallback,
} from "../lib/requestState";

const POLL_INTERVAL_MS = 1000;
const POLL_FAILURE_THRESHOLD = 3;

function estimateWordCount(text: string): number {
  const normalized = text.trim();
  if (!normalized) return 0;
  const cjkMatches = normalized.match(/[\u3400-\u9FFF\uF900-\uFAFF]/g);
  if (cjkMatches && cjkMatches.length > 0) {
    const latinWordCount = normalized
      .replace(/[\u3400-\u9FFF\uF900-\uFAFF]/g, " ")
      .split(/\s+/)
      .filter(Boolean).length;
    return Math.max(latinWordCount, Math.ceil(cjkMatches.length / 2));
  }
  return normalized.split(/\s+/).filter(Boolean).length;
}

export function GeneratePage({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const { sessionId, scriptId } = useParams<{ sessionId: string; scriptId?: string }>();
  const bridge = useBridge();
  const taskId = sessionId ? `render_audio:${sessionId}` : "";

  const [project, setProject] = useState<SessionProject | null>(null);
  const [capability, setCapability] = useState<TTSCapability | null>(null);
  const [ttsConfig, setTtsConfig] = useState<TTSProviderConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestState, setRequestState] = useState<RequestState | null>(null);
  const [pollWarning, setPollWarning] = useState<string | null>(null);
  const pollHandleRef = useRef<number | null>(null);
  const pollingInFlightRef = useRef(false);
  const pollFailureCountRef = useRef(0);
  const expectedRunTokenRef = useRef<string | null>(null);

  const stopTaskPolling = () => {
    if (pollHandleRef.current !== null) {
      window.clearInterval(pollHandleRef.current);
      pollHandleRef.current = null;
    }
    pollingInFlightRef.current = false;
    pollFailureCountRef.current = 0;
  };

  const acceptPolledState = (state: RequestState | null): boolean => {
    if (!state) return false;
    const expected = expectedRunTokenRef.current;
    if (expected && state.run_token !== expected) {
      return false;
    }
    setRequestState((prev) => {
      if ((prev?.phase === "cancelling" || prev?.phase === "cancelled") && state.phase === "running") {
        return prev;
      }
      return state;
    });
    if (isTerminalRequestState(state)) {
      stopTaskPolling();
      setGenerating(false);
    } else {
      setGenerating(true);
    }
    return true;
  };

  const startTaskPolling = () => {
    if (!taskId || pollHandleRef.current !== null) return;
    pollFailureCountRef.current = 0;
    setPollWarning(null);
    pollHandleRef.current = window.setInterval(() => {
      if (pollingInFlightRef.current) return;
      pollingInFlightRef.current = true;
      void bridge
        .showTaskState(taskId)
        .then((state) => {
          pollFailureCountRef.current = 0;
          setPollWarning((prev) => (prev ? null : prev));
          acceptPolledState(state);
        })
        .catch((err: unknown) => {
          pollFailureCountRef.current += 1;
          if (pollFailureCountRef.current >= POLL_FAILURE_THRESHOLD) {
            const message = getErrorMessage(err, "Lost connection to the rendering runtime.");
            setPollWarning(message);
          }
        })
        .finally(() => {
          pollingInFlightRef.current = false;
        });
    }, POLL_INTERVAL_MS);
  };

  const syncTaskState = async (): Promise<RequestState | null> => {
    if (!taskId) return null;
    const state = await bridge.showTaskState(taskId);
    if (!state) return null;
    const expected = expectedRunTokenRef.current;
    if (expected && state.run_token !== expected) {
      return null;
    }
    setRequestState((prev) => {
      if ((prev?.phase === "cancelling" || prev?.phase === "cancelled") && state.phase === "running") {
        return prev;
      }
      return state;
    });
    return state;
  };

  useEffect(() => {
    async function loadData() {
      if (!sessionId) return;
      try {
        setLoading(true);
        setError(null);
        const [currentProject, cap, config] = await Promise.all([
          scriptId?.trim()
            ? bridge.showScript(sessionId, scriptId)
            : bridge.showSession(sessionId, { includeDeleted: true }),
          bridge.getLocalTTSCapability(),
          bridge.showTTSConfig(),
        ]);
        setProject(currentProject);
        setCapability(cap);
        setTtsConfig(config);
      } catch (err: unknown) {
        setError(getErrorMessage(err, "Failed to load project"));
        setRequestState(getErrorRequestState(err));
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [sessionId, scriptId, bridge]);

  useEffect(() => {
    if (!taskId) return;
    expectedRunTokenRef.current = null;
    void syncTaskState()
      .then((state) => {
        if (state && isActiveRequestState(state)) {
          expectedRunTokenRef.current = state.run_token ?? null;
          setGenerating(true);
          startTaskPolling();
        } else {
          setGenerating(false);
        }
      })
      .catch(() => undefined);

    return () => {
      stopTaskPolling();
      expectedRunTokenRef.current = null;
    };
  }, [taskId]);

  const handleGenerateAudio = async (providerOverride: string) => {
    if (!sessionId || !taskId) return;
    try {
      expectedRunTokenRef.current = null;
      stopTaskPolling();
      const existingState = await syncTaskState();
      if (existingState && isActiveRequestState(existingState)) {
        expectedRunTokenRef.current = existingState.run_token ?? null;
        setGenerating(true);
        startTaskPolling();
        return;
      }
      setGenerating(true);
      setError(null);
      setRequestState({
        operation: "render_audio",
        phase: "running",
        progress_percent: 0,
        message: "Rendering audio...",
      });
      const targetScriptId = scriptId?.trim() || project?.script?.script_id || "";
      const result = await bridge.renderAudio(sessionId, { providerOverride, scriptId: targetScriptId });
      const runToken =
        typeof result.run_token === "string" && result.run_token.length > 0
          ? result.run_token
          : result.request_state?.run_token ?? null;
      expectedRunTokenRef.current = runToken;
      setProject(result.project);
      const finalTaskId = result.task_id ?? taskId;
      const finalState = await bridge.showTaskState(finalTaskId).catch(() => null);
      const chosenState =
        finalState ?? result.request_state ?? buildRequestState("render_audio", "running", "Rendering audio...");
      if (runToken && !chosenState.run_token) {
        chosenState.run_token = runToken;
      }
      setRequestState(chosenState);
      if (isTerminalRequestState(chosenState)) {
        setGenerating(false);
      } else {
        setGenerating(true);
        startTaskPolling();
      }
      await onRefresh();
    } catch (err: unknown) {
      const errorState = getErrorRequestState(err);
      if (errorState?.phase === "cancelled") {
        setError(null);
      } else {
        setError(getErrorMessage(err, "Failed to render audio"));
      }
      setRequestState(
        withRequestStateFallback(
          errorState,
          buildRequestState("render_audio", "failed", "Failed to render audio."),
        ),
      );
      setGenerating(false);
      stopTaskPolling();
    }
  };

  const handleCancelAudio = async () => {
    if (!sessionId || !taskId) return;
    try {
      const state = await bridge.cancelTask(taskId);
      if (state) {
        setRequestState(state);
      } else {
        setRequestState(
          buildRequestState("render_audio", "cancelling", "Cancellation requested."),
        );
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to request cancellation"));
    }
  };

  const handleRevealInFinder = async () => {
    if (!project?.artifact?.audio_path) return;
    try {
      await revealInFinder(project.artifact.audio_path);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to open file manager"));
    }
  };

  const cloudProvider = useMemo(() => {
    const configuredProvider = ttsConfig?.provider?.trim();
    if (configuredProvider && configuredProvider !== "local_mlx") {
      return configuredProvider;
    }
    return capability?.fallback_provider || "mock_remote";
  }, [capability?.fallback_provider, ttsConfig?.provider]);

  const wordCount = useMemo(
    () => {
      const source = project?.script?.final?.trim() || project?.script?.draft?.trim() || "";
      return estimateWordCount(source);
    },
    [project?.script?.final, project?.script?.draft],
  );
  const estMinutes = wordCount === 0 ? 0 : Math.max(1, Math.round(wordCount / 150));

  if (loading) {
    return <div className="flex h-full items-center justify-center text-secondary text-sm">Loading orchestration settings...</div>;
  }

  if (!project || !sessionId) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-secondary gap-4">
        <Wand2 className="w-12 h-12 text-outline-variant mb-2" />
        <div className="text-center">
          <h2 className="text-lg font-semibold text-primary mb-1">No session</h2>
          <p className="text-sm">Open Script and choose a podcast, then use the Text to speech tab.</p>
        </div>
      </div>
    );
  }

  const { artifact, session } = project;
  let audioSrc = "";
  if (artifact?.audio_path) {
    try {
      audioSrc = convertFileSrc(artifact.audio_path);
    } catch {
      audioSrc = `file://${artifact.audio_path}`;
    }
  }

  const voices = [
    {
      id: session.tts_provider || "default",
      name: session.tts_provider || "System Default",
      description: capability?.available ? "Local MLX Engine" : "API Fallback",
    },
  ];

  const localEngineDisabled = generating || !capability?.available;
  const cloudEngineDisabled = generating;
  const cloudEngineDescription =
    cloudProvider === "openai_compatible"
      ? "Configured API provider. Requires internet connection."
      : "Fallback cloud-safe engine for a single render.";

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col lg:flex-row h-full w-full"
    >
      {/* Main settings area - Left aligned */}
      <div className="flex-1 overflow-y-auto px-6 lg:px-12 py-8">
        <div className="max-w-3xl">
          <div className="mb-8 border-b border-outline pb-6">
            <h1 className="text-2xl font-headline font-bold text-primary mb-2">
              Voice &amp; export
            </h1>
            <p className="text-secondary text-sm">
              Render audio locally or via the cloud, then preview and export your podcast file.
            </p>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-500 text-sm font-medium">
              {error}
            </div>
          )}
          {pollWarning && (
            <div className="mb-6 p-3 border border-amber-500/30 bg-amber-500/10 rounded-lg text-amber-500 text-xs font-medium">
              {pollWarning}
            </div>
          )}
          {!error && isActiveRequestState(requestState) && (
            <div className="mb-6 p-3 border border-outline rounded-lg text-secondary text-xs flex items-center justify-between gap-3">
              <span>{`${Math.round(requestState!.progress_percent)}% · ${requestState!.message}`}</span>
              {generating && requestState?.phase === "running" && (
                <button
                  type="button"
                  onClick={() => void handleCancelAudio()}
                  className="px-2 py-1 rounded border border-outline text-[11px] font-medium hover:bg-surface-container"
                >
                  Cancel
                </button>
              )}
            </div>
          )}
          {!error && requestState?.phase === "cancelled" && (
            <div className="mb-6 p-3 border border-outline rounded-lg text-secondary text-xs">
              {requestState.message}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="bg-surface-container p-5 rounded-xl border border-outline">
              <div className="flex items-center gap-2 mb-3">
                <Timer className="w-4 h-4 text-accent-amber" />
                <span className="text-xs font-semibold text-secondary uppercase tracking-wider">Estimated Duration</span>
              </div>
              <p className="text-3xl font-headline font-bold text-primary">~{estMinutes}m</p>
            </div>
            
            <div className="bg-surface-container p-5 rounded-xl border border-outline">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-4 h-4 text-accent-amber" />
                <span className="text-xs font-semibold text-secondary uppercase tracking-wider">Word Count</span>
              </div>
              <p className="text-3xl font-headline font-bold text-primary">{wordCount}</p>
            </div>
          </div>

          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
               <h3 className="font-headline font-semibold text-primary">Voice Persona</h3>
               <button
                 type="button"
                 disabled
                 title="Coming soon"
                 className="text-xs font-medium text-accent-amber/60 flex items-center gap-1 cursor-not-allowed disabled:opacity-60"
               >
                 <Settings className="w-3 h-3" /> Manage Voices
               </button>
            </div>
            
            <div className="space-y-3">
              {voices.map((voice) => (
                <div 
                  key={voice.id}
                  className="w-full flex items-center justify-between p-4 rounded-xl border border-accent-amber/40 bg-accent-amber/5 ring-1 ring-accent-amber/10 shadow-sm transition-all"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full flex items-center justify-center bg-background border border-outline">
                      <Mic className="w-5 h-5 text-accent-amber" />
                    </div>
                    <div>
                      <p className="font-semibold text-sm text-primary">
                        {voice.name}
                      </p>
                      <p className="text-xs text-secondary mt-0.5">{voice.description}</p>
                    </div>
                  </div>
                  <CheckCircle2 className="w-5 h-5 text-accent-amber" />
                </div>
              ))}
            </div>
          </div>

          <div>
             <h3 className="font-headline font-semibold text-primary mb-4">Rendering Engine</h3>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <button 
                  onClick={() => void handleGenerateAudio(cloudProvider)}
                  disabled={cloudEngineDisabled}
                  className={cn(
                    "p-5 rounded-xl border text-left transition-all relative overflow-hidden group",
                    !cloudEngineDisabled
                      ? "border-accent-amber/30 bg-surface hover:bg-surface-container shadow-sm"
                      : "border-outline bg-surface-container opacity-60 cursor-not-allowed"
                  )}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <CloudDownload className={cn("w-5 h-5", !cloudEngineDisabled ? "text-accent-amber" : "text-secondary")} />
                    <span className="font-semibold text-sm">Cloud Synthesis</span>
                  </div>
                  <p className="text-xs text-secondary mb-3">{cloudEngineDescription}</p>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-secondary">
                    {generating ? "Generating..." : `Provider: ${cloudProvider}`}
                  </span>
                </button>

                <button 
                  onClick={() => void handleGenerateAudio("local_mlx")}
                  disabled={localEngineDisabled}
                  className={cn(
                    "p-5 rounded-xl border text-left transition-all relative overflow-hidden group",
                    !localEngineDisabled
                      ? "border-accent-amber bg-accent-amber text-black shadow-md hover:bg-accent-amber/90"
                      : "border-outline bg-surface-container opacity-60 cursor-not-allowed"
                  )}
                >
                  <div className="flex items-center gap-3 mb-2">
                    {generating ? <div className="w-5 h-5 rounded-full border-2 border-black/20 border-t-black animate-spin" /> : <Cpu className="w-5 h-5" />}
                    <span className="font-semibold text-sm">Local MLX Engine</span>
                  </div>
                  <p className={cn("text-xs mb-3", !localEngineDisabled ? "text-black/70" : "text-secondary")}>
                    High-performance local rendering using Apple Silicon.
                  </p>
                  <span className={cn("text-[10px] font-bold uppercase tracking-wider", !localEngineDisabled ? "text-black/80" : "text-secondary")}>
                    {generating ? "Rendering locally..." : "Recommended"}
                  </span>
                </button>
             </div>
          </div>

        </div>
      </div>

      {/* Right Sidebar - Output Preview */}
      <div className="w-full lg:w-[320px] shrink-0 border-l border-outline bg-accent-amber/5 ring-1 ring-inset ring-accent-amber/10 flex flex-col transition-all">
         <div className="p-4 border-b border-outline flex items-center justify-between">
            <h3 className="font-semibold text-sm text-primary">Output Artifacts</h3>
            <span className="flex h-2 w-2 rounded-full bg-accent-amber animate-pulse" />
         </div>
         
         <div className="flex-1 p-4 flex flex-col">
            {artifact?.audio_path ? (
              <div className="bg-surface-container rounded-xl p-4 border border-outline shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded bg-accent-amber/20 flex items-center justify-center">
                      <PlayCircle className="w-4 h-4 text-accent-amber" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-primary">Final Audio</p>
                      <p className="text-[10px] text-secondary">Ready to play</p>
                    </div>
                  </div>
                </div>
                
                <audio 
                  id="generated-audio"
                  controls 
                  className="w-full h-8 outline-none mb-3 [&::-webkit-media-controls-panel]:bg-background [&::-webkit-media-controls-panel]:border [&::-webkit-media-controls-panel]:border-outline"
                  src={audioSrc}
                />
                
                <div className="bg-background rounded p-2 overflow-hidden mb-4">
                  <p className="text-[10px] text-secondary font-mono truncate" title={artifact.audio_path}>
                    {artifact.audio_path.split('/').pop()}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => void handleRevealInFinder()}
                  className="w-full py-2 bg-surface-container-high hover:bg-surface-container-highest border border-outline rounded-lg text-xs font-medium text-primary transition-colors flex items-center justify-center gap-2"
                >
                  <Wand2 className="w-3.5 h-3.5" />
                  Reveal in Finder
                </button>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6 border border-dashed border-accent-amber/40 bg-accent-amber/5 rounded-xl transition-colors">
                 <Wand2 className="w-8 h-8 mb-3 text-accent-amber" />
                 <p className="text-sm font-medium text-secondary">No audio generated yet.</p>
                 <p className="text-xs text-outline mt-1">
                   Configure the engine on the left and run synthesis to see the file here.
                 </p>
              </div>
            )}
         </div>
      </div>
    </motion.div>
  );
}
