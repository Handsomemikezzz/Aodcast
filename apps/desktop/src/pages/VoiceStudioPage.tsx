import { motion } from "framer-motion";
import { ChevronDown, Clock3, Download, FileAudio, FolderOpen, Loader2, Mic, Pause, Play, RefreshCw, SlidersHorizontal, Wand2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { resolveAudioFileUrl } from "../lib/audioFile";
import { useBridge } from "../lib/BridgeContext";
import { getErrorMessage, isActiveRequestState, isTerminalRequestState } from "../lib/requestState";
import { revealInFinder } from "../lib/shellOps";
import { cn } from "../lib/utils";
import type {
  AudioTakeRecord,
  RequestState,
  ScriptRecord,
  SessionProject,
  VoicePreset,
  VoiceRenderSettings,
  VoiceStylePreset,
} from "../types";

const POLL_INTERVAL_MS = 1000;

function estimateMinutes(script: string): string {
  const words = script.trim().split(/\s+/).filter(Boolean).length;
  const minutes = Math.max(1, Math.round(words / 260));
  return `约 ${minutes} 分钟`;
}

function takeStatus(take: AudioTakeRecord, finalTakeId: string): string {
  return take.take_id === finalTakeId ? "最终版本" : "候选版本";
}

export function VoiceStudioPage() {
  const { sessionId: routeSessionId, scriptId: routeScriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const bridge = useBridge();
  const navigate = useNavigate();
  const previewAudioRef = useRef<HTMLAudioElement>(null);
  const pollingRef = useRef<number | null>(null);

  const [projects, setProjects] = useState<SessionProject[]>([]);
  const [scripts, setScripts] = useState<ScriptRecord[]>([]);
  const [project, setProject] = useState<SessionProject | null>(null);
  const [voices, setVoices] = useState<VoicePreset[]>([]);
  const [styles, setStyles] = useState<VoiceStylePreset[]>([]);
  const [previewText, setPreviewText] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState(routeSessionId ?? "");
  const [selectedScriptId, setSelectedScriptId] = useState(routeScriptId ?? "");
  const [selectedVoiceId, setSelectedVoiceId] = useState("warm_narrator");
  const [selectedStyleId, setSelectedStyleId] = useState("natural");
  const [speed, setSpeed] = useState(1.0);
  const [language, setLanguage] = useState("zh");
  const [audioFormat, setAudioFormat] = useState("wav");
  const [providerOverride, setProviderOverride] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [previewSrc, setPreviewSrc] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [requestState, setRequestState] = useState<RequestState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const scriptText = project?.script?.final?.trim() || project?.script?.draft?.trim() || "";
  const takes = project?.artifact?.takes ?? [];
  const finalTakeId = project?.artifact?.final_take_id ?? "";
  const selectedVoice = voices.find((voice) => voice.voice_id === selectedVoiceId) ?? voices[0];
  const selectedStyle = styles.find((style) => style.style_id === selectedStyleId) ?? styles[0];

  const settings: VoiceRenderSettings = useMemo(
    () => ({
      voice_id: selectedVoiceId,
      voice_name: selectedVoice?.name ?? "",
      style_id: selectedStyleId,
      style_name: selectedStyle?.name ?? "",
      speed,
      language,
      audio_format: audioFormat,
      preview_text: previewText,
    }),
    [audioFormat, language, previewText, selectedStyle?.name, selectedStyleId, selectedVoice?.name, selectedVoiceId, speed],
  );

  const selectedSession = projects.find((item) => item.session.session_id === selectedSessionId);

  const loadProject = async (sessionId: string, scriptId: string) => {
    if (!sessionId || !scriptId) return;
    const loaded = await bridge.showScript(sessionId, scriptId);
    setProject(loaded);
  };

  const refreshScripts = async (sessionId: string) => {
    if (!sessionId) {
      setScripts([]);
      return;
    }
    const loadedScripts = await bridge.listScripts(sessionId);
    setScripts(loadedScripts);
  };

  useEffect(() => {
    void (async () => {
      try {
        const [catalog, loadedProjects] = await Promise.all([bridge.listVoicePresets(), bridge.listProjects()]);
        setVoices(catalog.voices);
        setStyles(catalog.styles);
        setPreviewText(catalog.standard_preview_text);
        setProjects(loadedProjects);
        const ttsConfig = await bridge.showTTSConfig().catch(() => null);
        if (ttsConfig?.audio_format) setAudioFormat(ttsConfig.audio_format);
        if (ttsConfig?.provider) setProviderOverride(ttsConfig.provider);
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load Voice Studio."));
      }
    })();
  }, [bridge]);

  useEffect(() => {
    void refreshScripts(selectedSessionId).catch((err) => setError(getErrorMessage(err, "Failed to load scripts.")));
  }, [selectedSessionId]);

  useEffect(() => {
    void loadProject(selectedSessionId, selectedScriptId).catch((err) => setError(getErrorMessage(err, "Failed to load script.")));
  }, [selectedScriptId, selectedSessionId]);

  useEffect(() => {
    return () => {
      if (pollingRef.current !== null) window.clearInterval(pollingRef.current);
    };
  }, []);

  const stopPolling = () => {
    if (pollingRef.current !== null) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  const startPolling = (taskId: string) => {
    stopPolling();
    pollingRef.current = window.setInterval(() => {
      void bridge.showTaskState(taskId)
        .then(async (state) => {
          if (!state) return;
          setRequestState(state);
          if (isTerminalRequestState(state)) {
            stopPolling();
            setRendering(false);
            await loadProject(selectedSessionId, selectedScriptId);
          } else if (isActiveRequestState(state)) {
            setRendering(true);
          }
        })
        .catch((err) => setError(getErrorMessage(err, "Lost connection to rendering runtime.")));
    }, POLL_INTERVAL_MS);
  };

  const handlePreview = async () => {
    try {
      setPreviewing(true);
      setError(null);
      const result = await bridge.renderVoicePreview(settings);
      setPreviewSrc(resolveAudioFileUrl(result.audio_path));
      window.setTimeout(() => {
        void previewAudioRef.current?.play().catch(() => undefined);
      }, 100);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to render preview."));
    } finally {
      setPreviewing(false);
    }
  };

  const handleRenderTake = async () => {
    if (!selectedSessionId || !selectedScriptId) return;
    try {
      setRendering(true);
      setError(null);
      setMessage(null);
      const result = await bridge.renderVoiceTake(selectedSessionId, selectedScriptId, settings, {
        providerOverride,
        scriptId: selectedScriptId,
      });
      const state = result.request_state ?? {
        operation: "render_voice_take",
        phase: "running",
        progress_percent: 5,
        message: "Rendering voice take...",
      };
      setRequestState(state);
      startPolling(result.task_id ?? `render_voice_take:${selectedSessionId}`);
    } catch (err) {
      setRendering(false);
      setError(getErrorMessage(err, "Failed to render voice take."));
    }
  };

  const handleCancel = async () => {
    const state = await bridge.cancelTask(`render_voice_take:${selectedSessionId}`);
    if (state) setRequestState(state);
  };

  const handleSetFinal = async (take: AudioTakeRecord) => {
    try {
      setError(null);
      const updated = await bridge.setFinalVoiceTake(selectedSessionId, take.take_id);
      setProject(updated);
      setMessage("已设为最终版本，Script 页音频区会显示该 take。");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to set final take."));
    }
  };

  const handleAudioLoadError = () => {
    setError("无法加载音频文件。文件可能已移动或删除，请重新生成音频。");
  };

  const handleDownload = (take: AudioTakeRecord) => {
    const src = resolveAudioFileUrl(take.audio_path);
    const filename = take.audio_path.split("/").pop() || "voice-take.wav";
    const link = document.createElement("a");
    link.href = src;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="h-full overflow-y-auto px-5 py-5 lg:px-8">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-5">
        <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-amber">Voice Studio</p>
              <h1 className="mt-2 font-headline text-2xl font-semibold text-primary">语音工坊</h1>
              <p className="mt-2 text-sm text-secondary">从脚本到成品音频：选择音色、调节表达、试听并对比最多 2 个 take。</p>
            </div>
            <button
              type="button"
              onClick={() => selectedSessionId && selectedScriptId && navigate(`/script/${selectedSessionId}/${selectedScriptId}`)}
              className="rounded-2xl border border-outline bg-surface-container-low px-4 py-2 text-sm font-medium text-primary hover:bg-surface-container"
            >
              返回 Script
            </button>
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="space-y-5">
            <section className="rounded-[28px] border border-outline bg-surface p-5">
              <h2 className="text-sm font-semibold text-primary">脚本选择</h2>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <select
                  value={selectedSessionId}
                  onChange={(event) => {
                    setSelectedSessionId(event.target.value);
                    setSelectedScriptId("");
                    setProject(null);
                  }}
                  className="rounded-2xl border border-outline bg-background px-3 py-3 text-sm text-primary"
                >
                  <option value="">选择 session</option>
                  {projects.map((item) => (
                    <option key={item.session.session_id} value={item.session.session_id}>{item.session.topic || "Untitled"}</option>
                  ))}
                </select>
                <select
                  value={selectedScriptId}
                  onChange={(event) => setSelectedScriptId(event.target.value)}
                  className="rounded-2xl border border-outline bg-background px-3 py-3 text-sm text-primary"
                >
                  <option value="">选择脚本</option>
                  {scripts.map((script) => (
                    <option key={script.script_id} value={script.script_id}>{script.name}</option>
                  ))}
                </select>
              </div>
              {project?.script ? (
                <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                  <div className="rounded-2xl border border-outline bg-background p-3">
                    <p className="text-xs text-secondary">当前脚本</p>
                    <p className="mt-1 truncate font-medium text-primary">{project.script.name}</p>
                  </div>
                  <div className="rounded-2xl border border-outline bg-background p-3">
                    <p className="text-xs text-secondary">所属项目</p>
                    <p className="mt-1 truncate font-medium text-primary">{selectedSession?.session.topic ?? project.session.topic}</p>
                  </div>
                  <div className="rounded-2xl border border-outline bg-background p-3">
                    <p className="text-xs text-secondary">预计时长</p>
                    <p className="mt-1 font-medium text-primary">{estimateMinutes(scriptText)}</p>
                  </div>
                </div>
              ) : null}
            </section>

            <section className="rounded-[28px] border border-outline bg-surface p-5">
              <h2 className="text-sm font-semibold text-primary">主播音色</h2>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {voices.map((voice) => (
                  <button
                    key={voice.voice_id}
                    type="button"
                    onClick={() => setSelectedVoiceId(voice.voice_id)}
                    className={cn(
                      "rounded-[22px] border p-4 text-left transition-colors",
                      selectedVoiceId === voice.voice_id ? "border-accent-amber bg-accent-amber/10" : "border-outline bg-background hover:border-accent-amber/30",
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-primary">{voice.name}</p>
                      <Mic className="h-4 w-4 text-accent-amber" />
                    </div>
                    <p className="mt-2 text-xs leading-5 text-secondary">{voice.description}</p>
                    <p className="mt-2 text-xs text-secondary">{voice.scenario}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {voice.tags.map((tag) => (
                        <span key={tag} className="rounded-full border border-outline px-2 py-0.5 text-[11px] text-secondary">{tag}</span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-[28px] border border-outline bg-surface p-5">
              <h2 className="text-sm font-semibold text-primary">表达设置</h2>
              <div className="mt-4 rounded-[22px] border border-outline bg-background p-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-primary">语速</span>
                  <span className="font-medium text-accent-amber">{speed.toFixed(1)}x</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.2"
                  step="0.1"
                  value={speed}
                  onChange={(event) => setSpeed(Number(event.target.value))}
                  className="mt-4 w-full accent-[rgb(227,171,73)]"
                />
                <div className="mt-2 flex justify-between text-xs text-secondary">
                  <span>0.8x 偏慢</span><span>1.0x 标准</span><span>1.2x 偏快</span>
                </div>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-4">
                {styles.map((style) => (
                  <button
                    key={style.style_id}
                    type="button"
                    onClick={() => setSelectedStyleId(style.style_id)}
                    className={cn(
                      "rounded-2xl border px-3 py-3 text-sm font-medium transition-colors",
                      selectedStyleId === style.style_id ? "border-accent-amber bg-accent-amber/10 text-primary" : "border-outline bg-background text-secondary hover:text-primary",
                    )}
                  >
                    {style.name}
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-[28px] border border-outline bg-surface p-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-primary">组合试音</h2>
                  <p className="mt-1 text-xs text-secondary">当前试音用于比较音色与风格，长文本效果可能因脚本内容略有差异。</p>
                </div>
                <button
                  type="button"
                  onClick={() => void handlePreview()}
                  disabled={previewing || !selectedVoice || !selectedStyle}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl bg-accent-amber px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
                >
                  {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  生成组合试音
                </button>
              </div>
              <textarea
                value={previewText}
                onChange={(event) => setPreviewText(event.target.value)}
                rows={3}
                placeholder="输入一句你想用来比较音色与风格的试音文本"
                className="mt-4 w-full resize-none rounded-2xl border border-outline bg-background px-4 py-3 text-sm text-primary outline-none focus:border-accent-amber/40"
              />
              <p className="mt-2 text-[11px] text-secondary">留空时使用系统标准试音句。</p>
              {previewSrc ? <audio ref={previewAudioRef} controls src={previewSrc} onError={handleAudioLoadError} className="mt-4 w-full" /> : null}
            </section>
          </div>

          <aside className="space-y-5">
            <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
              <button type="button" onClick={() => setAdvancedOpen(!advancedOpen)} className="flex w-full items-center justify-between gap-3 text-left">
                <span>
                  <span className="flex items-center gap-2 text-sm font-semibold text-primary"><SlidersHorizontal className="h-4 w-4 text-accent-amber" /> 高级设置：模型、语言与输出格式</span>
                  <span className="mt-1 block text-xs text-secondary">通常无需修改。默认设置会根据所选音色自动选择合适模型。</span>
                </span>
                <ChevronDown className={cn("h-4 w-4 text-secondary transition-transform", advancedOpen && "rotate-180")} />
              </button>
              {advancedOpen ? (
                <div className="mt-4 grid gap-3">
                  <label className="text-xs text-secondary">引擎 / Provider override
                    <input value={providerOverride} onChange={(event) => setProviderOverride(event.target.value)} className="mt-1 w-full rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary" />
                  </label>
                  <label className="text-xs text-secondary">语言
                    <input value={language} onChange={(event) => setLanguage(event.target.value)} className="mt-1 w-full rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary" />
                  </label>
                  <label className="text-xs text-secondary">输出格式
                    <input value={audioFormat} onChange={(event) => setAudioFormat(event.target.value)} className="mt-1 w-full rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary" />
                    <p className="mt-1 text-[11px] text-secondary">
                      只影响本次 Voice Studio take；Script 页“生成完整音频”仍使用 Settings 中保存的 TTS 格式。MP4 指 audio-only 容器，不含视频画面。
                    </p>
                  </label>
                </div>
              ) : null}
            </section>

            <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-primary">完整音频生成</h2>
                  <p className="mt-1 text-xs text-secondary">预计生成耗时：约 2-4 分钟。首次生成可能需要更久。</p>
                </div>
                <Clock3 className="h-5 w-5 text-accent-amber" />
              </div>
              {requestState ? (
                <div className="mt-4 rounded-2xl border border-outline bg-background p-3 text-sm text-secondary">
                  {Math.round(requestState.progress_percent)}% · {requestState.message}
                </div>
              ) : null}
              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  onClick={() => void handleRenderTake()}
                  disabled={rendering || !selectedSessionId || !selectedScriptId || !scriptText}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl bg-accent-amber px-4 py-3 text-sm font-semibold text-black disabled:opacity-50"
                >
                  {rendering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                  {takes.length > 0 ? "重新生成一个 take" : "生成完整音频"}
                </button>
                {rendering ? (
                  <button type="button" onClick={() => void handleCancel()} className="rounded-2xl border border-outline px-4 py-3 text-sm text-primary">取消</button>
                ) : null}
              </div>
              {error ? <p className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-200">{error}</p> : null}
              {message ? <p className="mt-4 rounded-2xl border border-accent-amber/20 bg-accent-amber/10 p-3 text-sm text-accent-amber">{message}</p> : null}
            </section>

            <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-primary">Take 对比</h2>
                  <p className="mt-1 text-xs text-secondary">最多保留最终 take + 最新候选 take。</p>
                </div>
                <FileAudio className="h-5 w-5 text-accent-amber" />
              </div>
              <div className="space-y-3">
                {takes.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-outline p-5 text-center text-sm text-secondary">还没有 take。生成完整音频后可在这里对比。</div>
                ) : takes.map((take) => {
                  const src = resolveAudioFileUrl(take.audio_path);
                  return (
                    <div key={take.take_id} className="rounded-[22px] border border-outline bg-background p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-primary">{takeStatus(take, finalTakeId)}</p>
                          <p className="mt-1 text-xs text-secondary">{take.voice_name} / {take.style_name} / {take.speed.toFixed(1)}x</p>
                          <p className="mt-1 text-[11px] text-secondary">{new Date(take.created_at).toLocaleString()}</p>
                        </div>
                        <button type="button" onClick={() => void revealInFinder(take.audio_path)} className="rounded-xl border border-outline p-2 text-secondary hover:text-primary">
                          <FolderOpen className="h-4 w-4" />
                        </button>
                      </div>
                      <audio controls src={src} onError={handleAudioLoadError} className="mt-3 w-full" />
                      <div className="mt-3 grid grid-cols-2 gap-2">
                        <button type="button" onClick={() => void handleSetFinal(take)} disabled={take.take_id === finalTakeId} className="rounded-xl border border-outline px-3 py-2 text-xs font-medium text-primary disabled:opacity-50">
                          设为最终版本
                        </button>
                        <button type="button" onClick={() => handleDownload(take)} className="inline-flex items-center justify-center gap-1 rounded-xl border border-outline px-3 py-2 text-xs font-medium text-primary">
                          <Download className="h-3.5 w-3.5" /> 下载
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <button type="button" onClick={() => selectedSessionId && selectedScriptId && void loadProject(selectedSessionId, selectedScriptId)} className="mt-3 inline-flex items-center gap-2 text-xs text-secondary hover:text-primary">
                <RefreshCw className="h-3.5 w-3.5" /> 刷新 take
              </button>
            </section>
          </aside>
        </div>
      </div>
    </motion.div>
  );
}
