import { motion } from "framer-motion";
import { CheckCircle2, FileAudio, Loader2, Mic, Pencil, RefreshCw, Square, Trash2, Upload, Wand2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { resolveAudioFileUrl } from "../lib/audioFile";
import { useBridge } from "../lib/BridgeContext";
import { AudioPlayer } from "../components/AudioPlayer";
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
type ProfileAudioSource = "upload" | "microphone" | "system";
type ProfileDialogMode = "create" | "edit";

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

function profileSampleAudioFormat(fileName: string, file: File | Blob | null): string {
  const extension = fileName.split(".").pop()?.trim().toLowerCase();
  if (extension) return extension;
  if (file?.type.includes("webm")) return "webm";
  if (file?.type.includes("mp4")) return "mp4";
  if (file?.type.includes("mpeg")) return "mp3";
  if (file?.type.includes("ogg")) return "ogg";
  return "wav";
}

export function VoiceStudioPage() {
  const { sessionId: routeSessionId, scriptId: routeScriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const bridge = useBridge();
  const navigate = useNavigate();
  const previewAudioRef = useRef<HTMLAudioElement>(null);
  const profileFileInputRef = useRef<HTMLInputElement>(null);
  const profileRecorderRef = useRef<MediaRecorder | null>(null);
  const profileRecordingChunksRef = useRef<Blob[]>([]);
  const profileRecordingStreamRef = useRef<MediaStream | null>(null);
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
  const [previewKey, setPreviewKey] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [previewRequestState, setPreviewRequestState] = useState<RequestState | null>(null);
  const [profileDialogMode, setProfileDialogMode] = useState<ProfileDialogMode | null>(null);
  const [editingProfileId, setEditingProfileId] = useState("");
  const [existingProfileAudioUrl, setExistingProfileAudioUrl] = useState("");
  const [profileAudioSource, setProfileAudioSource] = useState<ProfileAudioSource>("upload");
  const [newProfileName, setNewProfileName] = useState("");
  const [newProfileAudioFile, setNewProfileAudioFile] = useState<File | Blob | null>(null);
  const [newProfileAudioFileName, setNewProfileAudioFileName] = useState("");
  const [newProfileAudioPreviewUrl, setNewProfileAudioPreviewUrl] = useState("");
  const [newProfileReferenceText, setNewProfileReferenceText] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [recordingProfileSample, setRecordingProfileSample] = useState(false);
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
    setPreviewRequestState(null);
  }, []);

  const stopProfileRecordingStream = useCallback(() => {
    profileRecordingStreamRef.current?.getTracks().forEach((track) => track.stop());
    profileRecordingStreamRef.current = null;
  }, []);

  const setProfileAudioSample = useCallback((file: File | Blob, fileName: string) => {
    setNewProfileAudioFile(file);
    setNewProfileAudioFileName(fileName);
    setNewProfileAudioPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return URL.createObjectURL(file);
    });
  }, []);

  const resetProfileDialog = useCallback(() => {
    setProfileDialogMode(null);
    setEditingProfileId("");
    setProfileAudioSource("upload");
    setNewProfileName("");
    setNewProfileAudioFile(null);
    setNewProfileAudioFileName("");
    setNewProfileAudioPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return "";
    });
    setExistingProfileAudioUrl("");
    setNewProfileReferenceText("");
    setRecordingProfileSample(false);
    profileRecordingChunksRef.current = [];
    profileRecorderRef.current = null;
    stopProfileRecordingStream();
  }, [stopProfileRecordingStream]);

  const openCreateProfileDialog = useCallback(() => {
    resetProfileDialog();
    setProfileDialogMode("create");
  }, [resetProfileDialog]);

  const openEditProfileDialog = useCallback((profile: VoiceProfileRecord) => {
    resetProfileDialog();
    setProfileDialogMode("edit");
    setEditingProfileId(profile.voice_profile_id);
    setNewProfileName(profile.name);
    setNewProfileReferenceText(profile.preview_text || profile.reference_text || "");
    setExistingProfileAudioUrl(resolveAudioFileUrl(profile.audio_path));
  }, [resetProfileDialog]);

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

  useEffect(
    () => () => {
      if (newProfileAudioPreviewUrl) URL.revokeObjectURL(newProfileAudioPreviewUrl);
      stopProfileRecordingStream();
    },
    [newProfileAudioPreviewUrl, stopProfileRecordingStream],
  );

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

  const handleProfileFileSelected = (file: File | null) => {
    if (!file) return;
    if (!file.type.startsWith("audio/") && !/\.(wav|mp3|m4a|mp4|aac|flac|webm|ogg)$/i.test(file.name)) {
      setError("请选择 wav、mp3、m4a、mp4、aac、flac、webm 或 ogg 音频文件。");
      return;
    }
    setError(null);
    setProfileAudioSample(file, file.name);
  };

  const handleStartProfileRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("当前环境不支持麦克风录音，请改用上传音频。");
      return;
    }
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      profileRecordingStreamRef.current = stream;
      profileRecordingChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      profileRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) profileRecordingChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(profileRecordingChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        profileRecordingChunksRef.current = [];
        stopProfileRecordingStream();
        setRecordingProfileSample(false);
        if (blob.size > 0) {
          const extension = recorder.mimeType.includes("mp4") ? "mp4" : recorder.mimeType.includes("wav") ? "wav" : "webm";
          setProfileAudioSample(blob, `microphone-reference.${extension}`);
        }
      };
      recorder.start();
      setRecordingProfileSample(true);
    } catch (err) {
      stopProfileRecordingStream();
      setRecordingProfileSample(false);
      setError(getErrorMessage(err, "无法开始麦克风录音。"));
    }
  };

  const handleStopProfileRecording = () => {
    const recorder = profileRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      return;
    }
    stopProfileRecordingStream();
    setRecordingProfileSample(false);
  };

  const handleSaveVoiceProfile = async () => {
    const name = newProfileName.trim() || "我的音色";
    const referenceText = newProfileReferenceText.trim();
    if (!referenceText) {
      setError("请填写参考音频中实际朗读的文本。");
      return;
    }

    if (profileDialogMode === "create") {
      if (!newProfileAudioFile) {
        setError("请先上传或录制一段参考音频。");
        return;
      }
      try {
        setSavingProfile(true);
        setError(null);
        const profile = await bridge.createVoiceProfile({
          name,
          referenceAudioFile: newProfileAudioFile,
          referenceAudioFileName: newProfileAudioFileName,
          referenceText,
          provider: ttsConfig?.provider || "local_mlx",
          model: resolvedModel,
          language,
          audioFormat: profileSampleAudioFormat(newProfileAudioFileName, newProfileAudioFile),
          settings: { ...settings, preview_text: referenceText },
        });
        await refreshVoiceProfiles();
        resetProfileDialog();
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
        setSavingProfile(false);
      }
      return;
    }

    const editingProfile = voiceProfiles.find((profile) => profile.voice_profile_id === editingProfileId);
    if (!editingProfile || editingProfile.source !== "user_saved") {
      setError("找不到要编辑的音色。");
      return;
    }

    const nameChanged = name !== editingProfile.name;
    const textChanged = referenceText !== (editingProfile.preview_text || editingProfile.reference_text || "");
    const hasNewAudio = Boolean(newProfileAudioFile);
    if (!nameChanged && !textChanged && !hasNewAudio) {
      resetProfileDialog();
      return;
    }

    try {
      setSavingProfile(true);
      setError(null);
      const patch: { name?: string; referenceText?: string; referenceAudioFile?: Blob; referenceAudioFileName?: string; audioFormat?: string } = {};
      if (nameChanged) patch.name = name;
      if (textChanged || hasNewAudio) patch.referenceText = referenceText;
      if (hasNewAudio && newProfileAudioFile) {
        patch.referenceAudioFile = newProfileAudioFile;
        patch.referenceAudioFileName = newProfileAudioFileName;
        patch.audioFormat = profileSampleAudioFormat(newProfileAudioFileName, newProfileAudioFile);
      }
      const profile = await bridge.updateVoiceProfile(editingProfileId, patch);
      await refreshVoiceProfiles();
      if (selectedSessionId && selectedScriptId && voiceReference?.voice_profile_id === profile.voice_profile_id) {
        await loadProject(selectedSessionId, selectedScriptId);
      }
      resetProfileDialog();
      setMessage(`已更新「${profile.name}」。`);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to update voice profile."));
    } finally {
      setSavingProfile(false);
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
      resetProfileDialog();
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
      <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5">
        <section className="rounded-[32px] border border-outline theme-panel-surface p-6 backdrop-blur-xl shadow-lg relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-accent-amber/[0.03] to-transparent pointer-events-none" />
          <div className="relative z-10 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-amber">Voice Library</p>
              <h1 className="mt-2 font-headline text-2xl font-bold tracking-tight text-primary">音色工坊</h1>
              <p className="mt-2.5 max-w-2xl text-sm leading-relaxed text-secondary/90">
                {scriptBoundMode
                  ? `为「${scriptTitle}」选择或创建一个可复用音色。完整音频生成和成品管理会在 Script 页完成。`
                  : "管理可复用音色库。打开某个脚本后，可以把这里的音色应用到那一集播客。"}
              </p>
            </div>
            {scriptBoundMode ? (
              <button
                type="button"
                onClick={() => selectedSessionId && selectedScriptId && navigate(`/script/${selectedSessionId}/${selectedScriptId}`)}
                className="rounded-2xl border border-outline bg-surface-container-high/60 hover:bg-surface-container-high hover:border-accent-amber/20 px-4 py-2 text-sm font-semibold text-primary transition-all duration-200 active:scale-95 cursor-pointer"
              >
                返回 Script
              </button>
            ) : null}
          </div>
        </section>

        {error ? <p className="rounded-2xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-200">{error}</p> : null}
        {message ? <p className="rounded-2xl border border-accent-amber/20 bg-accent-amber/10 p-3 text-sm text-accent-amber">{message}</p> : null}

        <div className="flex flex-col gap-5">
          <div className="mx-auto w-full max-w-[960px] space-y-5">
            <section className="rounded-[32px] border border-outline theme-panel-surface p-6 backdrop-blur-xl shadow-md">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-base font-bold font-headline text-primary tracking-wide">音色库</h2>
                  <p className="mt-1.5 text-xs leading-relaxed text-secondary/80">
                    {scriptBoundMode
                      ? "当前脚本的试听会使用所选音色的参考音频与参考文本；Script 页面生成音频时也会使用该 profile。"
                      : "这里是可复用音色资产库。可以播放参考音频、删除我的音色；打开某个脚本后才能把音色应用到具体播客。"}
                  </p>
                  {scriptBoundMode && selectedProfile ? (
                    <p className="mt-3 text-xs font-semibold text-accent-amber flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-accent-amber pulse-amber" />
                      当前选用：{selectedProfile.name}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2 shrink-0">
                  <button 
                    type="button" 
                    onClick={openCreateProfileDialog} 
                    className="inline-flex items-center gap-2 rounded-2xl theme-accent-gradient hover:shadow-lg hover:shadow-accent-amber/15 px-4 py-2.5 text-xs font-bold text-on-primary transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
                  >
                    <Mic className="h-3.5 w-3.5" /> 创建音色
                  </button>
                  <button 
                    type="button" 
                    onClick={() => void refreshVoiceProfiles()} 
                    className="inline-flex items-center gap-2 rounded-2xl border border-outline bg-surface-container-high/60 px-4 py-2.5 text-xs font-semibold text-secondary hover:text-primary transition-all duration-200 hover:bg-surface-container-high cursor-pointer"
                  >
                    <RefreshCw className="h-3.5 w-3.5" /> 刷新音色库
                  </button>
                </div>
              </div>
              <div className="mt-6 grid gap-4 grid-cols-1 sm:grid-cols-2">
                {activeVoiceProfiles.map((profile) => {
                  const isSelected = voiceReference?.voice_profile_id === profile.voice_profile_id;
                  const profileAudioError = profileAudioErrors[profile.voice_profile_id];
                  return (
                    <div 
                      key={profile.voice_profile_id} 
                      className={cn(
                        "rounded-[24px] p-5 transition-all duration-200 relative flex flex-col justify-between min-h-[240px]", 
                        isSelected ? "glass-card-selected" : "glass-card"
                      )}
                    >
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-bold text-primary tracking-wide truncate">{profile.name}</p>
                            <p className="mt-1 text-[10px] uppercase tracking-wider text-secondary/80 font-headline font-semibold">
                              {profile.source === "built_in" ? "默认音色" : "我的音色"} · {profile.voice_name || profile.voice_id} / {profile.style_name || profile.style_id}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-0.5 relative z-10">
                            {profile.source === "user_saved" ? (
                              <div className="flex items-center rounded-xl border border-outline theme-panel-elevated p-0.5">
                                <button
                                  type="button"
                                  onClick={() => openEditProfileDialog(profile)}
                                  className="inline-flex items-center rounded-lg p-1.5 text-secondary hover:bg-surface-container-high/60 hover:text-primary transition-colors cursor-pointer"
                                  aria-label={`编辑「${profile.name}」`}
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </button>
                                <span className="h-4 w-px bg-surface-container-high/60" aria-hidden />
                                <button
                                  type="button"
                                  onClick={() => void handleDeleteVoiceProfile(profile)}
                                  className="inline-flex items-center rounded-lg p-1.5 text-secondary hover:bg-red-500/10 hover:text-red-200 transition-colors cursor-pointer"
                                  aria-label={`删除「${profile.name}」`}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            ) : null}
                            {isSelected ? <CheckCircle2 className="ml-1 h-5 w-5 shrink-0 text-accent-amber" /> : null}
                          </div>
                        </div>
                        <p className="mt-3.5 line-clamp-2 text-xs leading-relaxed text-secondary/80">{profile.description || profile.preview_text}</p>
                      </div>
                      
                      <div className="mt-4">
                        <AudioPlayer
                          src={resolveAudioFileUrl(profile.audio_path)}
                          onError={() => handleProfileAudioLoadError(profile.voice_profile_id)}
                          className="bg-surface-container"
                          variant="minimal"
                        />
                        {profileAudioError ? <p className="mt-2 text-xs text-red-400">{profileAudioError}</p> : null}
                        <div className="mt-4 flex flex-wrap gap-2">
                          {scriptBoundMode ? (
                            <button
                              type="button"
                              onClick={() => void handleSelectVoiceProfile(profile)}
                              disabled={isSelected}
                              className={cn(
                                "rounded-xl border px-3 py-2 text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer",
                                isSelected
                                  ? "border-accent-amber/20 bg-accent-amber/5 text-accent-amber cursor-default"
                                  : "border-outline bg-surface-container-high/60 text-primary hover:bg-surface-container-high hover:border-accent-amber/20 active:scale-95"
                              )}
                            >
                              {isSelected ? "已用于当前脚本" : "用于当前脚本"}
                            </button>
                          ) : (
                            <span className="rounded-xl border border-outline bg-surface-container-high/60 px-3 py-2 text-xs font-medium text-secondary/80">
                              打开脚本后可选用
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {scriptBoundMode ? (
              <>
                <section className="rounded-[32px] border border-outline theme-panel-surface p-6 backdrop-blur-xl shadow-md">
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <h2 className="text-xs font-semibold uppercase tracking-wider text-secondary/80">试听设置</h2>
                      <p className="mt-2 text-xl font-bold font-headline text-primary tracking-tight">
                        {selectedProfile?.name ?? "未选择音色"} <span className="mx-1 text-primary/20 font-light">·</span> {selectedStyle?.name ?? "默认风格"} <span className="mx-1 text-primary/20 font-light">·</span> <span className="text-accent-amber">{speed.toFixed(1)}x</span>
                      </p>
                      <p className="mt-1.5 text-xs text-secondary/70">
                        {selectedProfile ? "将使用该音色的参考音频生成试听。" : "请先为当前脚本选用一个音色。"}
                      </p>
                    </div>
                  </div>
                </section>

                <section className="rounded-[32px] border border-outline theme-panel-surface p-6 backdrop-blur-xl shadow-md">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="text-base font-bold font-headline text-primary tracking-wide">音色试听</h2>
                      <p className="mt-1 text-xs text-secondary/85 leading-relaxed">
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
                      className="inline-flex items-center justify-center gap-2 rounded-2xl theme-accent-gradient hover:shadow-lg hover:shadow-accent-amber/15 px-4 py-2.5 text-xs font-bold text-on-primary transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 cursor-pointer shrink-0"
                    >
                      {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                      生成试听
                    </button>
                  </div>
                  <div className="mt-5 flex flex-wrap gap-2">
                    {[
                      { id: "standard", label: "标准试音句" },
                      { id: "script_opening", label: "使用脚本开头", disabled: !scriptOpening },
                      { id: "custom", label: "自定义文本" },
                    ].map((btn) => (
                      <button
                        key={btn.id}
                        type="button"
                        onClick={() => setPreviewTextMode(btn.id as PreviewTextMode)}
                        disabled={btn.disabled}
                        className={cn(
                          "rounded-full border px-4 py-2 text-xs font-semibold transition-all duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed", 
                          previewTextMode === btn.id 
                            ? "border-accent-amber bg-accent-amber/10 text-accent-amber shadow-sm" 
                            : "border-outline bg-surface-container-high/60 text-secondary hover:text-primary hover:bg-surface-container-high"
                        )}
                      >
                        {btn.label}
                      </button>
                    ))}
                  </div>
                  <textarea
                    value={previewText}
                    onChange={(event) => {
                      setPreviewTextMode("custom");
                      setPreviewText(event.target.value);
                    }}
                    rows={3}
                    placeholder="输入一句你想用来比较音色与风格的试音文本"
                    className={cn("mt-4 w-full resize-none rounded-[20px] border border-outline bg-background/50 px-4 py-3.5 text-sm text-primary outline-none transition-all duration-200 focus:border-accent-amber/30", previewTextMode !== "custom" && "hidden")}
                  />
                  <p className="mt-3.5 text-[11px] text-secondary/80 leading-relaxed bg-surface-container-low px-3.5 py-2.5 rounded-xl border border-outline-variant">
                    <span className="font-semibold text-accent-amber/90">当前试音文本：</span>
                    {effectivePreviewText ? `${effectivePreviewText.slice(0, 80)}${effectivePreviewText.length > 80 ? "…" : ""}` : "系统标准试音句"}
                  </p>
                  {!selectedProfileId ? (
                    <p className="mt-3 text-[11px] text-amber-300 font-medium pl-1">请先为当前脚本选用一个音色。</p>
                  ) : null}
                  {previewRequestState && previewRequestState.phase !== "succeeded" ? (
                    <div className="mt-4 rounded-2xl border border-outline bg-background/30 px-4 py-3.5 text-sm text-secondary/90 flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin text-accent-amber" />
                      <span>{Math.round(previewRequestState.progress_percent)}% · {previewRequestState.message}</span>
                    </div>
                  ) : null}
                  {previewSrc && previewMatchesCurrentSelection ? (
                    <div className="mt-4 space-y-3">
                      <AudioPlayer ref={previewAudioRef} src={previewSrc} onError={handlePreviewAudioLoadError} />
                      <div className="flex flex-wrap gap-2">
                        <button 
                          type="button" 
                          onClick={() => void handleDeletePreview()} 
                          className="inline-flex items-center gap-1.5 rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs font-semibold text-red-200 hover:bg-red-500/10 transition-colors cursor-pointer"
                        >
                          <Trash2 className="h-3.5 w-3.5" /> 删除试音音频
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {selectedProfile ? (
                    <div className="mt-4 rounded-2xl border border-emerald-500/15 bg-emerald-500/5 p-4 text-xs text-emerald-100/90 leading-relaxed">
                      <div className="flex items-start gap-2.5">
                        <CheckCircle2 className="mt-0.5 h-4.5 w-4.5 shrink-0 text-emerald-400" />
                        <p>已选择「{selectedProfile.name}」。试听会使用这个音色 profile，Script 页面生成音频时也会引用它。</p>
                      </div>
                    </div>
                  ) : null}
                </section>
              </>
            ) : null}
          </div>

          <section className="mx-auto w-full max-w-[960px] rounded-2xl border border-outline theme-panel-elevated p-4 backdrop-blur-md shadow-[0_12px_40px_rgba(0,0,0,0.3)]">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-start gap-3 sm:items-center">
                <div className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full sm:mt-0", localEngineReady ? "bg-emerald-400 shadow-[0_0_8px_#10b981]" : "bg-accent-amber animate-pulse shadow-[0_0_8px_#f59e0b]")} />
                <div className="min-w-0">
                  <h2 className="text-[11px] font-semibold uppercase tracking-wider text-secondary">当前语音引擎</h2>
                  <p className="mt-0.5 truncate text-sm font-semibold text-primary">{engineLabel}</p>
                  <p className={cn("mt-0.5 text-xs", localEngineReady ? "text-secondary/70" : "text-amber-200/90")}>{engineStatus}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => navigate("/models")}
                className="shrink-0 rounded-xl border border-outline bg-surface-container-high/60 px-3 py-2 text-xs font-semibold text-primary transition-all hover:border-outline hover:bg-surface-container-high active:scale-[0.98] cursor-pointer"
              >
                Change model
              </button>
            </div>
          </section>
        </div>
      </div>
      {profileDialogMode ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center theme-modal-overlay backdrop-blur-md px-4 py-6">
          <div className="max-h-full w-full max-w-2xl overflow-y-auto rounded-[32px] border border-outline theme-modal-surface backdrop-blur-2xl p-8 shadow-[0_24px_60px_rgba(0,0,0,0.5)]">
            <div className="flex items-start justify-between gap-4 border-b border-outline pb-5">
              <div>
                <h2 className="text-lg font-bold font-display text-primary tracking-tight">{profileDialogMode === "create" ? "创建我的音色" : "编辑我的音色"}</h2>
                <p className="mt-1.5 text-xs leading-relaxed text-secondary/80">
                  {profileDialogMode === "create"
                    ? "添加 10-30 秒参考音频，并逐字填写音频里实际朗读的文本。"
                    : "可修改名称与参考文本；如需更换参考音频，请重新上传或录制。"}
                </p>
              </div>
              <button
                type="button"
                onClick={resetProfileDialog}
                className="rounded-xl border border-outline bg-surface-container-high/60 p-2 text-secondary hover:text-primary hover:bg-surface-container-high transition-colors cursor-pointer"
                aria-label="关闭"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-6 grid gap-5">
              <label className="text-xs font-semibold text-secondary/90 flex flex-col gap-2">
                音色名称
                <input
                  value={newProfileName}
                  onChange={(event) => setNewProfileName(event.target.value)}
                  className="w-full rounded-2xl border border-outline bg-surface-container-high px-4 py-3 text-sm text-primary outline-none focus:border-accent-amber/30 transition-all font-sans placeholder:text-secondary/40 focus:bg-background"
                  placeholder="例如：我的知识讲述音色"
                />
              </label>

              <div>
                <p className="text-xs font-semibold text-secondary/90 mb-2">参考音频来源</p>
                <div className="grid gap-2 sm:grid-cols-3">
                  {[
                    { id: "upload", label: "上传", icon: Upload },
                    { id: "microphone", label: "麦克风录音", icon: Mic },
                    { id: "system", label: "系统内录", icon: FileAudio },
                  ].map((item) => {
                    const Icon = item.icon;
                    const isSystem = item.id === "system";
                    const selected = profileAudioSource === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => !isSystem && setProfileAudioSource(item.id as ProfileAudioSource)}
                        disabled={isSystem}
                        className={cn(
                          "inline-flex items-center justify-center gap-2 rounded-2xl border px-3 py-3 text-xs font-semibold disabled:opacity-40 transition-all cursor-pointer",
                          selected 
                            ? "border-accent-amber/30 bg-accent-amber/10 text-accent-amber shadow-[0_0_12px_rgba(242,191,87,0.1)]" 
                            : "border-outline bg-surface-container-high/60 text-secondary hover:text-primary hover:bg-surface-container-high hover:border-outline",
                        )}
                      >
                        <Icon className="h-3.5 w-3.5" />
                        {item.label}
                      </button>
                    );
                  })}
                </div>
                {profileAudioSource === "upload" ? (
                  <div className="mt-3 rounded-2xl border border-dashed border-outline bg-surface-container p-6 text-center hover:border-accent-amber/20 transition-colors">
                    <input
                      ref={profileFileInputRef}
                      type="file"
                      accept="audio/*,.wav,.mp3,.m4a,.mp4,.aac,.flac,.webm,.ogg"
                      className="hidden"
                      onChange={(event) => handleProfileFileSelected(event.target.files?.[0] ?? null)}
                    />
                    <button
                      type="button"
                      onClick={() => profileFileInputRef.current?.click()}
                      className="inline-flex items-center gap-2 rounded-xl border border-outline bg-surface-container-high/60 px-4 py-2.5 text-xs font-semibold text-primary hover:bg-surface-container-high hover:border-outline active:scale-[0.98] transition-all cursor-pointer"
                    >
                      <Upload className="h-4 w-4" />
                      选择音频文件
                    </button>
                    <p className="mt-2.5 text-[11px] text-secondary/60 leading-normal">支持 wav、mp3、m4a、mp4、aac、flac、webm、ogg；WAV 会校验 30 秒上限。</p>
                  </div>
                ) : null}
                {profileAudioSource === "microphone" ? (
                  <div className="mt-3 rounded-2xl border border-outline bg-surface-container p-6 flex flex-col items-center justify-center gap-3">
                    <button
                      type="button"
                      onClick={() => (recordingProfileSample ? handleStopProfileRecording() : void handleStartProfileRecording())}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition-all cursor-pointer",
                        recordingProfileSample 
                          ? "bg-red-500/10 border border-red-500/20 text-red-400 animate-pulse" 
                          : "bg-accent-amber hover:bg-accent-amber/90 active:scale-[0.98] text-on-primary shadow-[0_4px_16px_rgba(242,191,87,0.2)]",
                      )}
                    >
                      {recordingProfileSample ? <Square className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
                      {recordingProfileSample ? "停止录音" : "开始录音"}
                    </button>
                    <p className="text-[11px] text-secondary/60">录音完成后会自动作为参考音频。请控制在 30 秒以内。</p>
                  </div>
                ) : null}
                {profileAudioSource === "system" ? (
                  <div className="mt-3 rounded-2xl border border-outline bg-surface-container p-4 text-xs text-secondary/60">
                    系统内录需要新增 macOS 桌面采集能力；当前版本请使用上传或麦克风录音。
                  </div>
                ) : null}
                {profileDialogMode === "edit" && existingProfileAudioUrl && !newProfileAudioPreviewUrl ? (
                  <div className="mt-3 rounded-2xl border border-outline bg-surface-container-high p-4">
                    <p className="mb-2.5 text-xs font-semibold text-primary">当前参考音频</p>
                    <audio controls src={existingProfileAudioUrl} className="w-full rounded-lg" />
                  </div>
                ) : null}
                {newProfileAudioPreviewUrl ? (
                  <div className="mt-3 rounded-2xl border border-outline bg-surface-container-high p-4">
                    <p className="mb-2.5 text-xs font-semibold text-primary">{newProfileAudioFileName || "新参考音频"}</p>
                    <audio controls src={newProfileAudioPreviewUrl} className="w-full rounded-lg" />
                  </div>
                ) : null}
              </div>

              <label className="text-xs font-semibold text-secondary/90 flex flex-col gap-2">
                参考音频文本
                <textarea
                  value={newProfileReferenceText}
                  onChange={(event) => setNewProfileReferenceText(event.target.value)}
                  rows={5}
                  className="w-full resize-none rounded-2xl border border-outline bg-surface-container-high px-4 py-3 text-sm text-primary outline-none focus:border-accent-amber/30 transition-all font-sans leading-relaxed placeholder:text-secondary/40 focus:bg-background"
                  placeholder="逐字填写参考音频里实际说出的内容"
                />
              </label>

              {profileDialogMode === "edit" ? (
                <div className="rounded-2xl border border-red-500/10 bg-red-500/5 p-4 flex items-center justify-between gap-4">
                  <p className="text-xs text-secondary/80">删除后无法恢复；已使用该音色的脚本会清除对应参考。</p>
                  <button
                    type="button"
                    onClick={() => {
                      const profile = voiceProfiles.find((item) => item.voice_profile_id === editingProfileId);
                      if (profile) void handleDeleteVoiceProfile(profile);
                    }}
                    disabled={savingProfile}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs font-bold text-red-300 hover:bg-red-500/20 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                    删除此音色
                  </button>
                </div>
              ) : null}

              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end border-t border-outline pt-5">
                <button
                  type="button"
                  onClick={resetProfileDialog}
                  className="rounded-xl border border-outline bg-surface-container-high/60 px-4 py-2.5 text-xs font-bold text-secondary hover:text-primary hover:bg-surface-container-high active:scale-[0.98] transition-all cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void handleSaveVoiceProfile()}
                  disabled={savingProfile || recordingProfileSample}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent-amber hover:bg-accent-amber/90 active:scale-[0.98] transition-all px-5 py-2.5 text-xs font-bold text-on-primary disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-[0_4px_16px_rgba(242,191,87,0.2)]"
                >
                  {savingProfile ? <Loader2 className="h-4 w-4 animate-spin" /> : profileDialogMode === "create" ? <Mic className="h-4 w-4" /> : <Pencil className="h-4 w-4" />}
                  {profileDialogMode === "create"
                    ? scriptBoundMode
                      ? "创建并用于当前脚本"
                      : "创建音色"
                    : "保存修改"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </motion.div>
  );
}
