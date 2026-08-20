import { useEffect, useMemo, useState } from "react";
import type { DesktopBridge } from "../../lib/desktopBridge";
import { getErrorMessage } from "../../lib/requestState";
import type { ModelStatus, SessionProject, SpeakerReference, TTSCapability, TTSProviderConfig } from "../../types";
import { estimateWordCount, formatEstimateMinutes, formatSessionState } from "./workbenchUtils";

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
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [voiceSelectionError, setVoiceSelectionError] = useState<string | null>(null);
  const [selectedEngine, setSelectedEngine] = useState<"local_mlx" | "cloud">("cloud");
  const [loading, setLoading] = useState(true);
  const [loadingError, setLoadingError] = useState<string | null>(null);

  const reload = async () => {
    const [loadedProject, loadedCapability, loadedConfig, loadedReferences, loadedModels] = await Promise.all([
      bridge.showScript(sessionId, scriptId),
      bridge.getLocalTTSCapability(),
      bridge.showTTSConfig(),
      bridge.listSpeakerReferences(),
      bridge.listModelsStatus(),
    ]);
    setProject(loadedProject);
    setScript(loadedProject.script?.final || loadedProject.script?.draft || "");
    setCapability(loadedCapability);
    setTtsConfig(loadedConfig);
    setSpeakerReferences(loadedReferences);
    setModels(loadedModels);
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

  useEffect(() => {
    const defaultEngine = ttsConfig?.provider === "local_mlx" ? "local_mlx" : capability?.available ? "local_mlx" : "cloud";
    setSelectedEngine(defaultEngine);
  }, [capability?.available, ttsConfig?.provider]);

  useEffect(() => {
    const configured = ttsConfig?.model?.trim() || "";
    const rendered = project?.render_manifest?.pipeline.find((stage) => stage.stage === "speech_synthesis")?.model || "";
    const firstReady = models.find((model) => model.downloaded && model.available !== false)?.hf_repo_id
      ?? models.find((model) => model.downloaded && model.available !== false)?.model_name
      ?? "";
    const modelIsReady = (modelId: string) => models.some(
      (model) => (model.hf_repo_id === modelId || model.model_name === modelId)
        && model.downloaded
        && model.available !== false,
    );
    setSelectedModelId((current) => {
      if (current && modelIsReady(current)) return current;
      return modelIsReady(configured) ? configured : modelIsReady(rendered) ? rendered : firstReady;
    });
  }, [models, project?.render_manifest?.render_id, ttsConfig?.model]);

  const cloudProvider = useMemo(() => {
    const configuredProvider = ttsConfig?.provider?.trim();
    if (configuredProvider && configuredProvider !== "local_mlx") {
      return configuredProvider;
    }
    return capability?.fallback_provider || "mock_remote";
  }, [capability?.fallback_provider, ttsConfig?.provider]);

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
  const sessionStateLabel = formatSessionState(project?.session.state);

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
    models,
    selectedModelId,
    setSelectedModelId,
    voiceSelectionError,
    selectedEngine,
    setSelectedEngine,
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
    sessionStateLabel,
    handleSelectSpeakerReference,
  };
}
