import { motion } from "framer-motion";
import { CheckCircle2, Loader2, Mic, RefreshCw, Trash2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { resolveAudioFileUrl } from "../lib/audioFile";
import { useBridge } from "../lib/BridgeContext";
import { getErrorMessage } from "../lib/requestState";
import { cn } from "../lib/utils";
import { filterActiveVoiceProfiles, resolveProjectVoiceSettings } from "../lib/voiceSettings";
import type {
  ModelStatus,
  RequestState,
  SessionProject,
  TTSCapability,
  TTSProviderConfig,
  VoicePreset,
  VoiceProfileRecord,
  VoiceRenderSettings,
  VoiceStylePreset,
} from "../types";

const DEFAULT_QWEN3_TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit";
type PreviewTextMode = "standard" | "script_opening" | "custom";

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
  const previewRequestTokenRef = useRef(0);
  const previewContextRef = useRef({ previewKey: "", profileId: "", scriptId: "", sessionId: "" });
  const projectLoadTokenRef = useRef(0);
  const projectLoadContextRef = useRef({ scriptBoundMode: false, scriptId: "", sessionId: "" });
  const lastCurrentPreviewKeyRef = useRef("");

  const [projects, setProjects] = useState<SessionProject[]>([]);
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
  const selectedSessionId = routeSessionId ?? "";
  const selectedScriptId = routeScriptId ?? "";
  const [selectedVoiceId, setSelectedVoiceId] = useState("warm_narrator");
  const [selectedStyleId, setSelectedStyleId] = useState("natural");
  const [speed, setSpeed] = useState(1.0);
  const [language, setLanguage] = useState("zh");
  const [audioFormat, setAudioFormat] = useState("wav");
  const providerOverride = "";
  const [previewSrc, setPreviewSrc] = useState("");
  const [previewPath, setPreviewPath] = useState("");
  const [lastPreviewProvider, setLastPreviewProvider] = useState("");
  const [lastPreviewModel, setLastPreviewModel] = useState("");
  const [lastPreviewSettings, setLastPreviewSettings] = useState<VoiceRenderSettings | null>(null);
  const [previewKey, setPreviewKey] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [previewRequestState, setPreviewRequestState] = useState<RequestState | null>(null);
  const [newProfileName, setNewProfileName] = useState("");
  const [newProfileAudioPath, setNewProfileAudioPath] = useState("");
  const [newProfileReferenceText, setNewProfileReferenceText] = useState("");
  const [creatingProfile, setCreatingProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileAudioErrors, setProfileAudioErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const selectedSession = projects.find((item) => item.session.session_id === selectedSessionId);
  const scriptBoundMode = Boolean(routeSessionId && routeScriptId);
  const canApplyProfileToScript = Boolean(selectedSessionId && selectedScriptId);
  const scriptTitle = (project?.script as { title?: string } | undefined)?.title || selectedSession?.session.topic || "当前脚本";
  const scriptText = scriptBoundMode ? project?.script?.final?.trim() || project?.script?.draft?.trim() || "" : "";
  const scriptOpening = scriptOpeningText(scriptText);
  const effectivePreviewText =
    previewTextMode === "script_opening"
      ? scriptOpening || standardPreviewText
      : previewTextMode === "standard"
        ? standardPreviewText
        : previewText;
  const voiceReference = scriptBoundMode ? project?.artifact?.voice_reference : undefined;
  const activeVoiceProfiles = useMemo(() => filterActiveVoiceProfiles(voiceProfiles), [voiceProfiles]);
  const selectedProfile = voiceReference?.voice_profile_id
    ? activeVoiceProfiles.find((profile) => profile.voice_profile_id === voiceReference.voice_profile_id)
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
  const previewUsesLocalEngine = providerOverride ? providerOverride === "local_mlx" : isLocalEngine;
  const previewEngineReady = Boolean(ttsConfig) && (!previewUsesLocalEngine || (localPathConfigured ? localPathReady : Boolean(localCatalogModelInstalled && ttsCapability?.available)));
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
      voiceId: selectedVoiceId,
      voiceName: selectedVoice?.name ?? "",
      text: effectivePreviewText,
      style: selectedStyleId,
      speed,
      language,
      audioFormat,
      providerOverride,
    }),
    [audioFormat, effectivePreviewText, language, providerOverride, selectedProfileId, selectedStyleId, selectedVoice?.name, selectedVoiceId, speed],
  );
  previewContextRef.current = {
    previewKey: currentPreviewKey,
    profileId: selectedProfileId,
    scriptId: selectedScriptId,
    sessionId: selectedSessionId,
  };
  projectLoadContextRef.current = {
    scriptBoundMode,
    scriptId: selectedScriptId,
    sessionId: selectedSessionId,
  };
  const previewMatchesCurrentSelection = Boolean(previewPath && previewKey === currentPreviewKey);
  const clearPreviewState = useCallback(() => {
    previewRequestTokenRef.current += 1;
    setPreviewing(false);
    setPreviewSrc("");
    setPreviewPath("");
    setPreviewKey("");
    setLastPreviewProvider("");
    setLastPreviewModel("");
    setLastPreviewSettings(null);
    setPreviewRequestState(null);
  }, []);

  const loadProject = async (sessionId: string, scriptId: string) => {
    if (!sessionId || !scriptId) return;
    const requestToken = projectLoadTokenRef.current + 1;
    projectLoadTokenRef.current = requestToken;
    const loaded = await bridge.showScript(sessionId, scriptId);
    const currentContext = projectLoadContextRef.current;
    if (
      projectLoadTokenRef.current !== requestToken ||
      !currentContext.scriptBoundMode ||
      currentContext.sessionId !== sessionId ||
      currentContext.scriptId !== scriptId
    ) {
      return;
    }
    const savedSettings = resolveProjectVoiceSettings(loaded);
    setSelectedVoiceId(savedSettings.voice_id);
    setSelectedStyleId(savedSettings.style_id);
    setSpeed(savedSettings.speed);
    setLanguage(savedSettings.language ?? "zh");
    setAudioFormat(savedSettings.audio_format ?? "wav");
    setProject(loaded);
  };

  const refreshVoiceProfiles = async () => {
    setProfileAudioErrors({});
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
    clearPreviewState();
    if (!scriptBoundMode || !selectedSessionId || !selectedScriptId) {
      projectLoadTokenRef.current += 1;
      setProject(null);
      setSelectedVoiceId("warm_narrator");
      setSelectedStyleId("natural");
      setSpeed(1.0);
      setLanguage("zh");
      setAudioFormat(ttsConfig?.audio_format ?? "wav");
      setError(null);
      setMessage(null);
      return;
    }
    void loadProject(selectedSessionId, selectedScriptId).catch((err) => setError(getErrorMessage(err, "Failed to load script.")));
  }, [clearPreviewState, scriptBoundMode, selectedScriptId, selectedSessionId, ttsConfig?.audio_format]);

  useEffect(() => {
    if (!lastCurrentPreviewKeyRef.current) {
      lastCurrentPreviewKeyRef.current = currentPreviewKey;
      return;
    }
    if (lastCurrentPreviewKeyRef.current === currentPreviewKey) return;
    lastCurrentPreviewKeyRef.current = currentPreviewKey;
    if (previewKey && previewKey === currentPreviewKey) return;
    if (previewSrc || previewPath || previewRequestState) clearPreviewState();
  }, [clearPreviewState, currentPreviewKey, previewKey, previewPath, previewRequestState, previewSrc]);

  const handlePreview = async () => {
    if (!selectedProfileId) {
      setError("请先从音色库选择一个音色，再生成试听。");
      return;
    }
    const requestToken = previewRequestTokenRef.current + 1;
    previewRequestTokenRef.current = requestToken;
    const requestSessionId = selectedSessionId;
    const requestScriptId = selectedScriptId;
    const requestProfileId = selectedProfileId;
    const requestPreviewKey = currentPreviewKey;
    const requestSettings = settings;
    const isCurrentPreviewRequest = () => {
      const context = previewContextRef.current;
      return (
        previewRequestTokenRef.current === requestToken &&
        context.sessionId === requestSessionId &&
        context.scriptId === requestScriptId &&
        context.profileId === requestProfileId &&
        context.previewKey === requestPreviewKey
      );
    };
    try {
      setPreviewing(true);
      setError(null);
      setPreviewRequestState({
        operation: "render_voice_preview",
        phase: "running",
        progress_percent: 0,
        message: "Rendering voice preview...",
      });
      const result = await bridge.renderVoicePreview(requestSettings, {
        onState: (state) => {
          if (isCurrentPreviewRequest()) setPreviewRequestState(state);
        },
        sessionId: requestSessionId,
        scriptId: requestScriptId,
        providerOverride,
        voiceProfileId: requestProfileId,
      });
      if (!isCurrentPreviewRequest()) return;
      setPreviewRequestState(result.request_state ?? null);
      setPreviewSrc(resolveAudioFileUrl(result.audio_path));
      setPreviewPath(result.audio_path);
      setPreviewKey(requestPreviewKey);
      setLastPreviewProvider(result.provider);
      setLastPreviewModel(result.model);
      setLastPreviewSettings(result.settings ?? requestSettings);
      window.setTimeout(() => {
        if (!isCurrentPreviewRequest()) return;
        void previewAudioRef.current?.play().catch(() => undefined);
      }, 100);
    } catch (err) {
      if (!isCurrentPreviewRequest()) return;
      setError(getErrorMessage(err, "Failed to render preview."));
      setPreviewRequestState(null);
    } finally {
      if (previewRequestTokenRef.current === requestToken) setPreviewing(false);
    }
  };

  const handleCreateVoiceProfile = async () => {
    const name = newProfileName.trim();
    const referenceAudioPath = newProfileAudioPath.trim();
    const referenceText = newProfileReferenceText.trim();
    if (!name) {
      setError("请先填写音色名称。");
      return;
    }
    if (!referenceAudioPath) {
      setError("请先填写参考音频文件路径。");
      return;
    }
    if (!referenceText) {
      setError("请填写参考音频中实际朗读的文本。");
      return;
    }
    try {
      setCreatingProfile(true);
      setError(null);
      const profile = await bridge.createVoiceProfile({
        name,
        referenceAudioPath,
        referenceText,
        provider: ttsConfig?.provider || "local_mlx",
        model: resolvedModel,
        language,
        audioFormat,
        settings: { ...settings, preview_text: referenceText },
      });
      await refreshVoiceProfiles();
      setNewProfileName("");
      setNewProfileAudioPath("");
      setNewProfileReferenceText("");
      if (canApplyProfileToScript) {
        const updated = await bridge.selectVoiceProfile(selectedSessionId, selectedScriptId, profile.voice_profile_id);
        setProject(updated);
        setSelectedVoiceId(profile.voice_id);
        setSelectedStyleId(profile.style_id);
        setSpeed(profile.speed);
        setLanguage(profile.language);
        setAudioFormat(profile.audio_format);
        setMessage(`已创建「${profile.name}」并用于当前脚本。返回 Script 页后可以生成完整音频。`);
      } else {
        setMessage(`已创建「${profile.name}」。打开脚本后可以选用这个音色。`);
      }
    } catch (err) {
      setError(getErrorMessage(err, "Failed to create voice profile."));
    } finally {
      setCreatingProfile(false);
    }
  };

  const handleSelectVoiceProfile = async (profile: VoiceProfileRecord) => {
    if (!canApplyProfileToScript) {
      setError("请先从 Script 页面打开 Voice Studio，再把音色应用到具体脚本。");
      return;
    }
    try {
      setError(null);
      clearPreviewState();
      const updated = await bridge.selectVoiceProfile(selectedSessionId, selectedScriptId, profile.voice_profile_id);
      setProject(updated);
      setSelectedVoiceId(profile.voice_id);
      setSelectedStyleId(profile.style_id);
      setSpeed(profile.speed);
      setLanguage(profile.language);
      setAudioFormat(profile.audio_format);
      await refreshVoiceProfiles();
      setMessage(`已为当前脚本选用「${profile.name}」。返回 Script 页后可以生成完整音频。`);
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

  const handleDeletePreview = async () => {
    if (!previewPath) return;
    try {
      setError(null);
      await bridge.deleteArtifactAudio(previewPath);
      clearPreviewState();
      if (selectedSessionId && selectedScriptId) {
        await loadProject(selectedSessionId, selectedScriptId);
      }
      setMessage("试音音频已删除。");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete preview audio."));
    }
  };

  const handleProfileAudioLoadError = (profileId: string) => {
    setProfileAudioErrors((current) => ({
      ...current,
      [profileId]: "无法加载参考音频。文件可能已移动或删除。",
    }));
  };

  const handlePreviewAudioLoadError = () => {
    setError("无法加载试音音频。文件可能已移动或删除，请重新生成试听。");
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="h-full overflow-y-auto px-5 py-5 lg:px-8">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-5">
        <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-amber">Voice Studio</p>
              <h1 className="mt-2 font-headline text-2xl font-semibold text-primary">音色工坊</h1>
              <p className="mt-2 max-w-2xl text-sm text-secondary">
                {scriptBoundMode
                  ? `为「${scriptTitle}」选择或创建一个可复用音色。完整音频生成和成品管理会在 Script 页完成。`
                  : "管理可复用音色库。打开某个脚本后，可以把这里的音色应用到那一集播客。"}
              </p>
            </div>
            {scriptBoundMode ? (
              <button
                type="button"
                onClick={() => selectedSessionId && selectedScriptId && navigate(`/script/${selectedSessionId}/${selectedScriptId}`)}
                className="rounded-2xl border border-outline bg-surface-container-low px-4 py-2 text-sm font-medium text-primary hover:bg-surface-container"
              >
                返回 Script
              </button>
            ) : null}
          </div>
        </section>

        {error ? <p className="rounded-2xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-200">{error}</p> : null}
        {message ? <p className="rounded-2xl border border-accent-amber/20 bg-accent-amber/10 p-3 text-sm text-accent-amber">{message}</p> : null}

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="space-y-5">
            <section className="rounded-[28px] border border-outline bg-surface p-5">
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-primary">音色库</h2>
                  <p className="mt-1 text-xs text-secondary">
                    {scriptBoundMode
                      ? "当前脚本的试听会使用所选音色的参考音频与参考文本；Script 页面生成音频时也会使用该 profile。"
                      : "这里是可复用音色资产库。可以播放参考音频、删除我的音色；打开某个脚本后才能把音色应用到具体播客。"}
                  </p>
                  {scriptBoundMode && selectedProfile ? (
                    <p className="mt-2 text-xs font-medium text-accent-amber">当前选用：{selectedProfile.name}</p>
                  ) : null}
                </div>
                <button type="button" onClick={() => void refreshVoiceProfiles()} className="inline-flex items-center gap-2 rounded-2xl border border-outline px-3 py-2 text-xs font-medium text-secondary hover:text-primary">
                  <RefreshCw className="h-3.5 w-3.5" /> 刷新音色库
                </button>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {activeVoiceProfiles.map((profile) => {
                  const isSelected = voiceReference?.voice_profile_id === profile.voice_profile_id;
                  const profileAudioError = profileAudioErrors[profile.voice_profile_id];
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
                      <audio
                        controls
                        src={resolveAudioFileUrl(profile.audio_path)}
                        onError={() => handleProfileAudioLoadError(profile.voice_profile_id)}
                        className="mt-3 w-full"
                      />
                      {profileAudioError ? <p className="mt-2 text-xs text-red-200">{profileAudioError}</p> : null}
                      <div className="mt-3 flex flex-wrap gap-2">
                        {scriptBoundMode ? (
                          <button
                            type="button"
                            onClick={() => void handleSelectVoiceProfile(profile)}
                            disabled={isSelected}
                            className="rounded-xl border border-outline px-3 py-2 text-xs font-medium text-primary disabled:opacity-50"
                          >
                            {isSelected ? "已用于当前脚本" : "用于当前脚本"}
                          </button>
                        ) : (
                          <span className="rounded-xl border border-outline px-3 py-2 text-xs text-secondary">
                            打开脚本后可选用
                          </span>
                        )}
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

            {scriptBoundMode ? (
              <>
                <section className="rounded-[28px] border border-outline bg-surface p-5">
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <h2 className="text-sm font-semibold text-primary">试听设置</h2>
                      <p className="mt-2 text-lg font-semibold text-primary">
                        {selectedProfile?.name ?? "未选择音色"} · {selectedStyle?.name ?? "默认风格"} · {speed.toFixed(1)}x
                      </p>
                      <p className="mt-1 text-xs text-secondary">
                        {selectedProfile ? "将使用该音色的参考音频生成试听。" : "请先为当前脚本选用一个音色。"}
                      </p>
                    </div>
                  </div>
                </section>

                <section className="rounded-[28px] border border-outline bg-surface p-5">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="text-sm font-semibold text-primary">音色试听</h2>
                      <p className="mt-1 text-xs text-secondary">
                        用当前脚本选用的音色生成一段短试听；完整音频仍在 Script 页面生成。
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handlePreview()}
                      disabled={
                        previewing ||
                        !selectedVoice ||
                        !selectedStyle ||
                        !selectedProfileId ||
                        !previewEngineReady
                      }
                      className="inline-flex items-center justify-center gap-2 rounded-2xl bg-accent-amber px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
                    >
                      {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
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
                    className={cn("mt-4 w-full resize-none rounded-2xl border border-outline bg-background px-4 py-3 text-sm text-primary outline-none focus:border-accent-amber/40", previewTextMode !== "custom" && "hidden")}
                  />
                  <p className="mt-2 text-[11px] text-secondary">
                    当前试音文本：{effectivePreviewText ? `${effectivePreviewText.slice(0, 60)}${effectivePreviewText.length > 60 ? "…" : ""}` : "系统标准试音句"}
                  </p>
                  {!selectedProfileId ? (
                    <p className="mt-1 text-[11px] text-amber-200">请先为当前脚本选用一个音色。</p>
                  ) : null}
                  {previewRequestState && previewRequestState.phase !== "succeeded" ? (
                    <div className="mt-3 rounded-2xl border border-outline bg-background px-4 py-3 text-sm text-secondary">
                      {Math.round(previewRequestState.progress_percent)}% · {previewRequestState.message}
                    </div>
                  ) : null}
                  {previewSrc && previewMatchesCurrentSelection ? (
                    <div className="mt-4 space-y-2">
                      <audio ref={previewAudioRef} controls src={previewSrc} onError={handlePreviewAudioLoadError} className="w-full" />
                      <div className="flex flex-wrap gap-2">
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
                        <p>已选择「{selectedProfile.name}」。试听会使用这个音色 profile，Script 页面生成音频时也会引用它。</p>
                      </div>
                    </div>
                  ) : null}
                </section>
              </>
            ) : null}
          </div>

          <aside className="space-y-5">
            <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-primary">当前语音引擎</h2>
                  <p className="mt-1 text-xs text-secondary">{engineLabel}</p>
                  <p className={cn("mt-1 text-xs", localEngineReady ? "text-secondary" : "text-amber-200")}>{engineStatus}</p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate("/models")}
                  className="rounded-2xl border border-outline px-3 py-2 text-xs font-medium text-primary hover:bg-surface-container"
                >
                  Change model
                </button>
              </div>
            </section>

            <section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
              <div>
                <h2 className="text-sm font-semibold text-primary">创建我的音色</h2>
                <p className="mt-1 text-xs leading-5 text-secondary">
                  使用一段参考音频和它实际朗读的文本创建可复用 voice profile。
                </p>
              </div>
              <div className="mt-4 grid gap-3">
                <label className="text-xs text-secondary">
                  音色名称
                  <input
                    value={newProfileName}
                    onChange={(event) => setNewProfileName(event.target.value)}
                    className="mt-1 w-full rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary outline-none focus:border-accent-amber/40"
                    placeholder="例如：我的知识讲述音色"
                  />
                </label>
                <label className="text-xs text-secondary">
                  参考音频路径
                  <input
                    value={newProfileAudioPath}
                    onChange={(event) => setNewProfileAudioPath(event.target.value)}
                    className="mt-1 w-full rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary outline-none focus:border-accent-amber/40"
                    placeholder="/Users/.../reference.wav"
                  />
                </label>
                <label className="text-xs text-secondary">
                  参考音频文本
                  <textarea
                    value={newProfileReferenceText}
                    onChange={(event) => setNewProfileReferenceText(event.target.value)}
                    rows={4}
                    className="mt-1 w-full resize-none rounded-2xl border border-outline bg-background px-3 py-2 text-sm text-primary outline-none focus:border-accent-amber/40"
                    placeholder="逐字填写参考音频里实际说出的内容"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void handleCreateVoiceProfile()}
                  disabled={creatingProfile}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl bg-accent-amber px-4 py-3 text-sm font-semibold text-black disabled:opacity-50"
                >
                  {creatingProfile ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
                  {scriptBoundMode ? "创建并用于当前脚本" : "创建音色"}
                </button>
              </div>
            </section>
          </aside>
        </div>
      </div>
    </motion.div>
  );
}
