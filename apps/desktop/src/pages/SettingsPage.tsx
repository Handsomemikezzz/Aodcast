import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  Loader2,
  Sparkles,
  SlidersHorizontal,
  Volume2,
  Check,
  AlertCircle,
  Activity,
  ArrowRight,
  HelpCircle,
  RotateCw
} from "lucide-react";
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
  local_runtime: string;
  local_model_path: string;
  local_ref_audio_path: string;
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
    local_runtime: config.local_runtime,
    local_model_path: config.local_model_path,
    local_ref_audio_path: config.local_ref_audio_path,
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
    provider: "local_mlx",
    model: "",
    base_url: "",
    api_key: "",
    voice: "alloy",
    audio_format: "wav",
    local_runtime: "mlx",
    local_model_path: "",
    local_ref_audio_path: "",
  });

  // UI state managers
  const [loading, setLoading] = useState(true);
  const [savingLlm, setSavingLlm] = useState(false);
  const [savingTts, setSavingTts] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [savedFlashLlm, setSavedFlashLlm] = useState(false);
  const [savedFlashTts, setSavedFlashTts] = useState(false);
  const [requestState, setRequestState] = useState<RequestState | null>(null);
  const [advancedTtsOpen, setAdvancedTtsOpen] = useState(false);

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
        local_runtime: ttsForm.local_runtime,
        local_model_path: ttsForm.local_model_path,
        local_ref_audio_path: ttsForm.local_ref_audio_path,
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
        local_runtime: ttsForm.local_runtime,
        local_model_path: ttsForm.local_model_path,
        local_ref_audio_path: ttsForm.local_ref_audio_path,
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
  const ttsUsesLocalModels = ttsForm.provider === "local_mlx";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="h-full overflow-y-auto px-6 lg:px-12 py-8 bg-background text-on-surface mac-scrollbar"
    >
      <div className="max-w-2xl mx-auto space-y-8">
        
        {/* Modern Glassmorphic Header */}
        <header className="relative p-6 rounded-2xl border border-outline bg-surface-container-low/60 backdrop-blur-xl shadow-2xl overflow-hidden">
          <div className="absolute top-0 right-0 w-48 h-48 bg-accent-amber/5 blur-3xl rounded-full" />
          <h1 className="text-2xl font-headline font-bold text-primary tracking-wide">Settings</h1>
          <p className="text-secondary text-[13px] mt-2 leading-relaxed">
            Connect a ChatGPT subscription or configure an API endpoint, then choose Text-to-Speech voices. Aodcast never reads Codex OAuth tokens.
          </p>
        </header>

        {loading ? (
          <div className="py-24 flex flex-col items-center justify-center gap-3 text-secondary">
            <Loader2 className="w-6 h-6 animate-spin text-accent-amber" />
            <span className="text-xs font-medium tracking-wide uppercase">Loading Configuration…</span>
          </div>
        ) : (
          <div className="space-y-8">

            {/* SECTION 1: LLM CONFIGURATION */}
            <section className="p-6 rounded-2xl border border-outline bg-surface-container-low/50 backdrop-blur-xl shadow-xl space-y-6 relative">
              <div className="flex items-center border-b border-outline pb-4">
                <div className="flex items-center gap-2.5 text-accent-amber">
                  <Sparkles className="w-5 h-5" />
                  <h2 className="text-sm font-semibold tracking-wider uppercase font-headline">Language Model (LLM)</h2>
                </div>
              </div>

              <div className="space-y-5">
                {/* Provider Preset Dropdown */}
                <label className="block">
                  <span className="text-xs font-semibold text-on-surface-variant mb-2 block">Service Provider</span>
                  <div className="relative">
                    <select
                      value={selectedLlmPreset}
                      onChange={(e) => handlePresetChange(e.target.value)}
                      className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all appearance-none cursor-pointer"
                    >
                      {LLM_PRESETS.map((preset) => (
                        <option key={preset.id} value={preset.id}>
                          {preset.name}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary pointer-events-none" />
                  </div>
                </label>

                {isCodexSubscription && (
                  <div className="rounded-xl border border-accent-amber/20 bg-accent-amber/5 p-4 space-y-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-1">
                        <p className="text-xs font-semibold text-primary">Official Codex app-server</p>
                        <p className="text-[11px] leading-relaxed text-secondary">
                          Uses the ChatGPT account managed by the official Codex CLI. Requests consume that account&apos;s Codex plan allowance, not OpenAI API billing.
                        </p>
                      </div>
                      {loadingLlmProviderStatus ? (
                        <Loader2 className="w-4 h-4 animate-spin text-accent-amber shrink-0" />
                      ) : llmProviderStatus?.authenticated ? (
                        <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div className="rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2">
                        <span className="text-secondary">Codex CLI</span>
                        <p className="mt-0.5 text-on-surface-variant">
                          {llmProviderStatus?.installed
                            ? llmProviderStatus.version || "Installed"
                            : "Not installed"}
                        </p>
                      </div>
                      <div className="rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2">
                        <span className="text-secondary">ChatGPT plan</span>
                        <p className="mt-0.5 text-on-surface-variant capitalize">
                          {llmProviderStatus?.authenticated
                            ? llmProviderStatus.plan_type || "Connected"
                            : "Not connected"}
                        </p>
                      </div>
                    </div>

                    {llmProviderStatus?.account_email && (
                      <p className="text-[11px] text-secondary truncate">
                        Signed in as {llmProviderStatus.account_email}
                      </p>
                    )}

                    {llmProviderStatus?.rate_limit && (
                      <div className="space-y-1.5">
                        <div className="flex justify-between text-[10px] text-secondary">
                          <span>Current Codex usage window</span>
                          <span>{Math.round(llmProviderStatus.rate_limit.used_percent)}% used</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-surface-container-high">
                          <div
                            className="h-full rounded-full bg-accent-amber transition-[width]"
                            style={{ width: `${Math.min(100, llmProviderStatus.rate_limit.used_percent)}%` }}
                          />
                        </div>
                      </div>
                    )}

                    <p className="text-[11px] leading-relaxed text-secondary">
                      {llmProviderStatus?.message
                        ?? "Checking the local Codex installation and ChatGPT sign-in…"}
                    </p>
                    {!llmProviderStatus?.installed && (
                      <code className="block rounded-lg bg-surface-container-high px-3 py-2 text-[10px] text-on-surface-variant select-all">
                        npm install -g @openai/codex
                      </code>
                    )}

                    <div className="flex flex-wrap gap-2">
                      {!llmProviderStatus?.authenticated && (
                        <button
                          type="button"
                          onClick={() => void handleStartCodexLogin()}
                          disabled={!llmProviderStatus?.installed || startingLlmLogin || llmLoginPending}
                          className="rounded-lg bg-accent-amber px-3 py-2 text-[11px] font-semibold text-on-primary disabled:opacity-50"
                        >
                          {startingLlmLogin || llmLoginPending ? "Waiting for ChatGPT…" : "Connect ChatGPT"}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => void refreshLlmProviderStatus()}
                        disabled={loadingLlmProviderStatus}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-outline px-3 py-2 text-[11px] text-on-surface-variant disabled:opacity-50"
                      >
                        <RotateCw className={cn("h-3 w-3", loadingLlmProviderStatus && "animate-spin")} />
                        Refresh
                      </button>
                      {pendingLlmAuthUrl && !llmProviderStatus?.authenticated && (
                        <a
                          href={pendingLlmAuthUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-lg border border-accent-amber/30 px-3 py-2 text-[11px] text-accent-amber"
                        >
                          Open sign-in link
                        </a>
                      )}
                    </div>
                  </div>
                )}

                {/* Conditional Base URL field */}
                {selectedLlmPreset === "custom" && (
                  <label className="block">
                    <span className="text-xs font-semibold text-on-surface-variant mb-2 block">Base URL</span>
                    <input
                      type="url"
                      autoComplete="off"
                      placeholder="e.g. https://api.openai.com/v1"
                      value={llmForm.base_url}
                      onChange={(e) => updateLlm("base_url", e.target.value)}
                      className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all"
                    />
                  </label>
                )}

                {/* Preset-inferred non-editable Base URL details */}
                {selectedLlmPreset !== "custom" && selectedLlmPreset !== "mock" && !isCodexSubscription && (
                  <div className="px-4 py-2 rounded-xl bg-surface-container-low border border-outline-variant flex items-center justify-between text-xs">
                    <span className="text-secondary font-medium">Endpoint URL:</span>
                    <code className="text-on-surface-variant font-mono select-all text-[11px]">{llmForm.base_url}</code>
                  </div>
                )}

                {/* API Key */}
                {selectedLlmPreset !== "mock" && !isCodexSubscription && (
                  <label className="block">
                    <span className="text-xs font-semibold text-on-surface-variant mb-2 block">API key</span>
                    <input
                      type="password"
                      autoComplete="off"
                      placeholder="Paste your provider's API key here"
                      value={llmForm.api_key}
                      onChange={(e) => updateLlm("api_key", e.target.value)}
                      className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all font-mono"
                    />
                  </label>
                )}

                {/* Model Configuration Selector (Dual-mode) */}
                {selectedLlmPreset !== "mock" && (
                  <label className="block">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-on-surface-variant">Model Name</span>
                      {currentPresetConfig && currentPresetConfig.defaultModels.length > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            setLlmTestResult(null);
                            const nextState = !customModelActive;
                            setCustomModelActive(nextState);
                            if (!nextState) {
                              updateLlm("model", currentPresetConfig.defaultModels[0]);
                            } else {
                              updateLlm("model", "");
                            }
                          }}
                          className="text-[11px] text-accent-amber hover:underline transition-all"
                        >
                          {customModelActive ? "Choose standard models" : "Type custom model ID"}
                        </button>
                      )}
                    </div>

                    {isCodexSubscription ? (
                      <div className="relative">
                        <select
                          value={llmForm.model}
                          onChange={(e) => {
                            setLlmTestResult(null);
                            const nextModelId = e.target.value;
                            const nextModel = llmProviderStatus?.models.find(
                              (model) => model.id === nextModelId,
                            );
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
                          className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary outline-none focus:border-accent-amber/50 disabled:opacity-50 appearance-none"
                        >
                          {!codexReady && <option value="">Connect ChatGPT to load models</option>}
                          {llmProviderStatus?.models.map((model) => (
                            <option key={model.id} value={model.id}>
                              {model.display_name}{model.is_default ? " · Recommended" : ""}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary pointer-events-none" />
                      </div>
                    ) : !customModelActive && currentPresetConfig && currentPresetConfig.defaultModels.length > 0 ? (
                      <div className="relative">
                        <select
                          value={llmForm.model}
                          onChange={(e) => {
                            setLlmTestResult(null);
                            updateLlm("model", e.target.value);
                          }}
                          className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all appearance-none cursor-pointer"
                        >
                          {currentPresetConfig.defaultModels.map((modelId) => (
                            <option key={modelId} value={modelId}>
                              {modelId}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary pointer-events-none" />
                      </div>
                    ) : (
                      <input
                        type="text"
                        autoComplete="off"
                        placeholder="e.g. gpt-4o, deepseek-chat, or your custom fine-tune ID"
                        value={llmForm.model}
                        onChange={(e) => {
                          setLlmTestResult(null);
                          updateLlm("model", e.target.value);
                        }}
                        className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all"
                      />
                    )}
                  </label>
                )}

                {isCodexSubscription && (
                  <label className="block">
                    <span className="text-xs font-semibold text-on-surface-variant mb-2 block">
                      Reasoning effort
                    </span>
                    <div className="relative">
                      <select
                        value={llmForm.reasoning_effort}
                        onChange={(e) => {
                          setLlmTestResult(null);
                          updateLlm("reasoning_effort", e.target.value);
                        }}
                        disabled={!codexReady || !selectedCodexModel}
                        className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary outline-none focus:border-accent-amber/50 disabled:opacity-50 appearance-none"
                      >
                        <option value="auto">
                          Auto · Model default
                          {selectedCodexModel?.default_reasoning_effort
                            ? ` (${reasoningEffortLabel(selectedCodexModel.default_reasoning_effort)})`
                            : ""}
                        </option>
                        {selectedCodexModel?.supported_reasoning_efforts.map((effort) => (
                          <option key={effort} value={effort}>
                            {reasoningEffortLabel(effort)}
                          </option>
                        ))}
                      </select>
                      <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary pointer-events-none" />
                    </div>
                    <p className="mt-2 text-[11px] leading-relaxed text-secondary">
                      Applies to every Codex-backed LLM task. Higher effort can improve difficult outputs,
                      but usually increases response time and plan usage.
                    </p>
                  </label>
                )}
              </div>

              {/* Dynamic connection check messages */}
              <AnimatePresence mode="wait">
                {llmTestResult && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className={cn(
                      "p-3.5 rounded-xl border text-xs flex items-start gap-2.5 leading-relaxed transition-all duration-200",
                      llmTestResult.success
                        ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                        : "bg-rose-500/10 border-rose-500/20 text-rose-400"
                    )}
                  >
                    {llmTestResult.success ? (
                      <Check className="w-4 h-4 shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    )}
                    <span className="select-all">{llmTestResult.message}</span>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Action Buttons */}
              <div className="flex items-center justify-between border-t border-outline pt-4">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void handleSaveLlm()}
                    disabled={loading || savingLlm || (isCodexSubscription && !codexReady)}
                    className="px-5 py-2.5 rounded-xl bg-accent-amber hover:bg-accent-amber/90 text-on-primary text-xs font-semibold uppercase tracking-wider transition-all disabled:opacity-50"
                  >
                    {savingLlm ? "Saving…" : "Save LLM"}
                  </button>
                  <span
                    className={cn(
                      "text-xs text-secondary transition-opacity",
                      savedFlashLlm ? "opacity-100" : "opacity-0"
                    )}
                  >
                    Saved successfully
                  </span>
                </div>

                {selectedLlmPreset !== "mock" && (
                  <button
                    type="button"
                    onClick={() => void handleTestLlm()}
                    disabled={testingLlm || savingLlm || loading || (isCodexSubscription && !codexReady)}
                    className="px-4 py-2.5 rounded-xl border border-outline hover:bg-surface-container-high/60 text-on-surface-variant hover:text-primary text-xs font-semibold transition-all disabled:opacity-50 inline-flex items-center gap-2"
                  >
                    {testingLlm ? (
                      <>
                        <RotateCw className="w-3.5 h-3.5 animate-spin" />
                        Testing Connection...
                      </>
                    ) : (
                      <>
                        <Activity className="w-3.5 h-3.5" />
                        Test Connection
                      </>
                    )}
                  </button>
                )}
              </div>
            </section>


            {/* SECTION 2: TTS CONFIGURATION */}
            <section className="p-6 rounded-2xl border border-outline bg-surface-container-low/50 backdrop-blur-xl shadow-xl space-y-6 relative">
              <div className="flex items-center border-b border-outline pb-4">
                <div className="flex items-center gap-2.5 text-accent-amber">
                  <Volume2 className="w-5 h-5" />
                  <h2 className="text-sm font-semibold tracking-wider uppercase font-headline">Text-to-Speech (TTS)</h2>
                </div>
              </div>

              <div className="space-y-5">
                {/* TTS Provider Select */}
                <label className="block">
                  <span className="text-xs font-semibold text-on-surface-variant mb-2 block">TTS Engine</span>
                  <div className="relative">
                    <select
                      value={ttsForm.provider}
                      onChange={(e) => updateTts("provider", e.target.value)}
                      className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all appearance-none cursor-pointer"
                    >
                      <option value="local_mlx">Local · MLX on this Mac (Primary)</option>
                      <option value="openai_compatible">Remote API · OpenAI-compatible Cloud</option>
                    </select>
                    <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary pointer-events-none" />
                  </div>
                </label>

                {/* Local MLX Guide Card */}
                {ttsUsesLocalModels && (
                  <div className="rounded-xl border border-accent-amber/20 bg-accent-amber/5 p-4 space-y-3 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-accent-amber/5 blur-2xl rounded-full" />
                    <p className="text-xs font-semibold text-accent-amber">Local Voice Model Engine</p>
                    <p className="text-xs leading-relaxed text-secondary">
                      Download VoxCPM2, MOSS, or Qwen baseline models and manage local model storage in the dedicated Models Center.
                    </p>
                    <button
                      type="button"
                      onClick={() => navigate("/models")}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-accent-amber/35 px-3.5 py-1.5 text-xs font-semibold text-accent-amber hover:bg-accent-amber/10 transition-all"
                    >
                      Open Models Center
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}

                {/* Remote API Settings */}
                {!ttsUsesLocalModels && (
                  <div className="space-y-4 pt-1">
                    <label className="block">
                      <span className="text-xs font-semibold text-on-surface-variant mb-2 block">Cloud TTS Model</span>
                      <input
                        type="text"
                        autoComplete="off"
                        placeholder="e.g. tts-1, tts-1-hd"
                        value={ttsForm.model}
                        onChange={(e) => updateTts("model", e.target.value)}
                        className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all"
                      />
                    </label>

                    <label className="block">
                      <span className="text-xs font-semibold text-on-surface-variant mb-2 block">Base URL</span>
                      <input
                        type="url"
                        autoComplete="off"
                        placeholder="https://api.openai.com/v1"
                        value={ttsForm.base_url}
                        onChange={(e) => updateTts("base_url", e.target.value)}
                        className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all"
                      />
                    </label>

                    <label className="block">
                      <span className="text-xs font-semibold text-on-surface-variant mb-2 block">API key</span>
                      <input
                        type="password"
                        autoComplete="off"
                        placeholder="Paste your cloud TTS provider API key here"
                        value={ttsForm.api_key}
                        onChange={(e) => updateTts("api_key", e.target.value)}
                        className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all font-mono"
                      />
                    </label>

                    <label className="block">
                      <span className="text-xs font-semibold text-on-surface-variant mb-2 block">Voice</span>
                      <input
                        type="text"
                        autoComplete="off"
                        placeholder="e.g. alloy, echo, shimmer"
                        value={ttsForm.voice}
                        onChange={(e) => updateTts("voice", e.target.value)}
                        className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all"
                      />
                    </label>
                  </div>
                )}

                {/* Predefined Audio Format Select */}
                <label className="block">
                  <span className="text-xs font-semibold text-on-surface-variant mb-2 block">Audio format</span>
                  <div className="relative">
                    <select
                      value={ttsForm.audio_format}
                      onChange={(e) => updateTts("audio_format", e.target.value)}
                      className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary outline-none focus:border-accent-amber/50 hover:border-accent-amber/20 transition-all appearance-none cursor-pointer"
                    >
                      <option value="wav">wav (Recommended · Lossless Safety)</option>
                      <option value="mp3">mp3 (Compressed · Broad Compatibility)</option>
                      <option value="m4a">m4a (Compressed AAC)</option>
                    </select>
                    <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary pointer-events-none" />
                  </div>
                  <p className="mt-2 text-[11px] text-secondary leading-normal">
                    WAV is highly recommended for Qwen MLX voice synthesis to ensure no audio chunk decoding stretches. Cloud endpoints support MP3.
                  </p>
                </label>

                {/* Advanced TTS Parameters */}
                <div className="rounded-xl border border-outline bg-surface-container-low overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setAdvancedTtsOpen((v) => !v)}
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-container-low/60 transition-all"
                  >
                    <span className="inline-flex items-center gap-2 text-xs font-semibold text-secondary">
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      Advanced TTS parameters
                    </span>
                    <ChevronDown className={cn("h-4 w-4 text-secondary transition-transform duration-200", advancedTtsOpen && "rotate-180")} />
                  </button>

                  <AnimatePresence>
                    {advancedTtsOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden border-t border-outline bg-surface-container-low/60"
                      >
                        <div className="space-y-4 p-4">
                          {ttsUsesLocalModels && (
                            <label className="block">
                              <span className="text-xs font-semibold text-secondary mb-2 block">Raw local model repo id</span>
                              <input
                                type="text"
                                autoComplete="off"
                                placeholder="mlx-community/Qwen3-TTS-..."
                                value={ttsForm.model}
                                onChange={(e) => updateTts("model", e.target.value)}
                                className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50"
                              />
                              <p className="mt-1 text-[10px] text-secondary">Configure downloads primarily inside Models Center.</p>
                            </label>
                          )}

                          <label className="block">
                            <span className="text-xs font-semibold text-secondary mb-2 block">Local runtime</span>
                            <input
                              type="text"
                              autoComplete="off"
                              placeholder="mlx"
                              value={ttsForm.local_runtime}
                              onChange={(e) => updateTts("local_runtime", e.target.value)}
                              className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary outline-none focus:border-accent-amber/50"
                            />
                          </label>

                          <label className="block">
                            <span className="text-xs font-semibold text-secondary mb-2 block">Local model path override</span>
                            <input
                              type="text"
                              autoComplete="off"
                              placeholder="/absolute/path/to/model (optional)"
                              value={ttsForm.local_model_path}
                              onChange={(e) => updateTts("local_model_path", e.target.value)}
                              className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50"
                            />
                          </label>

                          <label className="block">
                            <span className="text-xs font-semibold text-secondary mb-2 block">Local ref audio path</span>
                            <input
                              type="text"
                              autoComplete="off"
                              placeholder="/absolute/path/to/ref.wav (optional)"
                              value={ttsForm.local_ref_audio_path}
                              onChange={(e) => updateTts("local_ref_audio_path", e.target.value)}
                              className="w-full rounded-xl border border-outline bg-surface-container-high px-4 py-2.5 text-[13px] text-primary placeholder:text-secondary/50 outline-none focus:border-accent-amber/50"
                            />
                          </label>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>

              {/* Dynamic TTS Verification Feedback */}
              <AnimatePresence mode="wait">
                {ttsTestResult && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className={cn(
                      "p-3.5 rounded-xl border text-xs flex items-start gap-2.5 leading-relaxed transition-all duration-200",
                      ttsTestResult.success
                        ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                        : "bg-rose-500/10 border-rose-500/20 text-rose-400"
                    )}
                  >
                    {ttsTestResult.success ? (
                      <Check className="w-4 h-4 shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    )}
                    <span className="select-all">{ttsTestResult.message}</span>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Action Footer */}
              <div className="flex items-center justify-between border-t border-outline pt-4">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void handleSaveTts()}
                    disabled={loading || savingTts}
                    className="px-5 py-2.5 rounded-xl bg-accent-amber hover:bg-accent-amber/90 text-on-primary text-xs font-semibold uppercase tracking-wider transition-all disabled:opacity-50"
                  >
                    {savingTts ? "Saving…" : "Save TTS"}
                  </button>
                  <span
                    className={cn(
                      "text-xs text-secondary transition-opacity",
                      savedFlashTts ? "opacity-100" : "opacity-0"
                    )}
                  >
                    Saved successfully
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => void handleTestTts()}
                  disabled={testingTts || savingTts || loading}
                  className="px-4 py-2.5 rounded-xl border border-outline hover:bg-surface-container-high/60 text-on-surface-variant hover:text-primary text-xs font-semibold transition-all disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {testingTts ? (
                    <>
                      <RotateCw className="w-3.5 h-3.5 animate-spin" />
                      Testing TTS...
                    </>
                  ) : (
                    <>
                      <Activity className="w-3.5 h-3.5" />
                      Test Connection
                    </>
                  )}
                </button>
              </div>
            </section>

          </div>
        )}

        {/* Global Error Banner */}
        {error && (
          <div className="p-4 rounded-xl border border-rose-500/20 bg-rose-500/5 text-rose-400 text-xs flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold">Operation Failed</p>
              <p className="leading-relaxed">{error}</p>
            </div>
          </div>
        )}

        {/* Global Status Manager Polling Indicator */}
        {!error && requestState?.phase === "running" && (
          <div className="p-4 rounded-xl border border-outline bg-surface-container-high/60 text-secondary text-xs flex items-center gap-2.5 animate-pulse">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-amber" />
            <span>{`${Math.round(requestState.progress_percent)}% · ${requestState.message}`}</span>
          </div>
        )}

        {/* Cohesive Footer Notice */}
        <p className="text-[11px] text-secondary text-center leading-relaxed max-w-sm mx-auto">
          Persisted globally in <code className="text-secondary font-mono">.local-data/config/</code>. Swapping default model presets does not re-write session-level configurations or historic audio files.
        </p>

      </div>
    </motion.div>
  );
}
