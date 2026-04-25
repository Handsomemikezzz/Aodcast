import { useEffect, useMemo, useState } from "react";
import type { DesktopBridge } from "../../lib/desktopBridge";
import { getErrorMessage } from "../../lib/requestState";
import type { SessionProject, TTSCapability, TTSProviderConfig } from "../../types";
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
  const [selectedEngine, setSelectedEngine] = useState<"local_mlx" | "cloud">("cloud");
  const [loading, setLoading] = useState(true);
  const [loadingError, setLoadingError] = useState<string | null>(null);

  const reload = async () => {
    const [loadedProject, loadedCapability, loadedConfig] = await Promise.all([
      bridge.showScript(sessionId, scriptId),
      bridge.getLocalTTSCapability(),
      bridge.showTTSConfig(),
    ]);
    setProject(loadedProject);
    setScript(loadedProject.script?.final || loadedProject.script?.draft || "");
    setCapability(loadedCapability);
    setTtsConfig(loadedConfig);
  };

  const refreshWorkspace = async () => {
    await Promise.allSettled([reload(), onRefresh()]);
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
  const outputFilename = project?.artifact?.audio_path?.split("/").pop() || "";
  const sessionStateLabel = formatSessionState(project?.session.state);

  return {
    project,
    setProject,
    script,
    setScript,
    capability,
    ttsConfig,
    selectedEngine,
    setSelectedEngine,
    loading,
    loadingError,
    reload,
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
  };
}
