import { useCallback, useEffect, useState } from "react";
import { Loader2, Check, AlertCircle, RotateCw } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useBridge } from "../lib/BridgeContext";
import { LLMProviderConfig, LLMProviderStatus, RequestState, TTSProviderConfig } from "../types";
import { cn } from "../lib/utils";
import { openExternalUrl } from "../lib/shellOps";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  withRequestStateFallback,
} from "../lib/requestState";

type LLMForm = {
  provider: string;
  model: string;
  reasoning_effort: string;
  base_url: string;
  api_key: string;
};

type TTSForm = {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  voice: string;
  audio_format: string;
};

type LLMPreset = {
  id: string;
  name: string;
  provider: string;
  baseUrl: string;
  defaultModels: string[];
};

const LLM_PRESETS: LLMPreset[] = [
  {
    id: "chatgpt-subscription",
    name: "ChatGPT subscription (via Codex)",
    provider: "codex_subscription",
    baseUrl: "",
    defaultModels: [],
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    provider: "openai_compatible",
    baseUrl: "https://api.deepseek.com/v1",
    defaultModels: ["deepseek-v4-flash", "deepseek-v4-pro"],
  },
  {
    id: "openai",
    name: "OpenAI",
    provider: "openai_compatible",
    baseUrl: "https://api.openai.com/v1",
    defaultModels: ["gpt-5.5-instant", "gpt-5.4-mini", "gpt-5.4-pro"],
  },
  {
    id: "anthropic",
    name: "Anthropic Claude (via proxy)",
    provider: "openai_compatible",
    baseUrl: "https://api.anthropic.com/v1",
    defaultModels: ["claude-sonnet-4.6", "claude-opus-4.8"],
  },
  {
    id: "ollama",
    name: "Ollama (Local)",
    provider: "openai_compatible",
    baseUrl: "http://localhost:11434",
    defaultModels: ["qwen2.5", "llama3"],
  },
  {
    id: "siliconflow",
    name: "SiliconFlow",
    provider: "openai_compatible",
    baseUrl: "https://api.siliconflow.cn/v1",
    defaultModels: [
      "Qwen/Qwen2.5-72B-Instruct",
      "deepseek-ai/DeepSeek-V3",
      "meta-llama/Llama-3.3-70B-Instruct"
    ],
  },
  {
    id: "mock",
    name: "Mock (Demo & Testing Mode)",
    provider: "mock",
    baseUrl: "",
    defaultModels: ["mock-model"],
  },
  {
    id: "custom",
    name: "Custom (OpenAI Compatible)",
    provider: "openai_compatible",
    baseUrl: "",
    defaultModels: [],
  },
];

const REASONING_EFFORT_LABELS: Record<string, string> = {
  none: "None",
  minimal: "Minimal",
  low: "Low",
  medium: "Medium",
  high: "High",
  xhigh: "Extra high",
  max: "Maximum",
  ultra: "Ultra",
};

function reasoningEffortLabel(value: string): string {
  return REASONING_EFFORT_LABELS[value] ?? value;
}

function toLLMForm(config: LLMProviderConfig): LLMForm {
  return {
    provider: config.provider,
    model: config.model,
    reasoning_effort: config.reasoning_effort || "auto",
    base_url: config.base_url,
    api_key: config.api_key,
  };
}

function toTTSForm(config: TTSProviderConfig): TTSForm {
  return {
    provider: config.provider,
    model: config.model,
    base_url: config.base_url,
    api_key: config.api_key,
    voice: config.voice,
    audio_format: config.audio_format,
  };
}

