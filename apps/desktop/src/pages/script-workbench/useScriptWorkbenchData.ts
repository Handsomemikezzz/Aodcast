import { useEffect, useMemo, useState } from "react";
import type { DesktopBridge } from "../../lib/desktopBridge";
import { getErrorMessage } from "../../lib/requestState";
import {
  modelId,
  modelMode,
  readyModelForMode,
  renderedSpeechModel,
  resolveProjectVoiceSettings,
} from "../../lib/voiceSettings";
import type {
  LocalVoiceMode,
  ModelStatus,
  SessionProject,
  SpeakerReference,
  TTSCapability,
  TTSProviderConfig,
  VoicePreset,
  VoiceRenderSettings,
  VoiceStylePreset,
} from "../../types";
import { estimateWordCount, formatEstimateMinutes } from "./workbenchUtils";

type UseScriptWorkbenchDataArgs = {
  bridge: DesktopBridge;
  sessionId: string;
  scriptId: string;
  onRefresh: () => Promise<void>;
};

export function useScriptWorkbenchData({ bridge, sessionId, scriptId, onRefresh }: UseScriptWorkbenchDataArgs) {
  const [project, setProject] = useState<SessionProject | null>(null);
  const [script, setScript] = useState("");
  const [capability, setCapability] = useState<TTSCapability | null>(null);
  const [ttsConfig, setTtsConfig] = useState<TTSProviderConfig | null>(null);
  const [speakerReferences, setSpeakerReferences] = useState<SpeakerReference[]>([]);
  const [voicePresets, setVoicePresets] = useState<VoicePreset[]>([]);
  // Selection overrides stay null until the user changes them, so the first loaded render already
  // reflects the saved voice and configured engine instead of transient defaults.
  const [presetVoiceOverride, setSelectedPresetVoiceId] = useState<string | null>(null);
  const [voiceStyles, setVoiceStyles] = useState<VoiceStylePreset[]>([]);
  const [models, setModels] = useState<ModelStatus[]>([]);
  // The user's explicit model choice; null follows the rendered/selected voice.
  const [modelOverride, setSelectedModelId] = useState<string | null>(null);
  const [voiceSelectionError, setVoiceSelectionError] = useState<string | null>(null);
  const [engineOverride, setSelectedEngine] = useState<"local_http" | "cloud" | null>(null);
  const [styleOverride, setSelectedStyleId] = useState<string | null>(null);
  const [speedOverride, setDeliverySpeed] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingError, setLoadingError] = useState<string | null>(null);

  const reload = async () => {
    const [loadedProject, loadedCapability, loadedConfig, loadedReferences, loadedModels, voiceCatalog] = await Promise.all([
      bridge.showScript(sessionId, scriptId),
      bridge.getLocalTTSCapability(),
      bridge.showTTSConfig(),
      bridge.listSpeakerReferences(),
      bridge.listModelsStatus(),
      bridge.listVoicePresets(),
    ]);
    setProject(loadedProject);
    setScript(loadedProject.script?.final || loadedProject.script?.draft || "");
    setCapability(loadedCapability);
    setTtsConfig(loadedConfig);
    setSpeakerReferences(loadedReferences);
    setModels(loadedModels);
    setVoiceStyles(voiceCatalog.styles);
    setVoicePresets(voiceCatalog.voices);
  };

  const refreshWorkspace = async () => {
    await Promise.allSettled([reload(), onRefresh()]);
  };

  const refreshProject = async () => {
    const loadedProject = await bridge.showScript(sessionId, scriptId);
    setProject(loadedProject);
    return loadedProject;
  };

  useEffect(() => {
    const loadWorkspace = async () => {
      try {
        setLoading(true);
        setLoadingError(null);
        await reload();
      } catch (err: unknown) {
        setLoadingError(getErrorMessage(err, "Failed to load the script workspace."));
      } finally {
        setLoading(false);
      }
    };

    void loadWorkspace();
  }, [bridge, sessionId, scriptId]);

  const selectedEngine = engineOverride ?? (ttsConfig?.provider === "local_http" ? "local_http" : "cloud");

  useEffect(() => {
    setSelectedEngine(null);
  }, [capability?.available, ttsConfig?.provider]);

  const renderedModel = renderedSpeechModel(project);
  const hasScriptReference = Boolean(
    (project?.artifact?.script_artifacts?.[scriptId]?.speaker_reference ?? project?.artifact?.speaker_reference)
      ?.speaker_reference_id,
  );
  // The model is chosen first; its declared capability decides whether the script speaks a
  // preset voice or a cloned Speaker Reference. Without an explicit choice, keep the model that
  // rendered the current audio, else a selected reference implies the default cloning model.
  const selectedModel = useMemo(() => {
    const ready = models.filter((model) => model.ready === true && model.available !== false);
    const byId = (id: string | null) => (id ? ready.find((model) => modelId(model) === id) : undefined);
    const rendered = byId(renderedModel);
    const followReference = hasScriptReference
      ? readyModelForMode(models, "clone", rendered && modelMode(rendered) === "clone" ? modelId(rendered) : "")
      : rendered;
    return byId(modelOverride)
      ?? followReference
      ?? readyModelForMode(models, "preset", ttsConfig?.model?.trim() || "");
  }, [models, modelOverride, renderedModel, hasScriptReference, ttsConfig?.model]);
  const selectedModelId = selectedModel ? modelId(selectedModel) : "";
  const localVoiceMode: LocalVoiceMode = modelMode(selectedModel);

  useEffect(() => {
    setSelectedModelId(null);
  }, [scriptId]);

  const savedVoiceSettings = resolveProjectVoiceSettings(project, scriptId);

  const selectedPresetVoiceId = presetVoiceOverride ?? savedVoiceSettings.voice_id;
  const selectedStyleId = styleOverride ?? (savedVoiceSettings.style_id || "natural");
  const deliverySpeed = speedOverride ?? (savedVoiceSettings.speed || 1);

  useEffect(() => {
    setSelectedPresetVoiceId(null);
  }, [scriptId, savedVoiceSettings.voice_id]);

  useEffect(() => {
    setSelectedStyleId(null);
    setDeliverySpeed(null);
  }, [scriptId, savedVoiceSettings.speed, savedVoiceSettings.style_id]);

  const cloudProvider = useMemo(() => {
    const configuredProvider = ttsConfig?.provider?.trim();
    if (configuredProvider && configuredProvider !== "local_http") {
      return configuredProvider;
    }
    return "openai_compatible";
  }, [ttsConfig?.provider]);

  const serverScript = project?.script?.final || project?.script?.draft || "";
  const isScriptDeleted = Boolean(project?.script?.deleted_at);
  const isSessionDeleted = Boolean(project?.session.deleted_at);
  const isDirty = !isScriptDeleted && !isSessionDeleted && script !== serverScript;
  const wordCount = useMemo(() => estimateWordCount(script), [script]);
  const estMinutes = useMemo(() => formatEstimateMinutes(wordCount), [wordCount]);
  const topic = project?.session.topic || "Untitled Project";
  const scriptName = project?.script?.name || topic;
  const updatedAt = project?.script?.updated_at || project?.session.updated_at || "";
  const outputFilename = (project?.render_manifest?.output.audio_path || project?.artifact?.audio_path || "").split("/").pop() || "";
  const voiceSettings = useMemo<VoiceRenderSettings>(() => {
    const selectedStyle = voiceStyles.find((style) => style.style_id === selectedStyleId);
    return {
      ...savedVoiceSettings,
      ...(selectedEngine === "local_http" ? { voice_id: selectedPresetVoiceId, voice_name: voicePresets.find((voice) => voice.voice_id === selectedPresetVoiceId)?.name || selectedPresetVoiceId, audio_format: "wav" } : {}),
      style_id: selectedEngine === "local_http" ? "natural" : selectedStyleId || "natural",
      style_name: selectedEngine === "local_http" ? "Natural" : selectedStyle?.name || savedVoiceSettings.style_name || "Natural",
      speed: selectedEngine === "local_http" ? 1 : deliverySpeed,
    };
  }, [deliverySpeed, savedVoiceSettings, selectedStyleId, voiceStyles, selectedEngine, selectedPresetVoiceId, voicePresets]);

  const handleSelectSpeakerReference = async (referenceId: string) => {
    const selectedScriptId = project?.script?.script_id || scriptId;
    if (!selectedScriptId) return;
    try {
      setVoiceSelectionError(null);
      const updatedProject = await bridge.selectSpeakerReference(sessionId, selectedScriptId, referenceId);
      setProject(updatedProject);
      await onRefresh();
    } catch (err: unknown) {
      setVoiceSelectionError(getErrorMessage(err, "Failed to select speaker reference."));
    }
  };

  return {
    project,
    setProject,
    script,
    setScript,
    capability,
    ttsConfig,
    speakerReferences,
    voiceStyles,
    voicePresets,
    selectedPresetVoiceId,
    setSelectedPresetVoiceId,
    models,
    selectedModelId,
    setSelectedModelId,
    localVoiceMode,
    voiceSelectionError,
    selectedEngine,
    setSelectedEngine,
    selectedStyleId,
    setSelectedStyleId,
    deliverySpeed,
    setDeliverySpeed,
    voiceSettings,
    loading,
    loadingError,
    reload,
    refreshProject,
    refreshWorkspace,
    cloudProvider,
    isScriptDeleted,
    isSessionDeleted,
    isDirty,
    topic,
    scriptName,
    updatedAt,
    wordCount,
    estMinutes,
    outputFilename,
    handleSelectSpeakerReference,
  };
}
