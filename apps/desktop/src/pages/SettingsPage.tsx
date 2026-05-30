import { useEffect, useState } from "react";
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
import { LLMProviderConfig, RequestState, TTSProviderConfig } from "../types";
import { cn } from "../lib/utils";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  withRequestStateFallback,
} from "../lib/requestState";

type LLMForm = {
  provider: string;
  model: string;
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

function toLLMForm(config: LLMProviderConfig): LLMForm {
  return {
    provider: config.provider,
    model: config.model,
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
    base_url: "",
    api_key: "",
  });

  const [ttsForm, setTtsForm] = useState<TTSForm>({
    provider: "mock_remote",
    model: "mock-voice",
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

    if (preset.id === "custom") {
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

  const handleTestLlm = async () => {
    setTestingLlm(true);
    setLlmTestResult(null);
    try {
      const res = await bridge.testLLMConnection({
        provider: llmForm.provider,
        model: llmForm.model,
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
  const ttsUsesLocalModels = ttsForm.provider === "local_mlx";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="h-full overflow-y-auto px-6 lg:px-12 py-8 bg-[#0f0f11] text-[#e4e4e7] mac-scrollbar"
    >
      <div className="max-w-2xl mx-auto space-y-8">
        
        {/* Modern Glassmorphic Header */}
        <header className="relative p-6 rounded-2xl border border-white/5 bg-white/[0.02] backdrop-blur-xl shadow-2xl overflow-hidden">
          <div className="absolute top-0 right-0 w-48 h-48 bg-accent-amber/5 blur-3xl rounded-full" />
          <h1 className="text-2xl font-headline font-bold text-white tracking-wide">Settings</h1>
          <p className="text-zinc-400 text-[13px] mt-2 leading-relaxed">
            Configure your Large Language Model endpoints and Text-to-Speech voices. Configurations are strictly stored locally on this device.
          </p>
        </header>

        {loading ? (
          <div className="py-24 flex flex-col items-center justify-center gap-3 text-zinc-500">
            <Loader2 className="w-6 h-6 animate-spin text-accent-amber" />
            <span className="text-xs font-medium tracking-wide uppercase">Loading Configuration…</span>
          </div>
        ) : (
          <div className="space-y-8">

            {/* SECTION 1: LLM CONFIGURATION */}
            <section className="p-6 rounded-2xl border border-white/5 bg-white/[0.01] backdrop-blur-xl shadow-xl space-y-6 relative">
              <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <div className="flex items-center gap-2.5 text-accent-amber">
                  <Sparkles className="w-5 h-5" />
                  <h2 className="text-sm font-semibold tracking-wider uppercase font-headline">Language Model (LLM)</h2>
                </div>
                <span className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full font-mono">
                  config/llm.json
                </span>
              </div>

              <div className="space-y-5">
                {/* Provider Preset Dropdown */}
                <label className="block">
                  <span className="text-xs font-semibold text-zinc-300 mb-2 block">Service Provider</span>
                  <div className="relative">
                    <select
                      value={selectedLlmPreset}
                      onChange={(e) => handlePresetChange(e.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all appearance-none cursor-pointer"
                    >
                      {LLM_PRESETS.map((preset) => (
                        <option key={preset.id} value={preset.id}>
                          {preset.name}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400 pointer-events-none" />
                  </div>
                </label>

                {/* Conditional Base URL field */}
                {selectedLlmPreset === "custom" && (
                  <label className="block">
                    <span className="text-xs font-semibold text-zinc-300 mb-2 block">Base URL</span>
                    <input
                      type="url"
                      autoComplete="off"
                      placeholder="e.g. https://api.openai.com/v1"
                      value={llmForm.base_url}
                      onChange={(e) => updateLlm("base_url", e.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all"
                    />
                  </label>
                )}

                {/* Preset-inferred non-editable Base URL details */}
                {selectedLlmPreset !== "custom" && selectedLlmPreset !== "mock" && (
                  <div className="px-4 py-2 rounded-xl bg-zinc-950/60 border border-white/[0.02] flex items-center justify-between text-xs">
                    <span className="text-zinc-500 font-medium">Endpoint URL:</span>
                    <code className="text-zinc-300 font-mono select-all text-[11px]">{llmForm.base_url}</code>
                  </div>
                )}

                {/* API Key */}
                {selectedLlmPreset !== "mock" && (
                  <label className="block">
                    <span className="text-xs font-semibold text-zinc-300 mb-2 block">API key</span>
                    <input
                      type="password"
                      autoComplete="off"
                      placeholder="Paste your provider's API key here"
                      value={llmForm.api_key}
                      onChange={(e) => updateLlm("api_key", e.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all font-mono"
                    />
                  </label>
                )}

                {/* Model Configuration Selector (Dual-mode) */}
                {selectedLlmPreset !== "mock" && (
                  <label className="block">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-zinc-300">Model Name</span>
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

                    {!customModelActive && currentPresetConfig && currentPresetConfig.defaultModels.length > 0 ? (
                      <div className="relative">
                        <select
                          value={llmForm.model}
                          onChange={(e) => {
                            setLlmTestResult(null);
                            updateLlm("model", e.target.value);
                          }}
                          className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all appearance-none cursor-pointer"
                        >
                          {currentPresetConfig.defaultModels.map((modelId) => (
                            <option key={modelId} value={modelId}>
                              {modelId}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400 pointer-events-none" />
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
                        className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all"
                      />
                    )}
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
              <div className="flex items-center justify-between border-t border-white/5 pt-4">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void handleSaveLlm()}
                    disabled={loading || savingLlm}
                    className="px-5 py-2.5 rounded-xl bg-accent-amber hover:bg-accent-amber/90 text-black text-xs font-semibold uppercase tracking-wider transition-all disabled:opacity-50"
                  >
                    {savingLlm ? "Saving…" : "Save LLM"}
                  </button>
                  <span
                    className={cn(
                      "text-xs text-zinc-400 transition-opacity",
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
                    disabled={testingLlm || savingLlm || loading}
                    className="px-4 py-2.5 rounded-xl border border-white/10 hover:bg-white/5 text-zinc-300 hover:text-white text-xs font-semibold transition-all disabled:opacity-50 inline-flex items-center gap-2"
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
            <section className="p-6 rounded-2xl border border-white/5 bg-white/[0.01] backdrop-blur-xl shadow-xl space-y-6 relative">
              <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <div className="flex items-center gap-2.5 text-accent-amber">
                  <Volume2 className="w-5 h-5" />
                  <h2 className="text-sm font-semibold tracking-wider uppercase font-headline">Text-to-Speech (TTS)</h2>
                </div>
                <span className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full font-mono">
                  config/tts.json
                </span>
              </div>

              <div className="space-y-5">
                {/* TTS Provider Select */}
                <label className="block">
                  <span className="text-xs font-semibold text-zinc-300 mb-2 block">TTS Engine</span>
                  <div className="relative">
                    <select
                      value={ttsForm.provider}
                      onChange={(e) => updateTts("provider", e.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all appearance-none cursor-pointer"
                    >
                      <option value="local_mlx">Local · MLX on this Mac (Primary)</option>
                      <option value="openai_compatible">Remote API · OpenAI-compatible Cloud</option>
                      <option value="mock_remote">Mock Testing Provider</option>
                    </select>
                    <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400 pointer-events-none" />
                  </div>
                </label>

                {/* Local MLX Guide Card */}
                {ttsUsesLocalModels && (
                  <div className="rounded-xl border border-accent-amber/20 bg-accent-amber/5 p-4 space-y-3 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-accent-amber/5 blur-2xl rounded-full" />
                    <p className="text-xs font-semibold text-accent-amber">Local Voice Model Engine</p>
                    <p className="text-xs leading-relaxed text-zinc-400">
                      Download Qwen TTS models, manage storage capacity, and configure voice profile takes via the dedicated Models Center.
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
                {!ttsUsesLocalModels && ttsForm.provider !== "mock_remote" && (
                  <div className="space-y-4 pt-1">
                    <label className="block">
                      <span className="text-xs font-semibold text-zinc-300 mb-2 block">Cloud TTS Model</span>
                      <input
                        type="text"
                        autoComplete="off"
                        placeholder="e.g. tts-1, tts-1-hd"
                        value={ttsForm.model}
                        onChange={(e) => updateTts("model", e.target.value)}
                        className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all"
                      />
                    </label>

                    <label className="block">
                      <span className="text-xs font-semibold text-zinc-300 mb-2 block">Base URL</span>
                      <input
                        type="url"
                        autoComplete="off"
                        placeholder="https://api.openai.com/v1"
                        value={ttsForm.base_url}
                        onChange={(e) => updateTts("base_url", e.target.value)}
                        className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all"
                      />
                    </label>

                    <label className="block">
                      <span className="text-xs font-semibold text-zinc-300 mb-2 block">API key</span>
                      <input
                        type="password"
                        autoComplete="off"
                        placeholder="Paste your cloud TTS provider API key here"
                        value={ttsForm.api_key}
                        onChange={(e) => updateTts("api_key", e.target.value)}
                        className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all font-mono"
                      />
                    </label>

                    <label className="block">
                      <span className="text-xs font-semibold text-zinc-300 mb-2 block">Voice</span>
                      <input
                        type="text"
                        autoComplete="off"
                        placeholder="e.g. alloy, echo, shimmer"
                        value={ttsForm.voice}
                        onChange={(e) => updateTts("voice", e.target.value)}
                        className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all"
                      />
                    </label>
                  </div>
                )}

                {/* Predefined Audio Format Select */}
                <label className="block">
                  <span className="text-xs font-semibold text-zinc-300 mb-2 block">Audio format</span>
                  <div className="relative">
                    <select
                      value={ttsForm.audio_format}
                      onChange={(e) => updateTts("audio_format", e.target.value)}
                      className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white outline-none focus:border-accent-amber/50 hover:border-white/20 transition-all appearance-none cursor-pointer"
                    >
                      <option value="wav">wav (Recommended · Lossless Safety)</option>
                      <option value="mp3">mp3 (Compressed · Broad Compatibility)</option>
                      <option value="m4a">m4a (Compressed AAC)</option>
                    </select>
                    <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400 pointer-events-none" />
                  </div>
                  <p className="mt-2 text-[11px] text-zinc-500 leading-normal">
                    WAV is highly recommended for Qwen MLX voice synthesis to ensure no audio chunk decoding stretches. Cloud endpoints support MP3.
                  </p>
                </label>

                {/* Advanced TTS Parameters */}
                <div className="rounded-xl border border-white/5 bg-zinc-950/20 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setAdvancedTtsOpen((v) => !v)}
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/[0.02] transition-all"
                  >
                    <span className="inline-flex items-center gap-2 text-xs font-semibold text-zinc-400">
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      Advanced TTS parameters
                    </span>
                    <ChevronDown className={cn("h-4 w-4 text-zinc-400 transition-transform duration-200", advancedTtsOpen && "rotate-180")} />
                  </button>

                  <AnimatePresence>
                    {advancedTtsOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden border-t border-white/5 bg-zinc-900/10"
                      >
                        <div className="space-y-4 p-4">
                          {ttsUsesLocalModels && (
                            <label className="block">
                              <span className="text-xs font-semibold text-zinc-400 mb-2 block">Raw local model repo id</span>
                              <input
                                type="text"
                                autoComplete="off"
                                placeholder="mlx-community/Qwen3-TTS-..."
                                value={ttsForm.model}
                                onChange={(e) => updateTts("model", e.target.value)}
                                className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50"
                              />
                              <p className="mt-1 text-[10px] text-zinc-500">Configure downloads primarily inside Models Center.</p>
                            </label>
                          )}

                          <label className="block">
                            <span className="text-xs font-semibold text-zinc-400 mb-2 block">Local runtime</span>
                            <input
                              type="text"
                              autoComplete="off"
                              placeholder="mlx"
                              value={ttsForm.local_runtime}
                              onChange={(e) => updateTts("local_runtime", e.target.value)}
                              className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white outline-none focus:border-accent-amber/50"
                            />
                          </label>

                          <label className="block">
                            <span className="text-xs font-semibold text-zinc-400 mb-2 block">Local model path override</span>
                            <input
                              type="text"
                              autoComplete="off"
                              placeholder="/absolute/path/to/model (optional)"
                              value={ttsForm.local_model_path}
                              onChange={(e) => updateTts("local_model_path", e.target.value)}
                              className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50"
                            />
                          </label>

                          <label className="block">
                            <span className="text-xs font-semibold text-zinc-400 mb-2 block">Local ref audio path</span>
                            <input
                              type="text"
                              autoComplete="off"
                              placeholder="/absolute/path/to/ref.wav (optional)"
                              value={ttsForm.local_ref_audio_path}
                              onChange={(e) => updateTts("local_ref_audio_path", e.target.value)}
                              className="w-full rounded-xl border border-white/10 bg-zinc-900/60 px-4 py-2.5 text-[13px] text-white placeholder-zinc-600 outline-none focus:border-accent-amber/50"
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
              <div className="flex items-center justify-between border-t border-white/5 pt-4">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void handleSaveTts()}
                    disabled={loading || savingTts}
                    className="px-5 py-2.5 rounded-xl bg-accent-amber hover:bg-accent-amber/90 text-black text-xs font-semibold uppercase tracking-wider transition-all disabled:opacity-50"
                  >
                    {savingTts ? "Saving…" : "Save TTS"}
                  </button>
                  <span
                    className={cn(
                      "text-xs text-zinc-400 transition-opacity",
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
                  className="px-4 py-2.5 rounded-xl border border-white/10 hover:bg-white/5 text-zinc-300 hover:text-white text-xs font-semibold transition-all disabled:opacity-50 inline-flex items-center gap-2"
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
          <div className="p-4 rounded-xl border border-white/5 bg-zinc-900/40 text-zinc-400 text-xs flex items-center gap-2.5 animate-pulse">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-amber" />
            <span>{`${Math.round(requestState.progress_percent)}% · ${requestState.message}`}</span>
          </div>
        )}

        {/* Cohesive Footer Notice */}
        <p className="text-[11px] text-zinc-500 text-center leading-relaxed max-w-sm mx-auto">
          Persisted globally in <code className="text-zinc-400 font-mono">.local-data/config/</code>. Swapping default model presets does not re-write session-level configurations or historic audio files.
        </p>

      </div>
    </motion.div>
  );
}