export function SettingsPage() {
  const bridge = useBridge();
  const navigate = useNavigate();

  const [llmForm, setLlmForm] = useState<LLMForm>({
    provider: "openai_compatible",
    model: "",
    reasoning_effort: "auto",
    base_url: "",
    api_key: "",
  });

  const [ttsForm, setTtsForm] = useState<TTSForm>({
    provider: "local_http",
    model: "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit",
    base_url: "http://127.0.0.1:8090/v1",
    api_key: "",
    voice: "默认中文音色",
    audio_format: "wav",
  });

  // UI state managers
  const [loading, setLoading] = useState(true);
  const [savingLlm, setSavingLlm] = useState(false);
  const [savingTts, setSavingTts] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [savedFlashLlm, setSavedFlashLlm] = useState(false);
  const [savedFlashTts, setSavedFlashTts] = useState(false);
  const [, setRequestState] = useState<RequestState | null>(null);

  // Connection testing states
  const [testingLlm, setTestingLlm] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [llmProviderStatus, setLlmProviderStatus] = useState<LLMProviderStatus | null>(null);
  const [loadingLlmProviderStatus, setLoadingLlmProviderStatus] = useState(false);
  const [startingLlmLogin, setStartingLlmLogin] = useState(false);
  const [llmLoginPending, setLlmLoginPending] = useState(false);
  const [pendingLlmAuthUrl, setPendingLlmAuthUrl] = useState("");
  
  const [testingTts, setTestingTts] = useState(false);
  const [ttsTestResult, setTtsTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Preset & Dual-mode custom state
  const [selectedLlmPreset, setSelectedLlmPreset] = useState("custom");
  const [customModelActive, setCustomModelActive] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        setError(null);
        const [llm, tts] = await Promise.all([bridge.showLLMConfig(), bridge.showTTSConfig()]);
        if (!active) return;
        
        const lf = toLLMForm(llm);
        setLlmForm(lf);
        setTtsForm(toTTSForm(tts));

        // Infer preset
        let matchedPreset = "custom";
        if (lf.provider === "mock") {
          matchedPreset = "mock";
        } else if (lf.provider === "codex_subscription") {
          matchedPreset = "chatgpt-subscription";
        } else {
          const match = LLM_PRESETS.find(
            (p) => p.baseUrl && lf.base_url.toLowerCase().startsWith(p.baseUrl.toLowerCase())
          );
          if (match) matchedPreset = match.id;
        }
        setSelectedLlmPreset(matchedPreset);

        // Infer custom model active
        const activePresetConfig = LLM_PRESETS.find((p) => p.id === matchedPreset);
        if (activePresetConfig && activePresetConfig.id !== "custom" && activePresetConfig.id !== "mock") {
          const isPresetModel = activePresetConfig.defaultModels.includes(lf.model);
          setCustomModelActive(!isPresetModel);
        } else {
          setCustomModelActive(true);
        }
      } catch (e) {
        if (!active) return;
        setError(getErrorMessage(e, "Failed to load settings."));
        setRequestState(getErrorRequestState(e));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [bridge]);

  const refreshLlmProviderStatus = useCallback(async () => {
    setLoadingLlmProviderStatus(true);
    try {
      const status = await bridge.showLLMProviderStatus();
      setLlmProviderStatus(status);
      if (status.authenticated && status.models.length > 0) {
        setLlmForm((prev) => {
          if (prev.provider !== "codex_subscription") return prev;
          const available = new Set(status.models.map((model) => model.id));
          const selectedModel = prev.model && available.has(prev.model)
            ? status.models.find((model) => model.id === prev.model)!
            : status.models.find((model) => model.is_default) ?? status.models[0];
          const reasoningEffort = prev.reasoning_effort !== "auto"
            && !selectedModel.supported_reasoning_efforts.includes(prev.reasoning_effort)
            ? "auto"
            : prev.reasoning_effort;
          if (selectedModel.id === prev.model && reasoningEffort === prev.reasoning_effort) return prev;
          return { ...prev, model: selectedModel.id, reasoning_effort: reasoningEffort };
        });
        setLlmLoginPending(false);
        setPendingLlmAuthUrl("");
      }
      return status;
    } catch (e) {
      setLlmTestResult({
        success: false,
        message: getErrorMessage(e, "Failed to read Codex subscription status."),
      });
      return null;
    } finally {
      setLoadingLlmProviderStatus(false);
    }
  }, [bridge]);

  useEffect(() => {
    if (selectedLlmPreset !== "chatgpt-subscription") return;
    void refreshLlmProviderStatus();
  }, [refreshLlmProviderStatus, selectedLlmPreset]);

  useEffect(() => {
    if (!llmLoginPending) return;
    const interval = window.setInterval(() => {
      void refreshLlmProviderStatus();
    }, 1500);
    const timeout = window.setTimeout(() => {
      setLlmLoginPending(false);
      setPendingLlmAuthUrl("");
    }, 5 * 60 * 1000);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(timeout);
    };
  }, [llmLoginPending, refreshLlmProviderStatus]);

  const updateLlm = <K extends keyof LLMForm>(key: K, value: LLMForm[K]) => {
    setLlmForm((prev) => ({ ...prev, [key]: value }));
  };

  const updateTts = <K extends keyof TTSForm>(key: K, value: TTSForm[K]) => {
    setTtsForm((prev) => ({ ...prev, [key]: value }));
  };

  // Handle Preset Selection Change
  const handlePresetChange = (presetId: string) => {
    setSelectedLlmPreset(presetId);
    setLlmTestResult(null);
    const preset = LLM_PRESETS.find((p) => p.id === presetId);
    if (!preset) return;

    if (preset.id === "chatgpt-subscription") {
      setCustomModelActive(false);
      setLlmForm((prev) => ({
        ...prev,
        provider: "codex_subscription",
        model: llmProviderStatus?.models.find((model) => model.is_default)?.id
          ?? llmProviderStatus?.models[0]?.id
          ?? "",
        reasoning_effort: "auto",
        base_url: "",
        api_key: "",
      }));
    } else if (preset.id === "custom") {
      setCustomModelActive(true);
      updateLlm("provider", "openai_compatible");
      updateLlm("base_url", "");
      updateLlm("model", "");
    } else if (preset.id === "mock") {
      setCustomModelActive(false);
      updateLlm("provider", "mock");
      updateLlm("base_url", "");
      updateLlm("model", "mock-model");
    } else {
      setCustomModelActive(false);
      updateLlm("provider", preset.provider);
      updateLlm("base_url", preset.baseUrl);
      updateLlm("model", preset.defaultModels[0] || "");
    }
  };

  const handleStartCodexLogin = async () => {
    setStartingLlmLogin(true);
    setLlmTestResult(null);
    setPendingLlmAuthUrl("");
    try {
      const login = await bridge.startLLMProviderLogin("codex_subscription");
      setPendingLlmAuthUrl(login.auth_url);
      setLlmLoginPending(true);
      try {
        await openExternalUrl(login.auth_url);
        setLlmTestResult({
          success: true,
          message: "Complete the ChatGPT sign-in in your browser. Aodcast will detect it automatically.",
        });
      } catch (openError) {
        setLlmTestResult({
          success: false,
          message: getErrorMessage(openError, "Open the ChatGPT sign-in link shown below."),
        });
      }
    } catch (e) {
      setLlmTestResult({
        success: false,
        message: getErrorMessage(e, "Failed to start ChatGPT sign-in."),
      });
    } finally {
      setStartingLlmLogin(false);
    }
  };

  const handleTestLlm = async () => {
    setTestingLlm(true);
    setLlmTestResult(null);
    try {
      const res = await bridge.testLLMConnection({
        provider: llmForm.provider,
        model: llmForm.model,
        reasoning_effort: llmForm.reasoning_effort,
        base_url: llmForm.base_url,
        api_key: llmForm.api_key,
      });
      setLlmTestResult({ success: true, message: res.message });
    } catch (e) {
      setLlmTestResult({
        success: false,
        message: e instanceof Error ? e.message : "Connection verification failed."
      });
    } finally {
      setTestingLlm(false);
    }
  };

  const handleTestTts = async () => {
    setTestingTts(true);
    setTtsTestResult(null);
    try {
      const res = await bridge.testTTSConnection({
        provider: ttsForm.provider,
        model: ttsForm.model,
        base_url: ttsForm.base_url,
        api_key: ttsForm.api_key,
        voice: ttsForm.voice,
        audio_format: ttsForm.audio_format,
      });
      setTtsTestResult({ success: true, message: res.message });
    } catch (e) {
      setTtsTestResult({
        success: false,
        message: e instanceof Error ? e.message : "TTS Verification failed."
      });
    } finally {
      setTestingTts(false);
    }
  };

  const handleSaveLlm = async () => {
    setSavingLlm(true);
    setError(null);
    setRequestState({
      operation: "configure_llm_provider",
      phase: "running",
      progress_percent: 0,
      message: "Saving LLM settings...",
    });
    try {
      const next = await bridge.configureLLMProvider({
        provider: llmForm.provider,
        model: llmForm.model,
        reasoning_effort: llmForm.reasoning_effort,
        base_url: llmForm.base_url,
        api_key: llmForm.api_key,
      });
      setLlmForm(toLLMForm(next));
      setRequestState({
        operation: "configure_llm_provider",
        phase: "succeeded",
        progress_percent: 100,
        message: "LLM settings saved.",
      });
      setSavedFlashLlm(true);
      window.setTimeout(() => setSavedFlashLlm(false), 2000);
    } catch (e) {
      setError(getErrorMessage(e, "Failed to save LLM settings."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(e),
          buildRequestState("configure_llm_provider", "failed", "Failed to save LLM settings."),
        ),
      );
    } finally {
      setSavingLlm(false);
    }
  };

  const handleSaveTts = async () => {
    setSavingTts(true);
    setError(null);
    setRequestState({
      operation: "configure_tts_provider",
      phase: "running",
      progress_percent: 0,
      message: "Saving TTS settings...",
    });
    try {
      const next = await bridge.configureTTSProvider({
        provider: ttsForm.provider,
        model: ttsForm.model,
        base_url: ttsForm.base_url,
        api_key: ttsForm.api_key,
        voice: ttsForm.voice,
        audio_format: ttsForm.audio_format,
      });
      setTtsForm(toTTSForm(next));
      setRequestState({
        operation: "configure_tts_provider",
        phase: "succeeded",
        progress_percent: 100,
        message: "TTS settings saved.",
      });
      setSavedFlashTts(true);
      window.setTimeout(() => setSavedFlashTts(false), 2000);
    } catch (e) {
      setError(getErrorMessage(e, "Failed to save TTS settings."));
      setRequestState(
        withRequestStateFallback(
          getErrorRequestState(e),
          buildRequestState("configure_tts_provider", "failed", "Failed to save TTS settings."),
        ),
      );
    } finally {
      setSavingTts(false);
    }
  };

  const currentPresetConfig = LLM_PRESETS.find((p) => p.id === selectedLlmPreset);
  const isCodexSubscription = llmForm.provider === "codex_subscription";
  const codexReady = Boolean(
    llmProviderStatus?.installed
    && llmProviderStatus.authenticated
    && llmProviderStatus.models.length > 0,
  );
  const selectedCodexModel = llmProviderStatus?.models.find(
    (model) => model.id === llmForm.model,
  ) ?? null;
  const ttsUsesLocalModels = ttsForm.provider === "local_http";

  const inputClass =
    "h-9 w-full rounded-lg border border-outline bg-transparent px-3 text-[13px] text-primary placeholder:text-secondary/60 outline-none focus:border-primary/25 disabled:opacity-50";
  const labelClass = "mb-1.5 block text-[13px] font-medium text-primary";
  const primaryButtonClass =
    "inline-flex h-9 items-center rounded-lg bg-primary px-3.5 text-[13px] font-semibold text-background transition-opacity disabled:opacity-40";
  const secondaryButtonClass =
    "inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-primary transition-colors hover:bg-primary/5 disabled:opacity-40";

  const renderTestResult = (result: { success: boolean; message: string } | null) =>
    result ? (
      <p
        role="status"
        className={cn(
          "flex items-start gap-2 text-[13px] leading-relaxed",
          result.success ? "text-emerald-700 dark:text-emerald-300" : "text-red-700 dark:text-red-300",
        )}
      >
        {result.success ? <Check className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
        <span className="select-all">{result.message}</span>
      </p>
    ) : null;

  return (
    <div className="h-full overflow-y-auto px-6 py-8 lg:px-10 mac-scrollbar">
      <div className="mx-auto w-full max-w-2xl">
        <h1 className="text-2xl font-headline font-semibold text-primary">Settings</h1>
        <p className="mt-1 text-sm text-secondary">
          Choose the language model that runs interviews and scripts, and the speech engine that reads them.
        </p>

        {error ? (
          <div role="alert" className="mt-6 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-[13px] text-red-700 dark:text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        {loading ? (
          <div className="flex items-center gap-2 py-16 text-sm text-secondary">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading settings…
          </div>
        ) : (
          <>
            <section className="mt-8 space-y-5 border-t border-outline pt-6">
              <h2 className="text-[15px] font-semibold text-primary">Language model</h2>

              <label className="block">
                <span className={labelClass}>Provider</span>
                <select value={selectedLlmPreset} onChange={(e) => handlePresetChange(e.target.value)} className={inputClass}>
                  {LLM_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>{preset.name}</option>
                  ))}
                </select>
              </label>

              {isCodexSubscription && (
                <div className="space-y-3 rounded-xl border border-outline p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 text-[13px]">
                      <p className="font-medium text-primary">
                        {llmProviderStatus?.authenticated
                          ? `ChatGPT ${llmProviderStatus.plan_type || "connected"}`
                          : llmProviderStatus?.installed === false
                            ? "Codex CLI not installed"
                            : "ChatGPT not connected"}
                      </p>
                      <p className="mt-0.5 truncate text-[12px] text-secondary">
                        {[
                          llmProviderStatus?.account_email,
                          llmProviderStatus?.installed ? `Codex ${llmProviderStatus.version || "installed"}` : null,
                        ].filter(Boolean).join(" · ") || "Checking the local Codex installation…"}
                      </p>
                    </div>
                    {loadingLlmProviderStatus ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-secondary" />
                    ) : llmProviderStatus?.authenticated ? (
                      <Check className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <AlertCircle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                    )}
                  </div>

                  {llmProviderStatus?.rate_limit && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[12px] text-secondary">
                        <span>Codex usage window</span>
                        <span>{Math.round(llmProviderStatus.rate_limit.used_percent)}% used</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-primary/10">
                        <div
                          className="h-full rounded-full bg-accent-amber transition-[width]"
                          style={{ width: `${Math.min(100, llmProviderStatus.rate_limit.used_percent)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  <p className="text-[12px] leading-relaxed text-secondary">
                    Uses the ChatGPT account signed in to the official Codex CLI and its plan allowance — never API billing.
                    Aodcast doesn't read or store Codex tokens.
                  </p>
                  {!llmProviderStatus?.installed && !loadingLlmProviderStatus && (
                    <code className="block rounded-lg bg-primary/5 px-3 py-2 font-mono text-[12px] text-primary select-all">
                      npm install -g @openai/codex
                    </code>
                  )}

                  <div className="flex flex-wrap items-center gap-1">
                    {!llmProviderStatus?.authenticated && (
                      <button
                        type="button"
                        onClick={() => void handleStartCodexLogin()}
                        disabled={!llmProviderStatus?.installed || startingLlmLogin || llmLoginPending}
                        className={primaryButtonClass}
                      >
                        {startingLlmLogin || llmLoginPending ? "Waiting for ChatGPT…" : "Connect ChatGPT"}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => void refreshLlmProviderStatus()}
                      disabled={loadingLlmProviderStatus}
                      className={secondaryButtonClass}
                    >
                      <RotateCw className={cn("h-3.5 w-3.5", loadingLlmProviderStatus && "animate-spin")} />
                      Refresh
                    </button>
                    {pendingLlmAuthUrl && !llmProviderStatus?.authenticated && (
                      <a href={pendingLlmAuthUrl} target="_blank" rel="noreferrer" className={secondaryButtonClass}>
                        Open sign-in link
                      </a>
                    )}
                  </div>
                </div>
              )}

              {selectedLlmPreset === "custom" && (
                <label className="block">
                  <span className={labelClass}>Base URL</span>
                  <input
                    type="url"
                    autoComplete="off"
                    placeholder="https://api.openai.com/v1"
                    value={llmForm.base_url}
                    onChange={(e) => updateLlm("base_url", e.target.value)}
                    className={inputClass}
                  />
                </label>
              )}

              {selectedLlmPreset !== "mock" && !isCodexSubscription && (
                <label className="block">
                  <span className={labelClass}>API key</span>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="Paste your provider's API key"
                    value={llmForm.api_key}
                    onChange={(e) => updateLlm("api_key", e.target.value)}
                    className={cn(inputClass, "font-mono")}
                  />
                  {selectedLlmPreset !== "custom" ? (
                    <span className="mt-1.5 block text-[12px] text-secondary">
                      Endpoint: <code className="font-mono select-all">{llmForm.base_url}</code>
                    </span>
                  ) : null}
                </label>
              )}

              {selectedLlmPreset !== "mock" && (
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <label htmlFor="llm-model" className="text-[13px] font-medium text-primary">Model</label>
                    {!isCodexSubscription && currentPresetConfig && currentPresetConfig.defaultModels.length > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          setLlmTestResult(null);
                          const nextState = !customModelActive;
                          setCustomModelActive(nextState);
                          updateLlm("model", nextState ? "" : currentPresetConfig.defaultModels[0]);
                        }}
                        className="text-[12px] text-secondary underline-offset-2 hover:text-primary hover:underline"
                      >
                        {customModelActive ? "Choose from list" : "Enter a model ID"}
                      </button>
                    )}
                  </div>

                  {isCodexSubscription ? (
                    <select
                      id="llm-model"
                      value={llmForm.model}
                      onChange={(e) => {
                        setLlmTestResult(null);
                        const nextModelId = e.target.value;
                        const nextModel = llmProviderStatus?.models.find((model) => model.id === nextModelId);
                        setLlmForm((prev) => ({
                          ...prev,
                          model: nextModelId,
                          reasoning_effort: prev.reasoning_effort !== "auto"
                            && !nextModel?.supported_reasoning_efforts.includes(prev.reasoning_effort)
                            ? "auto"
                            : prev.reasoning_effort,
                        }));
                      }}
                      disabled={!codexReady}
                      className={inputClass}
                    >
                      {!codexReady && <option value="">Connect ChatGPT to load models</option>}
                      {llmProviderStatus?.models.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.display_name}{model.is_default ? " · Recommended" : ""}
                        </option>
                      ))}
                    </select>
                  ) : !customModelActive && currentPresetConfig && currentPresetConfig.defaultModels.length > 0 ? (
                    <select
                      id="llm-model"
                      value={llmForm.model}
                      onChange={(e) => {
                        setLlmTestResult(null);
                        updateLlm("model", e.target.value);
                      }}
                      className={inputClass}
                    >
                      {currentPresetConfig.defaultModels.map((modelId) => (
                        <option key={modelId} value={modelId}>{modelId}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id="llm-model"
                      type="text"
                      autoComplete="off"
                      placeholder="e.g. gpt-4o or deepseek-chat"
                      value={llmForm.model}
                      onChange={(e) => {
                        setLlmTestResult(null);
                        updateLlm("model", e.target.value);
                      }}
                      className={inputClass}
                    />
                  )}
                </div>
              )}

              {isCodexSubscription && (
                <label className="block">
                  <span className={labelClass}>Reasoning effort</span>
                  <select
                    value={llmForm.reasoning_effort}
                    onChange={(e) => {
                      setLlmTestResult(null);
                      updateLlm("reasoning_effort", e.target.value);
                    }}
                    disabled={!codexReady || !selectedCodexModel}
                    className={inputClass}
                  >
                    <option value="auto">
                      Auto
                      {selectedCodexModel?.default_reasoning_effort
                        ? ` (${reasoningEffortLabel(selectedCodexModel.default_reasoning_effort)})`
                        : ""}
                    </option>
                    {selectedCodexModel?.supported_reasoning_efforts.map((effort) => (
                      <option key={effort} value={effort}>{reasoningEffortLabel(effort)}</option>
                    ))}
                  </select>
                  <span className="mt-1.5 block text-[12px] leading-relaxed text-secondary">
                    Higher effort can help hard outputs but is slower and uses more of your plan.
                  </span>
                </label>
              )}

              {renderTestResult(llmTestResult)}

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => void handleSaveLlm()}
                  disabled={loading || savingLlm || (isCodexSubscription && !codexReady)}
                  className={primaryButtonClass}
                >
                  {savingLlm ? "Saving…" : savedFlashLlm ? "Saved" : "Save"}
                </button>
                {selectedLlmPreset !== "mock" && (
                  <button
                    type="button"
                    onClick={() => void handleTestLlm()}
                    disabled={testingLlm || savingLlm || loading || (isCodexSubscription && !codexReady)}
                    className={secondaryButtonClass}
                  >
                    {testingLlm ? <RotateCw className="h-3.5 w-3.5 animate-spin" /> : null}
                    {testingLlm ? "Testing…" : "Test connection"}
                  </button>
                )}
              </div>
            </section>

            <section className="mt-10 space-y-5 border-t border-outline pt-6">
              <h2 className="text-[15px] font-semibold text-primary">Speech</h2>

              <label className="block">
                <span className={labelClass}>Engine</span>
                <select
                  value={ttsForm.provider}
                  onChange={(e) => {
                    const local = e.target.value === "local_http";
                    setTtsTestResult(null);
                    setTtsForm((current) => ({ ...current, provider: e.target.value,
                      ...(local ? { model: "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit", base_url: "http://127.0.0.1:8090/v1", voice: "默认中文音色", audio_format: "wav" } : {}) }));
                  }}
                  className={inputClass}
                >
                  <option value="local_http">Local speech service</option>
                  <option value="openai_compatible">Cloud API (OpenAI-compatible)</option>
                </select>
              </label>

              <label className="block">
                <span className={labelClass}>{ttsUsesLocalModels ? "Service address" : "Base URL"}</span>
                <input type="url" autoComplete="off" value={ttsForm.base_url}
                  onChange={(e) => updateTts("base_url", e.target.value)} className={inputClass} />
                {ttsUsesLocalModels ? (
                  <span className="mt-1.5 block text-[12px] leading-relaxed text-secondary">
                    The speech service manages its models: preset voices, plus voice cloning with Qwen3 Base models. Pick a voice per episode.{" "}
                    <button type="button" onClick={() => navigate("/models")} className="text-primary underline underline-offset-2">
                      View service status
                    </button>
                  </span>
                ) : null}
              </label>

              {!ttsUsesLocalModels ? (
                <>
                  <label className="block">
                    <span className={labelClass}>API key</span>
                    <input type="password" autoComplete="off" value={ttsForm.api_key}
                      onChange={(e) => updateTts("api_key", e.target.value)} className={cn(inputClass, "font-mono")} />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-[1fr_1fr_120px]">
                    <label className="block">
                      <span className={labelClass}>Model</span>
                      <input type="text" autoComplete="off" value={ttsForm.model}
                        onChange={(e) => updateTts("model", e.target.value)} className={inputClass} />
                    </label>
                    <label className="block">
                      <span className={labelClass}>Default voice</span>
                      <input type="text" autoComplete="off" value={ttsForm.voice}
                        onChange={(e) => updateTts("voice", e.target.value)} className={inputClass} />
                    </label>
                    <label className="block">
                      <span className={labelClass}>Format</span>
                      <select value={ttsForm.audio_format} onChange={(e) => updateTts("audio_format", e.target.value)} className={inputClass}>
                        <option value="wav">WAV</option>
                        <option value="mp3">MP3</option>
                      </select>
                    </label>
                  </div>
                </>
              ) : null}

              {renderTestResult(ttsTestResult)}

              <div className="flex items-center gap-1">
                <button type="button" onClick={() => void handleSaveTts()} disabled={loading || savingTts} className={primaryButtonClass}>
                  {savingTts ? "Saving…" : savedFlashTts ? "Saved" : "Save"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleTestTts()}
                  disabled={testingTts || savingTts || loading}
                  className={secondaryButtonClass}
                >
                  {testingTts ? <RotateCw className="h-3.5 w-3.5 animate-spin" /> : null}
                  {testingTts ? "Testing…" : "Test connection"}
                </button>
              </div>
            </section>

            <p className="mt-10 border-t border-outline pt-4 text-[12px] leading-relaxed text-secondary">
              Settings and API keys are saved unencrypted in <code className="font-mono">.local-data/config/</code> on this device.
              Changing them doesn't alter existing episodes or audio.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
