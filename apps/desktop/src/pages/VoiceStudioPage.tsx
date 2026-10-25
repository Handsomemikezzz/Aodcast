import { ArrowLeft, Check, Loader2, Mic, Pencil, Plus, Square, Trash2, Upload, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { resolveAudioFileUrl } from "../lib/audioFile";
import { useBridge } from "../lib/BridgeContext";
import type { LongTaskHandle } from "../lib/desktopBridge";
import { AudioPlayer } from "../components/AudioPlayer";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { OverflowMenu } from "../components/OverflowMenu";
import { getErrorMessage } from "../lib/requestState";
import { readySpeechModel } from "../lib/voiceSettings";
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

const DEFAULT_LOCAL_TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit";
type PreviewTextMode = "standard" | "script_opening" | "custom";
type ReferenceAudioSource = "upload" | "microphone";
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
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
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
  const canApplyReferenceToScript = Boolean(selectedSessionId && selectedScriptId && ttsConfig?.provider !== "local_http");
  const scriptTitle = (project?.script as { title?: string } | undefined)?.title || selectedSession?.session.topic || "this script";
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
  const currentModel = ttsConfig?.provider === "local_http" ? readySpeechModel(models, resolvedModel) : undefined;
  const isLocalEngine = ttsConfig?.provider === "local_http";
  const localEngineReady = Boolean(ttsConfig) && (!isLocalEngine || Boolean(ttsCapability?.available && currentModel));
  const previewEngineReady = localEngineReady;
  const engineLabel = isLocalEngine
    ? `Local HTTP · ${currentModel?.display_name ?? shortRepoName(resolvedModel)}`
    : `${ttsConfig?.provider || "Loading"} · ${ttsConfig?.model || ""}`;
  const engineStatus = !ttsConfig ? "Loading" : localEngineReady ? "Ready" : "Service unavailable";

  const settings: VoiceRenderSettings = useMemo(
    () => ({
      voice_id: isLocalEngine ? ttsConfig?.voice || "默认中文音色" : selectedVoiceId,
      voice_name: selectedVoice?.name ?? "",
      style_id: isLocalEngine ? "natural" : selectedStyleId,
      style_name: selectedStyle?.name ?? "",
      speed: isLocalEngine ? 1 : speed,
      language,
      audio_format: audioFormat,
      preview_text: effectivePreviewText,
    }),
    [audioFormat, effectivePreviewText, language, selectedStyle?.name, selectedStyleId, selectedVoice?.name, selectedVoiceId, speed, isLocalEngine, ttsConfig?.voice],
  );

  const currentPreviewKey = useMemo(
    () => JSON.stringify({
      speakerReference: selectedReferenceId,
      voiceId: selectedVoiceId,
      voiceName: selectedVoice?.name ?? "",
      text: effectivePreviewText,
      style: selectedStyleId,
      speed: isLocalEngine ? 1 : speed,
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

  useEffect(() => {
    if (!referenceDialogMode) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !savingReference && !recordingReferenceSample && !referenceToDelete) {
        resetReferenceDialog();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [recordingReferenceSample, referenceDialogMode, referenceToDelete, resetReferenceDialog, savingReference]);

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
    if (!isLocalEngine && !selectedReferenceId) {
      setError("Choose a voice for this script first.");
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
        modelId: isLocalEngine ? currentModel?.hf_repo_id || currentModel?.model_name : undefined,
        speakerReferenceId: isLocalEngine ? undefined : requestReferenceId,
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
        setMessage("Preview cancelled.");
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
      setError("Choose a WAV, MP3, M4A, MP4, AAC, FLAC, WebM, or OGG audio file.");
      return;
    }
    setError(null);
    setReferenceAudioSample(file, file.name);
  };

  const handleStartReferenceRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Recording isn't available here. Upload a file instead.");
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
      setError(getErrorMessage(err, "Couldn't start recording."));
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
    const name = newReferenceName.trim() || "My voice";
    const referenceText = newReferenceText.trim();
    const referenceLanguage = newReferenceLanguage.trim();
    if (!referenceText) {
      setError("Enter the exact words spoken in the sample.");
      return;
    }
    if (!referenceLanguage) {
      setError("Enter the language of the sample.");
      return;
    }

    if (referenceDialogMode === "create") {
      if (!newReferenceAudioFile) {
        setError("Upload or record a sample first.");
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
          setMessage(`Created “${reference.name}” and applied it to this script.`);
          if (returnTo) {
            navigate(returnTo);
          }
        } else {
          setMessage(isLocalEngine ? `Saved “${reference.name}”. The local speech service can't use voice samples.` : `Created “${reference.name}”. Open an episode to use it.`);
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
      setError("Couldn't find that voice.");
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
      if (!isLocalEngine && selectedSessionId && selectedScriptId && speakerReference?.speaker_reference_id === reference.speaker_reference_id) {
        const updated = await bridge.selectSpeakerReference(selectedSessionId, selectedScriptId, reference.speaker_reference_id);
        setProject(updated);
      }
      resetReferenceDialog();
      setMessage(`Updated “${reference.name}”.`);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to update speaker reference."));
    } finally {
      setSavingReference(false);
    }
  };

  const handleSelectSpeakerReference = async (reference: SpeakerReference) => {
    if (!canApplyReferenceToScript) {
      setError("Open Voice from an episode to apply a voice to its script.");
      return;
    }
    try {
      setError(null);
      clearPreviewState();
      const updated = await bridge.selectSpeakerReference(selectedSessionId, selectedScriptId, reference.speaker_reference_id);
      setProject(updated);
      await refreshSpeakerReferences();
      setMessage(`Using “${reference.name}” for this script.`);
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
      setMessage("Voice deleted.");
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
      setMessage("Preview deleted.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete preview audio."));
    }
  };

  const handleReferenceAudioLoadError = (referenceId: string) => {
    setReferenceAudioErrors((current) => ({
      ...current,
      [referenceId]: "Couldn't load this sample. The file may have been moved or deleted.",
    }));
  };

  const handlePreviewAudioLoadError = () => {
    setError("Couldn't load the preview. Generate it again.");
  };

  const backToEpisode = () => {
    if (returnTo) {
      navigate(returnTo);
      return;
    }
    if (selectedSessionId && selectedScriptId) navigate(`/studio/${selectedSessionId}/${selectedScriptId}`);
  };
  const canPreview = !previewing && previewEngineReady && (isLocalEngine || Boolean(selectedReferenceId && selectedVoice && selectedStyle));
  const fieldClass =
    "w-full rounded-lg border border-outline bg-transparent px-3 text-[13px] text-primary placeholder:text-secondary/60 outline-none focus:border-primary/25";
  const segmentClass = (active: boolean) =>
    cn(
      "inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[12px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40",
      active ? "bg-primary/[0.07] text-primary" : "text-secondary hover:text-primary",
    );

  return (
    <div className="h-full overflow-y-auto px-6 py-8 lg:px-10">
      <div className="mx-auto flex w-full max-w-3xl flex-col">
        {scriptBoundMode ? (
          <button
            type="button"
            onClick={backToEpisode}
            className="-ml-2 mb-4 inline-flex h-9 w-fit items-center gap-1.5 rounded-lg px-2 text-[13px] text-secondary transition-colors hover:bg-primary/5 hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to episode
          </button>
        ) : null}
        <header className="flex items-center justify-between gap-4">
          <h1 className="text-2xl font-headline font-semibold text-primary">Voice</h1>
          <button
            type="button"
            onClick={openCreateReferenceDialog}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-[13px] font-semibold text-background transition-opacity hover:opacity-90"
          >
            <Plus className="h-4 w-4" /> New voice
          </button>
        </header>
        <p className="mt-1 text-sm text-secondary">
          {scriptBoundMode
            ? `Choose or create a voice for “${scriptTitle}”. Full audio is generated back in the episode.`
            : "Reusable voice samples. Open an episode to apply one to its script."}
        </p>

        {isLocalEngine ? (
          <p className="mt-4 rounded-lg bg-primary/[0.04] px-3 py-2.5 text-[12px] leading-5 text-secondary">
            The local speech service uses preset voices, chosen per episode. Saved samples are kept here but can only be
            applied with a cloud speech engine (Settings).
          </p>
        ) : null}

        {error ? <p role="alert" className="mt-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2.5 text-[13px] text-red-700 dark:text-red-300">{error}</p> : null}

        {speakerReferences.length === 0 ? (
          <div className="mt-6 rounded-xl border border-dashed border-outline p-8 text-center">
            <p className="text-sm font-medium text-primary">No voices yet</p>
            <p className="mt-1 text-[13px] text-secondary">Upload or record a short sample to create your first voice.</p>
          </div>
        ) : (
          <ul className="mt-6 divide-y divide-outline rounded-xl border border-outline">
            {speakerReferences.map((reference) => {
              const isSelected = speakerReference?.speaker_reference_id === reference.speaker_reference_id;
              const referenceAudioError = referenceAudioErrors[reference.speaker_reference_id];
              return (
                <li key={reference.speaker_reference_id} className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 text-[14px] font-medium text-primary">
                      <span className="truncate">{reference.name}</span>
                      {isSelected ? (
                        <span className="inline-flex shrink-0 items-center gap-0.5 text-[12px] font-normal text-emerald-700 dark:text-emerald-300">
                          <Check className="h-3.5 w-3.5" /> In use
                        </span>
                      ) : null}
                    </p>
                    <p className="mt-0.5 truncate text-[12px] text-secondary" title={reference.description || reference.reference_text}>
                      {reference.source === "built_in" ? "Built in" : "Yours"} · {reference.language} · {formatReferenceDuration(reference.duration_ms)}
                      {reference.description || reference.reference_text ? ` · ${reference.description || reference.reference_text}` : ""}
                    </p>
                    {referenceAudioError ? <p className="mt-1 text-[12px] text-red-700 dark:text-red-300">{referenceAudioError}</p> : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <div className="w-56">
                      <AudioPlayer
                        src={resolveAudioFileUrl(reference.audio_path)}
                        onError={() => handleReferenceAudioLoadError(reference.speaker_reference_id)}
                       
                      />
                    </div>
                    {scriptBoundMode && !isLocalEngine && !isSelected ? (
                      <button
                        type="button"
                        onClick={() => void handleSelectSpeakerReference(reference)}
                        className="inline-flex h-8 items-center rounded-lg border border-outline px-2.5 text-[12px] font-medium text-primary transition-colors hover:bg-primary/5"
                      >
                        Use
                      </button>
                    ) : null}
                    {reference.source === "user_saved" ? (
                      <OverflowMenu
                        label={`More actions for ${reference.name}`}
                        items={[
                          { label: "Edit", icon: Pencil, onSelect: () => openEditReferenceDialog(reference) },
                          { label: "Delete", icon: Trash2, danger: true, onSelect: () => setReferenceToDelete(reference) },
                        ]}
                      />
                    ) : (
                      <span className="w-9" aria-hidden />
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {scriptBoundMode ? (
          <section className="mt-8 border-t border-outline pt-6">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-[15px] font-semibold text-primary">Preview</h2>
                <p className="mt-0.5 truncate text-[12px] text-secondary">
                  {isLocalEngine
                    ? `${voices.find((voice) => voice.voice_id === ttsConfig?.voice)?.name ?? "Service default voice"} · Natural · 1.0×`
                    : selectedReference
                      ? `${selectedReference.name} · ${selectedStyle?.name ?? "Default style"} · ${speed.toFixed(1)}×`
                      : "Choose a voice above to preview it."}
                </p>
              </div>
              {previewTask && previewRequestState?.phase === "running" ? (
                <button
                  type="button"
                  onClick={() => void handleCancelPreview()}
                  className="inline-flex h-9 shrink-0 items-center rounded-lg border border-outline px-3 text-[13px] font-medium text-primary hover:bg-primary/5"
                >
                  Cancel
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void handlePreview()}
                  disabled={!canPreview}
                  className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-[13px] font-semibold text-background transition-opacity disabled:opacity-35"
                >
                  {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Generate preview
                </button>
              )}
            </div>

            <div className="mt-4 inline-flex rounded-lg border border-outline p-0.5" role="group" aria-label="Preview text">
              {([
                { id: "standard", label: "Sample sentence" },
                { id: "script_opening", label: "Script opening", disabled: !scriptOpening },
                { id: "custom", label: "Custom" },
              ] as const).map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => setPreviewTextMode(option.id)}
                  disabled={"disabled" in option && option.disabled}
                  aria-pressed={previewTextMode === option.id}
                  className={segmentClass(previewTextMode === option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            {previewTextMode === "custom" ? (
              <textarea
                value={previewText}
                onChange={(event) => setPreviewText(event.target.value)}
                rows={3}
                placeholder="Type a sentence to hear in this voice"
                aria-label="Custom preview text"
                className={cn(fieldClass, "mt-3 resize-none py-2")}
              />
            ) : (
              <p className="mt-3 line-clamp-2 text-[13px] leading-relaxed text-secondary">{effectivePreviewText || "—"}</p>
            )}

            {previewRequestState && previewRequestState.phase !== "succeeded" ? (
              <p className="mt-3 flex items-center gap-2 text-[13px] text-secondary" aria-live="polite">
                <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                {Math.round(previewRequestState.progress_percent)}% · {previewRequestState.message}
              </p>
            ) : null}
            {previewSrc && previewMatchesCurrentSelection ? (
              <div className="mt-3 flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <AudioPlayer ref={previewAudioRef} src={previewSrc} onError={handlePreviewAudioLoadError} />
                </div>
                <button
                  type="button"
                  onClick={() => void handleDeletePreview()}
                  aria-label="Delete preview"
                  title="Delete preview"
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-red-500/10 hover:text-red-600 dark:hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ) : null}
          </section>
        ) : null}

        <p className="mt-8 flex flex-wrap items-center gap-1.5 border-t border-outline pt-4 text-[12px] text-secondary">
          <span className={cn("h-2 w-2 shrink-0 rounded-full", localEngineReady ? "bg-emerald-500" : "bg-amber-500")} aria-hidden />
          <span className="min-w-0 truncate">Speech engine: {engineLabel} · {engineStatus}</span>
          <button type="button" onClick={() => navigate("/models")} className="text-primary underline underline-offset-2">
            Models
          </button>
        </p>
      </div>

      {referenceDialogMode ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center theme-modal-overlay backdrop-blur-sm px-4 py-6">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="speaker-reference-dialog-title"
            className="flex max-h-full w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-outline theme-modal-surface shadow-xl"
          >
            <div className="flex shrink-0 items-start justify-between gap-4 border-b border-outline px-6 py-4">
              <div className="min-w-0">
                <h2 id="speaker-reference-dialog-title" className="text-[16px] font-semibold text-primary">
                  {referenceDialogMode === "create" ? "New voice" : "Edit voice"}
                </h2>
                <p className="mt-1 text-[12px] leading-relaxed text-secondary">
                  {referenceDialogMode === "create"
                    ? "Add a 10–30 second sample and type exactly what is said in it."
                    : "Change the name, language, or transcript. Upload or record again to replace the sample."}
                </p>
              </div>
              <button
                type="button"
                onClick={resetReferenceDialog}
                className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-primary/5 hover:text-primary"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 mac-scrollbar">
              <div className="grid gap-4">
                <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
                  <label className="flex flex-col gap-1.5 text-[13px] font-medium text-primary">
                    Name
                    <input
                      value={newReferenceName}
                      onChange={(event) => setNewReferenceName(event.target.value)}
                      className={cn(fieldClass, "h-9 font-normal")}
                      placeholder="My storytelling voice"
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-[13px] font-medium text-primary">
                    Language
                    <input
                      value={newReferenceLanguage}
                      onChange={(event) => setNewReferenceLanguage(event.target.value)}
                      className={cn(fieldClass, "h-9 font-normal")}
                      placeholder="zh, en, yue"
                    />
                  </label>
                </div>

                <div>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[13px] font-medium text-primary">Sample</p>
                    <div className="inline-flex rounded-lg border border-outline p-0.5" role="group" aria-label="Sample source">
                      {([
                        { id: "upload", label: "Upload", icon: Upload },
                        { id: "microphone", label: "Record", icon: Mic },
                      ] as const).map(({ id, label, icon: Icon }) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => setReferenceAudioSource(id)}
                          aria-pressed={referenceAudioSource === id}
                          className={segmentClass(referenceAudioSource === id)}
                        >
                          <Icon className="h-3.5 w-3.5" />
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                  {referenceAudioSource === "upload" ? (
                    <div className="mt-2 rounded-lg border border-dashed border-outline px-4 py-4 text-center">
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
                        className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-outline px-3 text-[13px] font-medium text-primary transition-colors hover:bg-primary/5"
                      >
                        <Upload className="h-4 w-4" />
                        Choose audio file
                      </button>
                      <p className="mt-2 text-[12px] text-secondary">WAV, MP3, M4A, MP4, AAC, FLAC, WebM or OGG · up to 10 minutes</p>
                    </div>
                  ) : (
                    <div className="mt-2 flex flex-col items-center gap-2 rounded-lg border border-outline px-4 py-4">
                      <button
                        type="button"
                        onClick={() => (recordingReferenceSample ? handleStopReferenceRecording() : void handleStartReferenceRecording())}
                        className={cn(
                          "inline-flex h-9 items-center gap-1.5 rounded-lg px-3.5 text-[13px] font-semibold transition-colors",
                          recordingReferenceSample
                            ? "bg-red-500/10 text-red-700 dark:text-red-300"
                            : "bg-primary text-background",
                        )}
                      >
                        {recordingReferenceSample ? <Square className="h-3.5 w-3.5 fill-current" /> : <Mic className="h-4 w-4" />}
                        {recordingReferenceSample ? "Stop recording" : "Start recording"}
                      </button>
                      <p className="text-[12px] text-secondary">
                        {recordingReferenceSample ? "Recording…" : "The recording becomes the sample when you stop. Up to 10 minutes."}
                      </p>
                    </div>
                  )}
                  {referenceDialogMode === "edit" && existingReferenceAudioUrl && !newReferenceAudioPreviewUrl ? (
                    <div className="mt-2">
                      <p className="mb-1 text-[12px] text-secondary">Current sample</p>
                      <audio controls src={existingReferenceAudioUrl} className="w-full" />
                    </div>
                  ) : null}
                  {newReferenceAudioPreviewUrl ? (
                    <div className="mt-2">
                      <p className="mb-1 truncate text-[12px] text-secondary">{newReferenceAudioFileName || "New sample"}</p>
                      <audio controls src={newReferenceAudioPreviewUrl} className="w-full" />
                    </div>
                  ) : null}
                </div>

                <label className="flex flex-col gap-1.5 text-[13px] font-medium text-primary">
                  Transcript
                  <textarea
                    value={newReferenceText}
                    onChange={(event) => setNewReferenceText(event.target.value)}
                    rows={4}
                    className={cn(fieldClass, "resize-none py-2 font-normal leading-relaxed")}
                    placeholder="Exactly what is said in the sample"
                  />
                </label>
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-outline px-6 py-3">
              {referenceDialogMode === "edit" ? (
                <button
                  type="button"
                  onClick={() => {
                    const reference = speakerReferences.find((item) => item.speaker_reference_id === editingReferenceId);
                    if (reference) setReferenceToDelete(reference);
                  }}
                  disabled={savingReference}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-red-700 transition-colors hover:bg-red-500/10 disabled:opacity-50 dark:text-red-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </button>
              ) : (
                <span />
              )}
              <div className="ml-auto flex items-center gap-1">
                <button
                  type="button"
                  onClick={resetReferenceDialog}
                  className="inline-flex h-9 items-center rounded-lg px-3 text-[13px] font-medium text-primary transition-colors hover:bg-primary/5"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleSaveSpeakerReference()}
                  disabled={savingReference || recordingReferenceSample}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-[13px] font-semibold text-background transition-opacity disabled:opacity-40"
                >
                  {savingReference ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {referenceDialogMode === "create"
                    ? canApplyReferenceToScript
                      ? "Create and use"
                      : "Create voice"
                    : "Save"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      <ConfirmDialog
        open={referenceToDelete !== null}
        title="Delete this voice?"
        message={
          referenceToDelete
            ? `Delete “${referenceToDelete.name}”? Voices still used by a script or rendered audio can't be deleted.`
            : ""
        }
        onClose={() => setReferenceToDelete(null)}
        actions={[
          { label: "Cancel", onClick: () => setReferenceToDelete(null) },
          {
            label: "Delete",
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
            className="max-w-md rounded-xl border border-outline bg-modal px-4 py-2.5 text-[13px] font-medium text-primary shadow-lg"
          >
            {message}
          </p>
        </div>
      ) : null}
    </div>
  );
}
