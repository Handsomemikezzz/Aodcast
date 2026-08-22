import { motion } from "framer-motion";
import { CheckCircle2, FileAudio, Loader2, Mic, Pencil, RefreshCw, Square, Trash2, Upload, Wand2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { resolveAudioFileUrl } from "../lib/audioFile";
import { useBridge } from "../lib/BridgeContext";
import type { LongTaskHandle } from "../lib/desktopBridge";
import { AudioPlayer } from "../components/AudioPlayer";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { getErrorMessage } from "../lib/requestState";
import { cn } from "../lib/utils";
import type {
  ModelStatus,
  RequestState,
  SessionProject,
  SpeakerReference,
  TTSCapability,
  TTSProviderConfig,
  VoicePreset,
  VoiceRenderSettings,
  VoiceStylePreset,
} from "../types";

const DEFAULT_LOCAL_TTS_MODEL = "mlx-community/VoxCPM2-8bit";
type PreviewTextMode = "standard" | "script_opening" | "custom";
type ReferenceAudioSource = "upload" | "microphone" | "system";
type ReferenceDialogMode = "create" | "edit";

function resolvedTtsModel(config: TTSProviderConfig | null): string {
  const raw = config?.model?.trim() ?? "";
  if (!raw || raw === "mock-voice") return DEFAULT_LOCAL_TTS_MODEL;
  return raw;
}

function shortRepoName(repo: string): string {
  return repo.split("/").pop()?.replace("Qwen3-TTS-12Hz-", "Qwen TTS ")?.replace("-Base-8bit", "") ?? repo;
}

function scriptOpeningText(script: string): string {
  return script.trim().replace(/\s+/g, " ").slice(0, 180);
}

function formatReferenceDuration(durationMs: number): string {
  const seconds = Math.max(0, Math.round(durationMs / 1000));
  return `${seconds} 秒`;
}

export function VoiceStudioPage() {
  const { sessionId: routeSessionId, scriptId: routeScriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const bridge = useBridge();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const previewAudioRef = useRef<HTMLAudioElement>(null);
  const referenceFileInputRef = useRef<HTMLInputElement>(null);
  const referenceRecorderRef = useRef<MediaRecorder | null>(null);
  const referenceRecordingChunksRef = useRef<Blob[]>([]);
  const referenceRecordingStreamRef = useRef<MediaStream | null>(null);
  const previewRequestTokenRef = useRef(0);
  const previewContextRef = useRef({ previewKey: "", speakerReferenceId: "", scriptId: "", sessionId: "" });
  const projectLoadTokenRef = useRef(0);
  const projectLoadContextRef = useRef({ scriptBoundMode: false, scriptId: "", sessionId: "" });
  const lastCurrentPreviewKeyRef = useRef("");

  const [projects, setProjects] = useState<SessionProject[]>([]);
  const [project, setProject] = useState<SessionProject | null>(null);
  const [voices, setVoices] = useState<VoicePreset[]>([]);
  const [speakerReferences, setSpeakerReferences] = useState<SpeakerReference[]>([]);
  const [styles, setStyles] = useState<VoiceStylePreset[]>([]);
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [ttsConfig, setTtsConfig] = useState<TTSProviderConfig | null>(null);
  const [ttsCapability, setTtsCapability] = useState<TTSCapability | null>(null);
  const [standardPreviewText, setStandardPreviewText] = useState("");
  const [previewTextMode, setPreviewTextMode] = useState<PreviewTextMode>("standard");
  const [previewText, setPreviewText] = useState("");
  const selectedSessionId = routeSessionId ?? "";
  const selectedScriptId = routeScriptId ?? "";
  const rawReturnTo = searchParams.get("returnTo") ?? "";
  const returnTo = rawReturnTo.startsWith("/") && !rawReturnTo.startsWith("//") ? rawReturnTo : "";
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
  const [previewTask, setPreviewTask] = useState<LongTaskHandle | null>(null);
  const [referenceDialogMode, setReferenceDialogMode] = useState<ReferenceDialogMode | null>(null);
  const [editingReferenceId, setEditingReferenceId] = useState("");
  const [existingReferenceAudioUrl, setExistingReferenceAudioUrl] = useState("");
  const [referenceAudioSource, setReferenceAudioSource] = useState<ReferenceAudioSource>("upload");
  const [newReferenceName, setNewReferenceName] = useState("");
  const [newReferenceAudioFile, setNewReferenceAudioFile] = useState<File | Blob | null>(null);
  const [newReferenceAudioFileName, setNewReferenceAudioFileName] = useState("");
  const [newReferenceAudioPreviewUrl, setNewReferenceAudioPreviewUrl] = useState("");
  const [newReferenceText, setNewReferenceText] = useState("");
  const [newReferenceLanguage, setNewReferenceLanguage] = useState("zh");
  const [savingReference, setSavingReference] = useState(false);
  const [recordingReferenceSample, setRecordingReferenceSample] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referenceAudioErrors, setReferenceAudioErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [referenceToDelete, setReferenceToDelete] = useState<SpeakerReference | null>(null);

  const selectedSession = projects.find((item) => item.session.session_id === selectedSessionId);
  const scriptBoundMode = Boolean(routeSessionId && routeScriptId);
  const canApplyReferenceToScript = Boolean(selectedSessionId && selectedScriptId);
  const scriptTitle = (project?.script as { title?: string } | undefined)?.title || selectedSession?.session.topic || "当前脚本";
  const scriptText = scriptBoundMode ? project?.script?.final?.trim() || project?.script?.draft?.trim() || "" : "";
  const scriptOpening = scriptOpeningText(scriptText);
  const effectivePreviewText =
    previewTextMode === "script_opening"
      ? scriptOpening || standardPreviewText
      : previewTextMode === "standard"
        ? standardPreviewText
        : previewText;
  const speakerReference = scriptBoundMode ? project?.artifact?.speaker_reference : undefined;
  const selectedReference = speakerReference?.speaker_reference_id
    ? speakerReferences.find((reference) => reference.speaker_reference_id === speakerReference.speaker_reference_id) ?? speakerReference
    : undefined;
  const selectedReferenceId = selectedReference?.speaker_reference_id ?? "";
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
      speakerReference: selectedReferenceId,
      voiceId: selectedVoiceId,
      voiceName: selectedVoice?.name ?? "",
      text: effectivePreviewText,
      style: selectedStyleId,
      speed,
      language,
      audioFormat,
      providerOverride,
    }),
    [audioFormat, effectivePreviewText, language, providerOverride, selectedReferenceId, selectedStyleId, selectedVoice?.name, selectedVoiceId, speed],
  );
  previewContextRef.current = {
    previewKey: currentPreviewKey,
    speakerReferenceId: selectedReferenceId,
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
    setPreviewTask(null);
  }, []);

  const stopReferenceRecordingStream = useCallback(() => {
    referenceRecordingStreamRef.current?.getTracks().forEach((track) => track.stop());
    referenceRecordingStreamRef.current = null;
  }, []);

  const setReferenceAudioSample = useCallback((file: File | Blob, fileName: string) => {
    setNewReferenceAudioFile(file);
    setNewReferenceAudioFileName(fileName);
    setNewReferenceAudioPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return URL.createObjectURL(file);
    });
  }, []);

  const resetReferenceDialog = useCallback(() => {
    setReferenceDialogMode(null);
    setEditingReferenceId("");
    setReferenceAudioSource("upload");
    setNewReferenceName("");
    setNewReferenceAudioFile(null);
    setNewReferenceAudioFileName("");
    setNewReferenceAudioPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return "";
    });
    setExistingReferenceAudioUrl("");
    setNewReferenceText("");
    setNewReferenceLanguage("zh");
    setRecordingReferenceSample(false);
    referenceRecordingChunksRef.current = [];
    referenceRecorderRef.current = null;
    stopReferenceRecordingStream();
  }, [stopReferenceRecordingStream]);

  const openCreateReferenceDialog = useCallback(() => {
    resetReferenceDialog();
    setReferenceDialogMode("create");
  }, [resetReferenceDialog]);

  const openEditReferenceDialog = useCallback((reference: SpeakerReference) => {
    resetReferenceDialog();
    setReferenceDialogMode("edit");
    setEditingReferenceId(reference.speaker_reference_id);
    setNewReferenceName(reference.name);
    setNewReferenceText(reference.reference_text);
    setNewReferenceLanguage(reference.language);
    setExistingReferenceAudioUrl(resolveAudioFileUrl(reference.audio_path));
  }, [resetReferenceDialog]);

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
    setProject(loaded);
  };

  const refreshSpeakerReferences = async () => {
    setReferenceAudioErrors({});
    setSpeakerReferences(await bridge.listSpeakerReferences());
  };

  useEffect(() => {
    void (async () => {
      try {
        const [catalog, loadedProjects, tts, modelStatus, capability, references] = await Promise.all([
          bridge.listVoicePresets(),
          bridge.listProjects(),
          bridge.showTTSConfig(),
          bridge.listModelsStatus(),
          bridge.getLocalTTSCapability(),
          bridge.listSpeakerReferences(),
        ]);
        setVoices(catalog.voices);
        setSpeakerReferences(references);
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
      if (newReferenceAudioPreviewUrl) URL.revokeObjectURL(newReferenceAudioPreviewUrl);
      stopReferenceRecordingStream();
    },
    [newReferenceAudioPreviewUrl, stopReferenceRecordingStream],
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

  // Success copy is ephemeral: show briefly, then clear so it doesn't pin the layout.
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(null), 3000);
    return () => window.clearTimeout(timer);
  }, [message]);

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
    if (!selectedReferenceId) {
      setError("请先从音色库选择一个音色，再生成试听。");
      return;
    }
    const requestToken = previewRequestTokenRef.current + 1;
    previewRequestTokenRef.current = requestToken;
    const requestSessionId = selectedSessionId;
    const requestScriptId = selectedScriptId;
    const requestReferenceId = selectedReferenceId;
    const requestPreviewKey = currentPreviewKey;
    const requestSettings = settings;
    const isCurrentPreviewRequest = () => {
      const context = previewContextRef.current;
      return (
        previewRequestTokenRef.current === requestToken &&
        context.sessionId === requestSessionId &&
        context.scriptId === requestScriptId &&
        context.speakerReferenceId === requestReferenceId &&
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
        onTaskStarted: (task) => {
          if (isCurrentPreviewRequest()) setPreviewTask(task);
        },
        sessionId: requestSessionId,
        scriptId: requestScriptId,
        providerOverride,
        speakerReferenceId: requestReferenceId,
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
      const errorMessage = getErrorMessage(err, "Failed to render preview.");
      if (/cancel/i.test(errorMessage)) {
        setError(null);
        setMessage("试听已取消。");
      } else {
        setError(errorMessage);
      }
      setPreviewRequestState(null);
    } finally {
      if (previewRequestTokenRef.current === requestToken) {
        setPreviewing(false);
        setPreviewTask(null);
      }
    }
  };

  const handleCancelPreview = async () => {
    if (!previewTask) return;
    try {
      const state = await bridge.cancelTask(previewTask.taskId, previewTask.runToken);
      if (state) setPreviewRequestState(state);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to cancel voice preview."));
    }
  };

  const handleReferenceFileSelected = (file: File | null) => {
    if (!file) return;
    if (!file.type.startsWith("audio/") && !/\.(wav|mp3|m4a|mp4|aac|flac|webm|ogg)$/i.test(file.name)) {
      setError("请选择 wav、mp3、m4a、mp4、aac、flac、webm 或 ogg 音频文件。");
      return;
    }
    setError(null);
    setReferenceAudioSample(file, file.name);
  };

  const handleStartReferenceRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("当前环境不支持麦克风录音，请改用上传音频。");
      return;
    }
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      referenceRecordingStreamRef.current = stream;
      referenceRecordingChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      referenceRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) referenceRecordingChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(referenceRecordingChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        referenceRecordingChunksRef.current = [];
        stopReferenceRecordingStream();
        setRecordingReferenceSample(false);
        if (blob.size > 0) {
          const extension = recorder.mimeType.includes("mp4") ? "mp4" : recorder.mimeType.includes("wav") ? "wav" : "webm";
          setReferenceAudioSample(blob, `microphone-reference.${extension}`);
        }
      };
      recorder.start();
      setRecordingReferenceSample(true);
    } catch (err) {
      stopReferenceRecordingStream();
      setRecordingReferenceSample(false);
      setError(getErrorMessage(err, "无法开始麦克风录音。"));
    }
  };

  const handleStopReferenceRecording = () => {
    const recorder = referenceRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      return;
    }
    stopReferenceRecordingStream();
    setRecordingReferenceSample(false);
  };

  const handleSaveSpeakerReference = async () => {
    const name = newReferenceName.trim() || "我的音色";
    const referenceText = newReferenceText.trim();
    const referenceLanguage = newReferenceLanguage.trim();
    if (!referenceText) {
      setError("请填写参考音频中实际朗读的文本。");
      return;
    }
    if (!referenceLanguage) {
      setError("请填写参考音频的语言。");
      return;
    }

    if (referenceDialogMode === "create") {
      if (!newReferenceAudioFile) {
        setError("请先上传或录制一段参考音频。");
        return;
      }
      try {
        setSavingReference(true);
        setError(null);
        const reference = await bridge.createSpeakerReference({
          name,
          referenceText,
          language: referenceLanguage,
          audioFile: newReferenceAudioFile,
          audioFileName: newReferenceAudioFileName,
        });
        await refreshSpeakerReferences();
        resetReferenceDialog();
        if (canApplyReferenceToScript) {
          const updated = await bridge.selectSpeakerReference(selectedSessionId, selectedScriptId, reference.speaker_reference_id);
          setProject(updated);
          setMessage(`已创建「${reference.name}」并用于当前脚本。返回 Studio 后可以生成完整音频。`);
          if (returnTo) {
            navigate(returnTo);
          }
        } else {
          setMessage(`已创建「${reference.name}」。打开脚本后可以选用这个音色。`);
        }
      } catch (err) {
        setError(getErrorMessage(err, "Failed to create speaker reference."));
      } finally {
        setSavingReference(false);
      }
      return;
    }

    const editingReference = speakerReferences.find((reference) => reference.speaker_reference_id === editingReferenceId);
    if (!editingReference || editingReference.source !== "user_saved") {
      setError("找不到要编辑的音色。");
      return;
    }

    const nameChanged = name !== editingReference.name;
    const textChanged = referenceText !== editingReference.reference_text;
    const languageChanged = referenceLanguage !== editingReference.language;
    const hasNewAudio = Boolean(newReferenceAudioFile);
    if (!nameChanged && !textChanged && !languageChanged && !hasNewAudio) {
      resetReferenceDialog();
      return;
    }

    try {
      setSavingReference(true);
      setError(null);
      const patch: { name?: string; referenceText?: string; language?: string; audioFile?: Blob; audioFileName?: string } = {};
      if (nameChanged) patch.name = name;
      if (textChanged || hasNewAudio) patch.referenceText = referenceText;
      if (languageChanged) patch.language = referenceLanguage;
      if (hasNewAudio && newReferenceAudioFile) {
        patch.audioFile = newReferenceAudioFile;
        patch.audioFileName = newReferenceAudioFileName;
      }
      const reference = await bridge.updateSpeakerReference(editingReferenceId, patch);
      await refreshSpeakerReferences();
      if (selectedSessionId && selectedScriptId && speakerReference?.speaker_reference_id === reference.speaker_reference_id) {
        const updated = await bridge.selectSpeakerReference(selectedSessionId, selectedScriptId, reference.speaker_reference_id);
        setProject(updated);
      }
      resetReferenceDialog();
      setMessage(`已更新「${reference.name}」。`);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to update speaker reference."));
    } finally {
      setSavingReference(false);
    }
  };

  const handleSelectSpeakerReference = async (reference: SpeakerReference) => {
    if (!canApplyReferenceToScript) {
      setError("请先从 Studio 打开 Voice Studio，再把音色应用到具体脚本。");
      return;
    }
    try {
      setError(null);
      clearPreviewState();
      const updated = await bridge.selectSpeakerReference(selectedSessionId, selectedScriptId, reference.speaker_reference_id);
      setProject(updated);
      await refreshSpeakerReferences();
      setMessage(`已为当前脚本选用「${reference.name}」。返回 Studio 后可以生成完整音频。`);
      if (returnTo) {
        navigate(returnTo);
      }
    } catch (err) {
      setError(getErrorMessage(err, "Failed to select speaker reference."));
    }
  };

  const handleDeleteSpeakerReference = async (reference: SpeakerReference) => {
    if (reference.source === "built_in") return;
    try {
      setError(null);
      await bridge.deleteSpeakerReference(reference.speaker_reference_id);
      await refreshSpeakerReferences();
      if (selectedSessionId && selectedScriptId) {
        await loadProject(selectedSessionId, selectedScriptId);
      }
      resetReferenceDialog();
      setReferenceToDelete(null);
      setMessage("音色已删除。");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete speaker reference."));
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

  const handleReferenceAudioLoadError = (referenceId: string) => {
    setReferenceAudioErrors((current) => ({
      ...current,
      [referenceId]: "无法加载参考音频。文件可能已移动或删除。",
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
                  ? `为「${scriptTitle}」选择或创建一个可复用音色。完整音频生成和成品管理会在 Studio 完成。`
                  : "管理可复用音色库。打开某个脚本后，可以把这里的音色应用到那一集播客。"}
              </p>
            </div>
            {scriptBoundMode ? (
              <button
                type="button"
                onClick={() => {
                  if (returnTo) {
                    navigate(returnTo);
                    return;
                  }
                  if (selectedSessionId && selectedScriptId) navigate(`/studio/${selectedSessionId}/${selectedScriptId}`);
                }}
                className="rounded-2xl border border-outline bg-surface-container-high/60 hover:bg-surface-container-high hover:border-accent-amber/20 px-4 py-2 text-sm font-semibold text-primary transition-all duration-200 active:scale-95 cursor-pointer"
              >
                返回 Studio
              </button>
            ) : null}
          </div>
        </section>

        {error ? <p role="alert" className="rounded-2xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-200">{error}</p> : null}

        <div className="flex flex-col gap-5">
          <div className="mx-auto w-full max-w-[960px] space-y-5">
            <section className="rounded-[32px] border border-outline theme-panel-surface p-6 backdrop-blur-xl shadow-md">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-base font-bold font-headline text-primary tracking-wide">音色库</h2>
                  <p className="mt-1.5 text-xs leading-relaxed text-secondary/80">
                    {scriptBoundMode
                      ? "当前脚本的试听会使用所选音色的参考音频与参考文本；Studio 生成音频时也会使用这份音色参考。"
                      : "这里是可复用音色资产库。可以播放参考音频、删除我的音色；打开某个脚本后才能把音色应用到具体播客。"}
                  </p>
                  {scriptBoundMode && selectedReference ? (
                    <p className="mt-3 text-xs font-semibold text-accent-amber flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-accent-amber pulse-amber" />
                      当前选用：{selectedReference.name}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2 shrink-0">
                  <button 
                    type="button" 
                    onClick={openCreateReferenceDialog}
                    className="inline-flex items-center gap-2 rounded-2xl theme-accent-gradient hover:shadow-lg hover:shadow-accent-amber/15 px-4 py-2.5 text-xs font-bold text-on-primary transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
                  >
                    <Mic className="h-3.5 w-3.5" /> 创建音色
                  </button>
                  <button 
                    type="button" 
                    onClick={() => void refreshSpeakerReferences()}
                    className="inline-flex items-center gap-2 rounded-2xl border border-outline bg-surface-container-high/60 px-4 py-2.5 text-xs font-semibold text-secondary hover:text-primary transition-all duration-200 hover:bg-surface-container-high cursor-pointer"
                  >
                    <RefreshCw className="h-3.5 w-3.5" /> 刷新音色库
                  </button>
                </div>
              </div>
              <div className="mt-6 grid gap-4 grid-cols-1 sm:grid-cols-2">
                {speakerReferences.map((reference) => {
                  const isSelected = speakerReference?.speaker_reference_id === reference.speaker_reference_id;
                  const referenceAudioError = referenceAudioErrors[reference.speaker_reference_id];
                  return (
                    <div 
                      key={reference.speaker_reference_id}
                      className={cn(
                        "rounded-[24px] p-5 transition-all duration-200 relative flex flex-col justify-between min-h-[240px]", 
                        isSelected ? "glass-card-selected" : "glass-card"
                      )}
                    >
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-bold text-primary tracking-wide truncate">{reference.name}</p>
                            <p className="mt-1 text-[10px] uppercase tracking-wider text-secondary/80 font-headline font-semibold">
                              {reference.source === "built_in" ? "默认音色" : "我的音色"} · {reference.language} · {formatReferenceDuration(reference.duration_ms)}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-0.5 relative z-10">
                            {reference.source === "user_saved" ? (
                              <div className="flex items-center rounded-xl border border-outline theme-panel-elevated p-0.5">
                                <button
                                  type="button"
                                  onClick={() => openEditReferenceDialog(reference)}
                                  className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-secondary hover:bg-surface-container-high/60 hover:text-primary transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
                                  aria-label={`编辑「${reference.name}」`}
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </button>
                                <span className="h-4 w-px bg-surface-container-high/60" aria-hidden />
                                <button
                                  type="button"
                                  onClick={() => setReferenceToDelete(reference)}
                                  className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-secondary hover:bg-red-500/10 hover:text-red-200 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
                                  aria-label={`删除「${reference.name}」`}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            ) : null}
                            {isSelected ? <CheckCircle2 className="ml-1 h-5 w-5 shrink-0 text-accent-amber" /> : null}
                          </div>
                        </div>
                        <p className="mt-3.5 line-clamp-2 text-xs leading-relaxed text-secondary/80">{reference.description || reference.reference_text}</p>
                      </div>
                      
                      <div className="mt-4">
                        <AudioPlayer
                          src={resolveAudioFileUrl(reference.audio_path)}
                          onError={() => handleReferenceAudioLoadError(reference.speaker_reference_id)}
                          className="bg-surface-container"
                          variant="minimal"
                        />
                        {referenceAudioError ? <p className="mt-2 text-xs text-red-400">{referenceAudioError}</p> : null}
                        <div className="mt-4 flex flex-wrap gap-2">
                          {scriptBoundMode ? (
                            <button
                              type="button"
                              onClick={() => void handleSelectSpeakerReference(reference)}
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
                {speakerReferences.length === 0 ? (
                  <div className="sm:col-span-2 rounded-[24px] border border-dashed border-outline bg-surface-container/50 p-8 text-center">
                    <p className="text-sm font-semibold text-primary">音色库还是空的</p>
                    <p className="mt-1.5 text-xs text-secondary/80">上传或录制一段参考音频，创建第一份音色参考。</p>
                  </div>
                ) : null}
              </div>
            </section>

            {scriptBoundMode ? (
              <>
                <section className="rounded-[32px] border border-outline theme-panel-surface p-6 backdrop-blur-xl shadow-md">
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <h2 className="text-xs font-semibold uppercase tracking-wider text-secondary/80">试听设置</h2>
                      <p className="mt-2 text-xl font-bold font-headline text-primary tracking-tight">
                        {selectedReference?.name ?? "未选择音色"} <span className="mx-1 text-primary/20 font-light">·</span> {selectedStyle?.name ?? "默认风格"} <span className="mx-1 text-primary/20 font-light">·</span> <span className="text-accent-amber">{speed.toFixed(1)}x</span>
                      </p>
                      <p className="mt-1.5 text-xs text-secondary/70">
                        {selectedReference ? "风格和语速仅用于本次试听，不会写入音色参考。" : "请先为当前脚本选用一个音色。"}
                      </p>
                    </div>
                  </div>
                </section>

                <section className="rounded-[32px] border border-outline theme-panel-surface p-6 backdrop-blur-xl shadow-md">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="text-base font-bold font-headline text-primary tracking-wide">音色试听</h2>
                      <p className="mt-1 text-xs text-secondary/85 leading-relaxed">
                        用当前脚本选用的音色生成一段短试听；完整音频仍在 Studio 生成。
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handlePreview()}
                      disabled={
                        previewing ||
                        !selectedVoice ||
                        !selectedStyle ||
                        !selectedReferenceId ||
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
                  {!selectedReferenceId ? (
                    <p className="mt-3 text-[11px] text-amber-300 font-medium pl-1">请先为当前脚本选用一个音色。</p>
                  ) : null}
                  {previewRequestState && previewRequestState.phase !== "succeeded" ? (
                    <div className="mt-4 rounded-2xl border border-outline bg-background/30 px-4 py-3.5 text-sm text-secondary/90 flex items-center gap-3" aria-live="polite">
                      <Loader2 className="h-4 w-4 animate-spin text-accent-amber shrink-0" />
                      <span className="min-w-0 flex-1">{Math.round(previewRequestState.progress_percent)}% · {previewRequestState.message}</span>
                      {previewTask && previewRequestState.phase === "running" ? (
                        <button
                          type="button"
                          onClick={() => void handleCancelPreview()}
                          className="min-h-10 shrink-0 rounded-xl border border-outline bg-surface-container-high px-3 text-xs font-bold text-primary hover:bg-surface-container-highest"
                        >
                          取消
                        </button>
                      ) : null}
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
                  {selectedReference ? (
                    <div className="mt-4 rounded-2xl border border-emerald-500/15 bg-emerald-500/5 p-4 text-xs text-emerald-100/90 leading-relaxed">
                      <div className="flex items-start gap-2.5">
                        <CheckCircle2 className="mt-0.5 h-4.5 w-4.5 shrink-0 text-emerald-400" />
                        <p>已选择「{selectedReference.name}」。试听和 Studio 音频生成都会使用这份音色参考。</p>
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
      {referenceDialogMode ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center theme-modal-overlay backdrop-blur-md px-4 py-6">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="speaker-reference-dialog-title"
            className="flex max-h-full w-full max-w-2xl flex-col overflow-hidden rounded-[32px] border border-outline theme-modal-surface backdrop-blur-2xl shadow-[0_24px_60px_rgba(0,0,0,0.5)]"
          >
            {/* Sticky header — stays visible while the form scrolls */}
            <div className="flex shrink-0 items-start justify-between gap-4 border-b border-outline px-6 pb-4 pt-6 sm:px-8 sm:pt-7">
              <div className="min-w-0">
                <h2 id="speaker-reference-dialog-title" className="text-lg font-bold font-display text-primary tracking-tight">
                  {referenceDialogMode === "create" ? "创建我的音色" : "编辑我的音色"}
                </h2>
                <p className="mt-1.5 text-xs leading-relaxed text-secondary/80">
                  {referenceDialogMode === "create"
                    ? "添加 10-30 秒参考音频，并逐字填写音频里实际朗读的文本。"
                    : "可修改名称、语言与参考文本；如需更换参考音频，请重新上传或录制。"}
                </p>
              </div>
              <button
                type="button"
                onClick={resetReferenceDialog}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-outline bg-surface-container-high/60 text-secondary hover:text-primary hover:bg-surface-container-high transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
                aria-label="关闭"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Only the form body scrolls so Cancel / Save remain on-screen */}
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 mac-scrollbar sm:px-8">
              <div className="grid gap-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="text-xs font-semibold text-secondary/90 flex flex-col gap-2">
                    音色名称
                    <input
                      value={newReferenceName}
                      onChange={(event) => setNewReferenceName(event.target.value)}
                      className="w-full rounded-2xl border border-outline bg-surface-container-high px-4 py-2.5 text-sm text-primary outline-none focus:border-accent-amber/30 transition-all font-sans placeholder:text-secondary/40 focus:bg-background"
                      placeholder="例如：我的知识讲述音色"
                    />
                  </label>

                  <label className="text-xs font-semibold text-secondary/90 flex flex-col gap-2">
                    参考音频语言
                    <input
                      value={newReferenceLanguage}
                      onChange={(event) => setNewReferenceLanguage(event.target.value)}
                      className="w-full rounded-2xl border border-outline bg-surface-container-high px-4 py-2.5 text-sm text-primary outline-none focus:border-accent-amber/30 transition-all font-sans placeholder:text-secondary/40 focus:bg-background"
                      placeholder="例如：zh、en 或 yue"
                    />
                    <span className="font-normal text-[11px] text-secondary/60">简短语言标签，帮助引擎理解参考内容。</span>
                  </label>
                </div>

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
                      const selected = referenceAudioSource === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => !isSystem && setReferenceAudioSource(item.id as ReferenceAudioSource)}
                          disabled={isSystem}
                          className={cn(
                            "inline-flex items-center justify-center gap-2 rounded-2xl border px-3 py-2.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 transition-all cursor-pointer",
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
                  {referenceAudioSource === "upload" ? (
                    <div className="mt-3 rounded-2xl border border-dashed border-outline bg-surface-container px-4 py-4 text-center hover:border-accent-amber/20 transition-colors">
                      <input
                        ref={referenceFileInputRef}
                        type="file"
                        accept="audio/*,.wav,.mp3,.m4a,.mp4,.aac,.flac,.webm,.ogg"
                        className="hidden"
                        onChange={(event) => handleReferenceFileSelected(event.target.files?.[0] ?? null)}
                      />
                      <button
                        type="button"
                        onClick={() => referenceFileInputRef.current?.click()}
                        className="inline-flex items-center gap-2 rounded-xl border border-outline bg-surface-container-high/60 px-4 py-2 text-xs font-semibold text-primary hover:bg-surface-container-high hover:border-outline active:scale-[0.98] transition-all cursor-pointer"
                      >
                        <Upload className="h-4 w-4" />
                        选择音频文件
                      </button>
                      <p className="mt-2 text-[11px] text-secondary/60 leading-normal">支持 wav、mp3、m4a、mp4、aac、flac、webm、ogg；WAV 会校验 30 秒上限。</p>
                    </div>
                  ) : null}
                  {referenceAudioSource === "microphone" ? (
                    <div className="mt-3 rounded-2xl border border-outline bg-surface-container px-4 py-4 flex flex-col items-center justify-center gap-2.5">
                      <button
                        type="button"
                        onClick={() => (recordingReferenceSample ? handleStopReferenceRecording() : void handleStartReferenceRecording())}
                        className={cn(
                          "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition-all cursor-pointer",
                          recordingReferenceSample
                            ? "bg-red-500/10 border border-red-500/20 text-red-400 animate-pulse"
                            : "bg-accent-amber hover:bg-accent-amber/90 active:scale-[0.98] text-on-primary shadow-[0_4px_16px_rgba(242,191,87,0.2)]",
                        )}
                      >
                        {recordingReferenceSample ? <Square className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
                        {recordingReferenceSample ? "停止录音" : "开始录音"}
                      </button>
                      <p className="text-[11px] text-secondary/60">录音完成后会自动作为参考音频。请控制在 30 秒以内。</p>
                    </div>
                  ) : null}
                  {referenceAudioSource === "system" ? (
                    <div className="mt-3 rounded-2xl border border-outline bg-surface-container px-4 py-3 text-xs text-secondary/60">
                      系统内录需要新增 macOS 桌面采集能力；当前版本请使用上传或麦克风录音。
                    </div>
                  ) : null}
                  {referenceDialogMode === "edit" && existingReferenceAudioUrl && !newReferenceAudioPreviewUrl ? (
                    <div className="mt-3 rounded-2xl border border-outline bg-surface-container-high px-3 py-3">
                      <p className="mb-2 text-[11px] font-semibold text-secondary">当前参考音频</p>
                      <audio controls src={existingReferenceAudioUrl} className="w-full rounded-lg" />
                    </div>
                  ) : null}
                  {newReferenceAudioPreviewUrl ? (
                    <div className="mt-3 rounded-2xl border border-outline bg-surface-container-high px-3 py-3">
                      <p className="mb-2 text-[11px] font-semibold text-secondary">{newReferenceAudioFileName || "新参考音频"}</p>
                      <audio controls src={newReferenceAudioPreviewUrl} className="w-full rounded-lg" />
                    </div>
                  ) : null}
                </div>

                <label className="text-xs font-semibold text-secondary/90 flex flex-col gap-2">
                  参考音频文本
                  <textarea
                    value={newReferenceText}
                    onChange={(event) => setNewReferenceText(event.target.value)}
                    rows={4}
                    className="w-full resize-none rounded-2xl border border-outline bg-surface-container-high px-4 py-3 text-sm text-primary outline-none focus:border-accent-amber/30 transition-all font-sans leading-relaxed placeholder:text-secondary/40 focus:bg-background"
                    placeholder="逐字填写参考音频里实际说出的内容"
                  />
                </label>
              </div>
            </div>

            {/* Sticky footer: delete (edit only) left, primary actions right */}
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-outline px-6 py-4 sm:px-8">
              {referenceDialogMode === "edit" ? (
                <button
                  type="button"
                  onClick={() => {
                    const reference = speakerReferences.find((item) => item.speaker_reference_id === editingReferenceId);
                    if (reference) setReferenceToDelete(reference);
                  }}
                  disabled={savingReference}
                  className="inline-flex min-h-11 items-center gap-1.5 rounded-xl px-2.5 text-xs font-semibold text-red-300/90 hover:bg-red-500/10 hover:text-red-200 transition-colors cursor-pointer disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  删除
                </button>
              ) : (
                <span />
              )}
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  onClick={resetReferenceDialog}
                  className="rounded-xl border border-outline bg-surface-container-high/60 px-4 py-2.5 text-xs font-bold text-secondary hover:text-primary hover:bg-surface-container-high active:scale-[0.98] transition-all cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void handleSaveSpeakerReference()}
                  disabled={savingReference || recordingReferenceSample}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent-amber hover:bg-accent-amber/90 active:scale-[0.98] transition-all px-5 py-2.5 text-xs font-bold text-on-primary disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-[0_4px_16px_rgba(242,191,87,0.2)]"
                >
                  {savingReference ? <Loader2 className="h-4 w-4 animate-spin" /> : referenceDialogMode === "create" ? <Mic className="h-4 w-4" /> : <Pencil className="h-4 w-4" />}
                  {referenceDialogMode === "create"
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
      <ConfirmDialog
        open={referenceToDelete !== null}
        title="删除此音色？"
        message={
          referenceToDelete
            ? `删除「${referenceToDelete.name}」？已使用该音色的脚本会清除对应参考。`
            : ""
        }
        onClose={() => setReferenceToDelete(null)}
        actions={[
          { label: "取消", onClick: () => setReferenceToDelete(null) },
          {
            label: "删除",
            variant: "danger",
            onClick: () => {
              const target = referenceToDelete;
              if (!target) return;
              void handleDeleteSpeakerReference(target);
            },
          },
        ]}
      />
      {message ? (
        <div className="pointer-events-none fixed inset-x-0 bottom-8 z-50 flex justify-center px-4">
          <p
            role="status"
            aria-live="polite"
            className="max-w-md rounded-2xl border border-accent-amber/25 bg-surface-container px-4 py-3 text-sm font-medium text-accent-amber shadow-[0_12px_32px_rgba(0,0,0,0.18)]"
          >
            {message}
          </p>
        </div>
      ) : null}
    </motion.div>
  );
}
