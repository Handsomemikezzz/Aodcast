import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Sparkles, Volume2 } from "lucide-react";
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
  const [loading, setLoading] = useState(true);
  const [savingLlm, setSavingLlm] = useState(false);
  const [savingTts, setSavingTts] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedFlashLlm, setSavedFlashLlm] = useState(false);
  const [savedFlashTts, setSavedFlashTts] = useState(false);
  const [requestState, setRequestState] = useState<RequestState | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        setError(null);
        const [llm, tts] = await Promise.all([bridge.showLLMConfig(), bridge.showTTSConfig()]);
        if (!active) return;
        setLlmForm(toLLMForm(llm));
        setTtsForm(toTTSForm(tts));
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="h-full overflow-y-auto px-6 lg:px-12 py-8"
    >
      <div className="max-w-xl mx-auto">
        <header className="mb-8 border-b border-outline pb-6">
          <h1 className="text-2xl font-headline font-bold text-primary">Settings</h1>
          <p className="text-secondary text-sm mt-2">
            Language model (interview and script) and text-to-speech. Stored only on this device via Python
            config files.
          </p>
        </header>

        {loading ? (
          <div className="py-16 flex justify-center text-secondary">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : (
          <>
            <section className="mb-10">
              <div className="flex items-center gap-2 mb-4 text-secondary">
                <Sparkles className="w-4 h-4" />
                <h2 className="text-[11px] font-semibold uppercase tracking-wider">Language model</h2>
              </div>
              <p className="text-[12px] text-outline mb-3">
                OpenAI-compatible HTTP API for chat (interview turns) and script generation. Same fields as{" "}
                <code className="text-secondary">.local-data/config/llm.json</code>.
              </p>
              <div className="space-y-4 rounded-xl border border-outline bg-surface-container p-4">
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Provider</span>
                  <select
                    value={llmForm.provider}
                    onChange={(e) => updateLlm("provider", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  >
                    <option value="openai_compatible">openai_compatible</option>
                    <option value="mock">mock</option>
                  </select>
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Model</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="e.g. gpt-4o-mini, Qwen/Qwen3.5-27B"
                    value={llmForm.model}
                    onChange={(e) => updateLlm("model", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Base URL</span>
                  <input
                    type="url"
                    autoComplete="off"
                    placeholder="https://api.openai.com/v1 or your compatible endpoint"
                    value={llmForm.base_url}
                    onChange={(e) => updateLlm("base_url", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">API key</span>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="LLM API key (interview and script)"
                    value={llmForm.api_key}
                    onChange={(e) => updateLlm("api_key", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40 font-mono"
                  />
                </label>
              </div>
              <div className="flex items-center gap-3 mt-4">
                <button
                  type="button"
                  onClick={() => void handleSaveLlm()}
                  disabled={loading || savingLlm}
                  className="px-4 py-2 rounded-lg bg-accent-amber hover:bg-accent-amber/90 text-black text-sm font-medium transition-colors"
                >
                  {savingLlm ? "Saving…" : "Save LLM"}
                </button>
                <span
                  className={cn(
                    "text-xs text-secondary transition-opacity",
                    savedFlashLlm ? "opacity-100" : "opacity-0",
                  )}
                >
                  Saved
                </span>
              </div>
            </section>

            <section className="mb-10">
              <div className="flex items-center gap-2 mb-4 text-secondary">
                <Volume2 className="w-4 h-4" />
                <h2 className="text-[11px] font-semibold uppercase tracking-wider">Text-to-speech</h2>
              </div>
              <div className="space-y-4 rounded-xl border border-outline bg-surface-container p-4">
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Provider</span>
                  <select
                    value={ttsForm.provider}
                    onChange={(e) => updateTts("provider", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  >
                    <option value="mock_remote">mock_remote</option>
                    <option value="openai_compatible">openai_compatible</option>
                    <option value="local_mlx">local_mlx</option>
                  </select>
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Model</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="qwen-tts-0.6B / gpt-4o-mini-tts / ..."
                    value={ttsForm.model}
                    onChange={(e) => updateTts("model", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Base URL</span>
                  <input
                    type="url"
                    autoComplete="off"
                    placeholder="https://..."
                    value={ttsForm.base_url}
                    onChange={(e) => updateTts("base_url", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">API key</span>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="TTS service API key"
                    value={ttsForm.api_key}
                    onChange={(e) => updateTts("api_key", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40 font-mono"
                  />
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Voice</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="alloy"
                    value={ttsForm.voice}
                    onChange={(e) => updateTts("voice", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Audio format</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="wav, mp3, m4a, or audio-only mp4"
                    value={ttsForm.audio_format}
                    onChange={(e) => updateTts("audio_format", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                  <p className="mt-1 text-[11px] text-secondary">
                    WAV is the safest default. M4A/MP4 here means audio-only output when the selected provider/runtime can produce it; this app does not create video MP4 files yet.
                  </p>
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Local runtime</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="mlx"
                    value={ttsForm.local_runtime}
                    onChange={(e) => updateTts("local_runtime", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Local model path</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="/absolute/path/to/model (optional)"
                    value={ttsForm.local_model_path}
                    onChange={(e) => updateTts("local_model_path", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-secondary mb-1.5 block">Local ref audio path</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="/absolute/path/to/ref.wav (optional)"
                    value={ttsForm.local_ref_audio_path}
                    onChange={(e) => updateTts("local_ref_audio_path", e.target.value)}
                    className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
                  />
                </label>
              </div>
              <div className="flex items-center gap-3 mt-4">
                <button
                  type="button"
                  onClick={() => void handleSaveTts()}
                  disabled={loading || savingTts}
                  className="px-4 py-2 rounded-lg bg-accent-amber hover:bg-accent-amber/90 text-black text-sm font-medium transition-colors"
                >
                  {savingTts ? "Saving…" : "Save TTS"}
                </button>
                <span
                  className={cn(
                    "text-xs text-secondary transition-opacity",
                    savedFlashTts ? "opacity-100" : "opacity-0",
                  )}
                >
                  Saved
                </span>
              </div>
            </section>
          </>
        )}

        {error && (
          <div className="mb-4 p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-red-400 text-sm">
            {error}
          </div>
        )}
        {!error && requestState?.phase === "running" && (
          <div className="mb-4 p-3 rounded-lg border border-outline text-secondary text-xs">
            {`${Math.round(requestState.progress_percent)}% · ${requestState.message}`}
          </div>
        )}

        <p className="text-[11px] text-outline mt-8 leading-relaxed">
          Settings are persisted via Python core config files and shared globally across all sessions.
        </p>
      </div>
    </motion.div>
  );
}
