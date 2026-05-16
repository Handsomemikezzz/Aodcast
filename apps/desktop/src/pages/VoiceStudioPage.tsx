import { motion } from "framer-motion";
import { CheckCircle2, ChevronDown, Clock3, Download, FileAudio, FolderOpen, Loader2, Mic, Play, RefreshCw, SlidersHorizontal, Trash2, Wand2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { resolveAudioFileUrl } from "../lib/audioFile";
import { useBridge } from "../lib/BridgeContext";
import { getErrorMessage, isActiveRequestState, isTerminalRequestState } from "../lib/requestState";
import { revealInFinder } from "../lib/shellOps";
import { cn } from "../lib/utils";
import { resolveProjectVoiceSettings } from "../lib/voiceSettings";
import type {
  AudioTakeRecord,
  ModelStatus,
  RequestState,
  ScriptRecord,
  SessionProject,
  TTSCapability,
  TTSProviderConfig,
  VoicePreset,
  VoiceProfileRecord,
  VoiceRenderSettings,
  VoiceStylePreset,
} from "../types";

const POLL_INTERVAL_MS = 1000;
const DEFAULT_QWEN3_TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit";
type PreviewTextMode = "standard" | "script_opening" | "custom";

function estimateMinutes(script: string): string {
  const words = script.trim().split(/\s+/).filter(Boolean).length;
  const minutes = Math.max(1, Math.round(words / 260));
  return `约 ${minutes} 分钟`;
}

function takeStatus(take: AudioTakeRecord, finalTakeId: string): string {
  return take.take_id === finalTakeId ? "最终版本" : "候选版本";
}

function resolvedTtsModel(config: TTSProviderConfig | null): string {
  const raw = config?.model?.trim() ?? "";
  if (!raw || raw === "mock-voice") return DEFAULT_QWEN3_TTS_MODEL;
  return raw;
}

function shortRepoName(repo: string): string {
  return repo.split("/").pop()?.replace("Qwen3-TTS-12Hz-", "Qwen TTS ")?.replace("-Base-8bit", "") ?? repo;
}

function scriptOpeningText(script: string): string {
  return script.trim().replace(/\s+/g, " ").slice(0, 180);
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
  const [voiceProfiles, setVoiceProfiles] = useState<VoiceProfileRecord[]>([]);
  const [styles, setStyles] = useState<VoiceStylePreset[]>([]);
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [ttsConfig, setTtsConfig] = useState<TTSProviderConfig | null>(null);
  const [ttsCapability, setTtsCapability] = useState<TTSCapability | null>(null);
  const [standardPreviewText, setStandardPreviewText] = useState("");
  const [previewTextMode, setPreviewTextMode] = useState<PreviewTextMode>("standard");
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
  const [previewPath, setPreviewPath] = useState("");
  const [lastPreviewProvider, setLastPreviewProvider] = useState("");
  const [lastPreviewModel, setLastPreviewModel] = useState("");
  const [lastPreviewSettings, setLastPreviewSettings] = useState<VoiceRenderSettings | null>(null);
  const [previewKey, setPreviewKey] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [previewRequestState, setPreviewRequestState] = useState<RequestState | null>(null);
  const [rendering, setRendering] = useState(false);
  const [requestState, setRequestState] = useState<RequestState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const scriptText = project?.script?.final?.trim() || project?.script?.draft?.trim() || "";
  const scriptOpening = scriptOpeningText(scriptText);
  const effectivePreviewText =
    previewTextMode === "script_opening"
      ? scriptOpening || standardPreviewText
      : previewTextMode === "standard"
        ? standardPreviewText
        : previewText;
  const takes = project?.artifact?.takes ?? [];
  const finalTakeId = project?.artifact?.final_take_id ?? "";
  const voiceReference = project?.artifact?.voice_reference;
  const selectedProfile = voiceReference?.voice_profile_id
    ? voiceProfiles.find((profile) => profile.voice_profile_id === voiceReference.voice_profile_id)
    : undefined;
  const selectedProfileId = selectedProfile?.voice_profile_id ?? "";
  const selectedVoice = voices.find((voice) => voice.voice_id === selectedVoiceId) ?? voices[0];
  const selectedStyle = styles.find((style) => style.style_id === selectedStyleId) ?? styles[0];
  const resolvedModel = resolvedTtsModel(ttsConfig);
  const currentModel = models.find((model) => model.hf_repo_id === resolvedModel);
  const localPathConfigured = Boolean(ttsConfig?.local_model_path?.trim());
  const isLocalEngine = ttsConfig?.provider === "local_mlx";
  const localCatalogModelInstalled = Boolean(currentModel?.downloaded);
  const localPathReady = Boolean(localPathConfigured && ttsCapability?.model_path_exists && ttsCapability?.available);
  const localEngineReady = Boolean(ttsConfig) && (!isLocalEngine || (localPathConfigured ? localPathReady : Boolean(localCatalogModelInstalled && ttsCapability?.available)));
  const renderUsesLocalEngine = providerOverride ? providerOverride === "local_mlx" : isLocalEngine;
  const renderEngineReady = Boolean(ttsConfig) && (!renderUsesLocalEngine || (localPathConfigured ? localPathReady : Boolean(localCatalogModelInstalled && ttsCapability?.available)));
  const engineLabel = isLocalEngine
    ? `Local MLX · ${localPathConfigured ? "Custom local path" : currentModel?.display_name ?? shortRepoName(resolvedModel)}`
    : ttsConfig?.provider
      ? `${ttsConfig.provider} · ${ttsConfig.model || "default model"}`
      : "Loading engine...";
  const engineStatus = !ttsConfig
    ? "Loading"
    : !isLocalEngine
      ? "Cloud / remote"
      : localEngineReady
        ? "Ready"
        : localPathConfigured && !ttsCapability?.model_path_exists
          ? "Model path missing"
          : !localPathConfigured && !localCatalogModelInstalled
            ? "Model not installed"
            : "Runtime unavailable";

  const settings: VoiceRenderSettings = useMemo(
    () => ({
      voice_id: selectedVoiceId,
      voice_name: selectedVoice?.name ?? "",
      style_id: selectedStyleId,
      style_name: selectedStyle?.name ?? "",
      speed,
      language,
      audio_format: audioFormat,
      preview_text: effectivePreviewText,
    }),
    [audioFormat, effectivePreviewText, language, selectedStyle?.name, selectedStyleId, selectedVoice?.name, selectedVoiceId, speed],
  );

  const currentPreviewKey = useMemo(
    () => JSON.stringify({
      profile: selectedProfileId,
      text: effectivePreviewText,
      style: selectedStyleId,
      speed,
      language,
      audioFormat,
      providerOverride,
    }),
    [audioFormat, effectivePreviewText, language, providerOverride, selectedProfileId, selectedStyleId, speed],
  );
  const previewMatchesCurrentSelection = Boolean(previewPath && previewKey === currentPreviewKey);
  const canSavePreviewAsProfile = Boolean(previewMatchesCurrentSelection && !previewing);

  const selectedSession = projects.find((item) => item.session.session_id === selectedSessionId);

  const loadProject = async (sessionId: string, scriptId: string) => {
    if (!sessionId || !scriptId) return;
    const loaded = await bridge.showScript(sessionId, scriptId);
    const savedSettings = resolveProjectVoiceSettings(loaded);
    setSelectedVoiceId(savedSettings.voice_id);
    setSelectedStyleId(savedSettings.style_id);
    setSpeed(savedSettings.speed);
    setLanguage(savedSettings.language ?? "zh");
    setAudioFormat(savedSettings.audio_format ?? "wav");
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

  const refreshVoiceProfiles = async () => {
    setVoiceProfiles(await bridge.listVoiceProfiles());
  };

  useEffect(() => {
    void (async () => {
      try {
        const [catalog, loadedProjects, tts, modelStatus, capability, profiles] = await Promise.all([
          bridge.listVoicePresets(),
          bridge.listProjects(),
          bridge.showTTSConfig(),
          bridge.listModelsStatus(),
          bridge.getLocalTTSCapability(),
          bridge.listVoiceProfiles(),
        ]);
        setVoices(catalog.voices);
        setVoiceProfiles(profiles);
        setStyles(catalog.styles);
        setStandardPreviewText(catalog.standard_preview_text);
        setPreviewText(catalog.standard_preview_text);
        setProjects(loadedProjects);
        setTtsConfig(tts);
        setModels(modelStatus);
        setTtsCapability(capability);
        if (tts?.audio_format) setAudioFormat(tts.audio_format);
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
    if (!selectedProfileId) {
      setError("请先从音色库选择一个音色，再生成试听。");
      return;
    }
    try {
      setPreviewing(true);
      setError(null);
      setPreviewRequestState({
        operation: "render_voice_preview",
        phase: "running",
        progress_percent: 0,
        message: "Rendering voice preview...",
      });
      const result = await bridge.renderVoicePreview(settings, {
        onState: setPreviewRequestState,
        sessionId: selectedSessionId,
        scriptId: selectedScriptId,
        providerOverride,
        voiceProfileId: selectedProfileId,
      });
      setPreviewRequestState(result.request_state ?? null);
      setPreviewSrc(resolveAudioFileUrl(result.audio_path));
      setPreviewPath(result.audio_path);
      setPreviewKey(currentPreviewKey);
      setLastPreviewProvider(result.provider);
      setLastPreviewModel(result.model);
      setLastPreviewSettings(result.settings ?? settings);
      window.setTimeout(() => {
        void previewAudioRef.current?.play().catch(() => undefined);
      }, 100);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to render preview."));
      setPreviewRequestState(null);
    } finally {
      setPreviewing(false);
    }
  };

  const handleSaveVoiceProfile = async () => {
    if (!previewPath) {
      setError("请先生成并确认一条试音，再保存为我的音色。");
      return;
    }
    if (!previewMatchesCurrentSelection) {
      setError("当前试听已过期，请先用所选音色重新生成试听。");
      return;
    }
    const name = window.prompt("给这个音色起个名字", selectedVoice?.name ? `我的${selectedVoice.name}` : "我的音色");
    if (name === null) return;
    try {
      setError(null);
      const profile = await bridge.createVoiceProfile({
        name,
        audioPath: previewPath,
        referenceText: (lastPreviewSettings ?? settings).preview_text ?? "",
        provider: lastPreviewProvider || providerOverride || ttsConfig?.provider || "",
        model: lastPreviewModel || resolvedModel,
        language: (lastPreviewSettings ?? settings).language ?? "zh",
        audioFormat: (lastPreviewSettings ?? settings).audio_format ?? "wav",
        settings: lastPreviewSettings ?? settings,
      });
      await refreshVoiceProfiles();
      if (selectedSessionId && selectedScriptId) {
        const updated = await bridge.selectVoiceProfile(selectedSessionId, selectedScriptId, profile.voice_profile_id);
        setProject(updated);
      }
      setMessage("已保存到我的音色库，并设为当前脚本音色。");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to save voice profile."));
    }
  };

  const handleSelectVoiceProfile = async (profile: VoiceProfileRecord) => {
    if (!selectedSessionId || !selectedScriptId) {
      setError("请先选择 Session 和脚本，再选用音色。");
      return;
    }
    try {
      setError(null);
      const updated = await bridge.selectVoiceProfile(selectedSessionId, selectedScriptId, profile.voice_profile_id);
      setProject(updated);
      setSelectedVoiceId(profile.voice_id);
      setSelectedStyleId(profile.style_id);
      setSpeed(profile.speed);
      setLanguage(profile.language);
      setAudioFormat(profile.audio_format);
      setPreviewSrc("");
      setPreviewPath("");
      setPreviewKey("");
      setLastPreviewProvider("");
      setLastPreviewModel("");
      setLastPreviewSettings(null);
      setPreviewRequestState(null);
      await refreshVoiceProfiles();
      setMessage(`已选用「${profile.name}」，正式生成会以该音频作为参考声音。`);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to select voice profile."));
    }
  };

  const handleDeleteVoiceProfile = async (profile: VoiceProfileRecord) => {
    if (profile.source === "built_in") return;
    if (!window.confirm(`删除「${profile.name}」？已使用该音色的脚本会清除对应参考。`)) return;
    try {
      setError(null);
      await bridge.deleteVoiceProfile(profile.voice_profile_id);
      await refreshVoiceProfiles();
      if (selectedSessionId && selectedScriptId) {
        await loadProject(selectedSessionId, selectedScriptId);
      }
      setMessage("音色已删除。");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete voice profile."));
    }
  };

  const handleRenderTake = async () => {
    setError(null);
    setMessage(null);
    if (!selectedSessionId || !selectedScriptId) {
      setError("请先选择 Session 和脚本，再生成完整音频。");
      return;
    }
    if (!renderEngineReady) {
      setError("当前本地语音模型尚未准备好。请先在 Models Center 下载或选择可用模型，或在高级设置中临时切换到云端 TTS。");
      return;
    }
    if (!scriptText) {
      setError("当前脚本没有可生成的内容，请先选择包含正文的脚本。");
      return;
    }
    if (!selectedProfileId) {
      setError("请先从音色库选择一个音色，再生成完整音频。");
      return;
    }
    try {
      setRendering(true);
      const result = await bridge.renderAudio(selectedSessionId, {
        providerOverride,
        scriptId: selectedScriptId,
        voiceSettings: settings,
        requireVoiceProfile: renderUsesLocalEngine,
      });
      const state = result.request_state ?? {
        operation: "render_audio",
        phase: "running",
        progress_percent: 5,
        message: "Rendering audio...",
      };
      setRequestState(state);
      setProject(result.project);
      startPolling(result.task_id ?? `render_audio:${selectedSessionId}`);
      setMessage("已开始使用所选音色生成完整音频；完成后会自动成为 Script 页的默认音频。");
    } catch (err) {
      setRendering(false);
      setError(getErrorMessage(err, "Failed to render voice take."));
    }
  };

  const handleCancel = async () => {
    const state = await bridge.cancelTask(requestState?.task_id ?? `render_audio:${selectedSessionId}`);
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

  const handleDeletePreview = async () => {
    if (!previewPath) return;
    try {
      setError(null);
      await bridge.deleteArtifactAudio(previewPath);
      setPreviewSrc("");
      setPreviewPath("");
      setLastPreviewProvider("");
      setLastPreviewModel("");
      setLastPreviewSettings(null);
      setPreviewRequestState(null);
      if (selectedSessionId && selectedScriptId) {
        await loadProject(selectedSessionId, selectedScriptId);
      }
      setMessage("试音音频已删除。");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete preview audio."));
    }
  };

  const handleDeleteTake = async (take: AudioTakeRecord) => {
    try {
      setError(null);
      const updated = await bridge.deleteVoiceTake(selectedSessionId, take.take_id);
      setProject(updated);
      setMessage(take.take_id === finalTakeId ? "最终音频已删除。" : "候选 take 已删除。");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete voice take."));
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
              <p className="mt-2 text-sm text-secondary">从音色库选择固定音色，试听确认后用于完整播客生成。</p>
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

        <section className={cn("rounded-[24px] border p-4", localEngineReady ? "border-outline bg-surface-container-low/40" : "border-amber-500/30 bg-amber-500/10")}>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-secondary">Current engine</p>
              <p className="mt-1 text-sm font-semibold text-primary">{engineLabel}</p>
              <p className={cn("mt-1 text-xs", localEngineReady ? "text-secondary" : "text-amber-200")}>{engineStatus}</p>
            </div>
            <button
              type="button"
              onClick={() => navigate("/models")}
              className="rounded-2xl border border-outline bg-background px-4 py-2 text-sm font-medium text-primary hover:bg-surface-container"
            >
              Change model
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
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-primary">音色库</h2>
                  <p className="mt-1 text-xs text-secondary">
                    当前脚本的试听和完整生成都会使用所选音色的参考音频与参考文本。
                  </p>
                  {selectedProfile ? (
                    <p className="mt-2 text-xs font-medium text-accent-amber">当前选用：{selectedProfile.name}</p>
                  ) : null}
                </div>
                <button type="button" onClick={() => void refreshVoiceProfiles()} className="inline-flex items-center gap-2 rounded-2xl border border-outline px-3 py-2 text-xs font-medium text-secondary hover:text-primary">
                  <RefreshCw className="h-3.5 w-3.5" /> 刷新音色库
                </button>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {voiceProfiles.map((profile) => {
                  const isSelected = voiceReference?.voice_profile_id === profile.voice_profile_id;
                  return (
                    <div key={profile.voice_profile_id} className={cn("rounded-[22px] border p-4", isSelected ? "border-accent-amber bg-accent-amber/10" : "border-outline bg-background")}>
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-primary">{profile.name}</p>
                          <p className="mt-1 text-[11px] text-secondary">{profile.source === "built_in" ? "默认音色" : "我的音色"} · {profile.voice_name || profile.voice_id} / {profile.style_name || profile.style_id}</p>
                        </div>
                        {isSelected ? <CheckCircle2 className="h-4 w-4 text-accent-amber" /> : null}
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs leading-5 text-secondary">{profile.description || profile.preview_text}</p>
                      <audio controls src={resolveAudioFileUrl(profile.audio_path)} onError={handleAudioLoadError} className="mt-3 w-full" />
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void handleSelectVoiceProfile(profile)}
                          disabled={isSelected}
                          className="rounded-xl border border-outline px-3 py-2 text-xs font-medium text-primary disabled:opacity-50"
                        >
                          {isSelected ? "已选用" : "选用音色"}
                        </button>
                        {profile.source === "user_saved" ? (
                          <button type="button" onClick={() => void handleDeleteVoiceProfile(profile)} className="rounded-xl border border-red-500/25 px-3 py-2 text-xs font-medium text-red-200 hover:bg-red-500/10">
                            删除
                          </button>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="rounded-[28px] border border-outline bg-surface p-5">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-primary">试听设置</h2>
                  <p className="mt-2 text-lg font-semibold text-primary">
                    {selectedProfile?.name ?? "未选择音色"} · {selectedStyle?.name ?? "默认风格"} · {speed.toFixed(1)}x
                  </p>
                  <p className="mt-1 text-xs text-secondary">
                    {selectedProfile ? "将使用该音色的参考音频生成试听。" : "请先在音色库中选择一个音色。"}
                  </p>
                </div>
                <button type="button" onClick={() => setAdvancedOpen(true)} className="rounded-2xl border border-outline bg-background px-4 py-2 text-sm font-medium text-primary hover:bg-surface-container">
                  Customize
                </button>
              </div>
            </section>

            {advancedOpen ? <section className="rounded-[28px] border border-outline bg-surface p-5">
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
            </section> : null}

            {advancedOpen ? <section className="rounded-[28px] border border-outline bg-surface p-5">
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
            </section> : null}

            <section className="rounded-[28px] border border-outline bg-surface p-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-primary">音色试听</h2>
                  <p className="mt-1 text-xs text-secondary">
                    用当前选中的音色生成一段短试听，确认后再生成完整播客音频。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handlePreview()}
                  disabled={previewing || !selectedVoice || !selectedStyle || !renderEngineReady || !selectedProfileId}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl bg-accent-amber px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
                >
                  {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  生成试听
                </button>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setPreviewTextMode("standard")}
                  className={cn("rounded-full border px-3 py-1.5 text-xs font-medium", previewTextMode === "standard" ? "border-accent-amber bg-accent-amber/10 text-accent-amber" : "border-outline text-secondary hover:text-primary")}
                >
                  标准试音句
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewTextMode("script_opening")}
                  disabled={!scriptOpening}
                  className={cn("rounded-full border px-3 py-1.5 text-xs font-medium disabled:opacity-40", previewTextMode === "script_opening" ? "border-accent-amber bg-accent-amber/10 text-accent-amber" : "border-outline text-secondary hover:text-primary")}
                >
                  使用脚本开头
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewTextMode("custom")}
                  className={cn("rounded-full border px-3 py-1.5 text-xs font-medium", previewTextMode === "custom" ? "border-accent-amber bg-accent-amber/10 text-accent-amber" : "border-outline text-secondary hover:text-primary")}
                >
                  自定义文本
                </button>
              </div>
              <textarea
                value={previewText}
                onChange={(event) => {
                  setPreviewTextMode("custom");
                  setPreviewText(event.target.value);
                }}
                rows={3}
                placeholder="输入一句你想用来比较音色与风格的试音文本"
                className={cn("mt-4 w-full resize-none rounded-2xl border border-outline bg-background px-4 py-3 text-sm text-primary outline-none focus:border-accent-amber/40", !advancedOpen && previewTextMode !== "custom" && "hidden")}
              />
              <p className="mt-2 text-[11px] text-secondary">
                当前试音文本：{effectivePreviewText ? `${effectivePreviewText.slice(0, 60)}${effectivePreviewText.length > 60 ? "…" : ""}` : "系统标准试音句"}
              </p>
              {!selectedProfileId ? (
                <p className="mt-1 text-[11px] text-amber-200">请先从音色库选择一个音色。</p>
              ) : null}
              {previewRequestState && previewRequestState.phase !== "succeeded" ? (
                <div className="mt-3 rounded-2xl border border-outline bg-background px-4 py-3 text-sm text-secondary">
                  {Math.round(previewRequestState.progress_percent)}% · {previewRequestState.message}
                </div>
              ) : null}
              {previewSrc && previewMatchesCurrentSelection ? (
                <div className="mt-4 space-y-2">
                  <audio ref={previewAudioRef} controls src={previewSrc} onError={handleAudioLoadError} className="w-full" />
                  <div className="flex flex-wrap gap-2">
                    {advancedOpen ? (
                      <button
                        type="button"
                        onClick={() => void handleSaveVoiceProfile()}
                        disabled={!canSavePreviewAsProfile}
                        className="inline-flex items-center gap-1 rounded-xl border border-outline px-3 py-2 text-xs font-semibold text-primary hover:bg-surface-container disabled:opacity-50"
                      >
                        保存为我的音色
                      </button>
                    ) : null}
                    <button type="button" onClick={() => void handleDeletePreview()} className="inline-flex items-center gap-1 rounded-xl border border-red-500/25 px-3 py-2 text-xs font-medium text-red-200 hover:bg-red-500/10">
                      <Trash2 className="h-3.5 w-3.5" /> 删除试音音频
                    </button>
                  </div>
                </div>
              ) : null}
              {selectedProfile ? (
                <div className="mt-4 rounded-2xl border border-emerald-500/25 bg-emerald-500/10 p-3 text-xs text-emerald-100">
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="mt-0.5 h-4 w-4" />
                    <p>已选择「{selectedProfile.name}」。试听和完整生成都会使用这个音色 profile。</p>
                  </div>
                </div>
              ) : null}
            </section>
          </div>

          <aside className="space-y-5">
            <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
              <button type="button" onClick={() => setAdvancedOpen(!advancedOpen)} className="flex w-full items-center justify-between gap-3 text-left">
                <span>
                  <span className="flex items-center gap-2 text-sm font-semibold text-primary"><SlidersHorizontal className="h-4 w-4 text-accent-amber" /> Advanced voice controls</span>
                  <span className="mt-1 block text-xs text-secondary">展开后可调整音色、表达、语言、输出格式和本次渲染引擎。全局模型在 Models Center 管理。</span>
                </span>
                <ChevronDown className={cn("h-4 w-4 text-secondary transition-transform", advancedOpen && "rotate-180")} />
              </button>
              {advancedOpen ? (
                <div className="mt-4 grid gap-3">
                  <div className="rounded-2xl border border-outline bg-background px-3 py-2">
                    <p className="text-xs text-secondary">Global model</p>
                    <p className="mt-1 text-sm font-medium text-primary">{engineLabel}</p>
                    <button type="button" onClick={() => navigate("/models")} className="mt-2 text-xs font-medium text-accent-amber hover:underline">Change in Models Center</button>
                  </div>
                  <label className="text-xs text-secondary">本次渲染引擎
                    <select value={providerOverride} onChange={(event) => setProviderOverride(event.target.value)} className="mt-1 w-full rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary">
                      <option value="">Use global engine</option>
                      <option value="local_mlx">Force Local MLX</option>
                      <option value="openai_compatible">Force cloud TTS</option>
                      <option value="mock_remote">Mock remote</option>
                    </select>
                  </label>
                  <label className="text-xs text-secondary">语言
                    <input value={language} onChange={(event) => setLanguage(event.target.value)} className="mt-1 w-full rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary" />
                  </label>
                  <label className="text-xs text-secondary">输出格式
                    <input value={audioFormat} onChange={(event) => setAudioFormat(event.target.value)} className="mt-1 w-full rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary" />
                    <p className="mt-1 text-[11px] text-secondary">
                      这会保存为当前脚本的 Voice Studio 默认配置；Script 页生成音频会使用同一配置。MP4 指 audio-only 容器，不含视频画面。
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
              {renderUsesLocalEngine ? (
                <div className={cn("mt-4 rounded-2xl border p-3 text-xs", selectedProfile ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100" : "border-amber-500/25 bg-amber-500/10 text-amber-100")}>
                  {selectedProfile ? (
                    <span>完整生成将使用「{selectedProfile.name}」的参考音频和参考文本。</span>
                  ) : (
                    <span>请先从音色库选择一个音色，完整生成才会开始。</span>
                  )}
                </div>
              ) : null}
              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  onClick={() => void handleRenderTake()}
                  disabled={rendering || !renderEngineReady || !selectedProfileId}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl bg-accent-amber px-4 py-3 text-sm font-semibold text-black disabled:opacity-50"
                >
                  {rendering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                  生成完整音频
                </button>
                {rendering ? (
                  <button type="button" onClick={() => void handleCancel()} className="rounded-2xl border border-outline px-4 py-3 text-sm text-primary">取消</button>
                ) : null}
              </div>
              {!renderEngineReady ? (
                <button type="button" onClick={() => navigate("/models")} className="mt-3 w-full rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm font-medium text-amber-100 hover:bg-amber-500/15">
                  Open Models Center to prepare a voice model
                </button>
              ) : null}
              {error ? <p className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-200">{error}</p> : null}
              {message ? <p className="mt-4 rounded-2xl border border-accent-amber/20 bg-accent-amber/10 p-3 text-sm text-accent-amber">{message}</p> : null}
            </section>

            {advancedOpen ? <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-primary">历史 take</h2>
                  <p className="mt-1 text-xs text-secondary">兼容旧 Voice Studio take；新的主流程直接生成完整音频。</p>
                </div>
                <FileAudio className="h-5 w-5 text-accent-amber" />
              </div>
              <div className="space-y-3">
                {takes.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-outline p-5 text-center text-sm text-secondary">还没有旧 take。</div>
                ) : takes.map((take) => {
                  const src = resolveAudioFileUrl(take.audio_path);
                  return (
                    <div key={take.take_id} className="rounded-[22px] border border-outline bg-background p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-primary">{takeStatus(take, finalTakeId)}</p>
                          <p className="mt-1 text-xs text-secondary">{take.voice_name} / {take.style_name} / {take.speed.toFixed(1)}x</p>
                          <p className="mt-1 text-[11px] text-secondary">{take.provider} · {take.model || "default model"} · {take.audio_format}</p>
                          <p className="mt-1 text-[11px] text-secondary">{new Date(take.created_at).toLocaleString()}</p>
                        </div>
                        <button type="button" onClick={() => void revealInFinder(take.audio_path)} className="rounded-xl border border-outline p-2 text-secondary hover:text-primary">
                          <FolderOpen className="h-4 w-4" />
                        </button>
                      </div>
                      <audio controls src={src} onError={handleAudioLoadError} className="mt-3 w-full" />
                      <div className="mt-3 grid grid-cols-3 gap-2">
                        <button type="button" onClick={() => void handleSetFinal(take)} disabled={take.take_id === finalTakeId} className="rounded-xl border border-outline px-3 py-2 text-xs font-medium text-primary disabled:opacity-50">
                          设为最终版本
                        </button>
                        <button type="button" onClick={() => handleDownload(take)} className="inline-flex items-center justify-center gap-1 rounded-xl border border-outline px-3 py-2 text-xs font-medium text-primary">
                          <Download className="h-3.5 w-3.5" /> 下载
                        </button>
                        <button type="button" onClick={() => void handleDeleteTake(take)} className="inline-flex items-center justify-center gap-1 rounded-xl border border-red-500/25 px-3 py-2 text-xs font-medium text-red-200 hover:bg-red-500/10">
                          <Trash2 className="h-3.5 w-3.5" /> 删除
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <button type="button" onClick={() => selectedSessionId && selectedScriptId && void loadProject(selectedSessionId, selectedScriptId)} className="mt-3 inline-flex items-center gap-2 text-xs text-secondary hover:text-primary">
                <RefreshCw className="h-3.5 w-3.5" /> 刷新历史 take
              </button>
            </section> : null}
          </aside>
        </div>
      </div>
    </motion.div>
  );
}
