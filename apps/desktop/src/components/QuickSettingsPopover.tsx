import React, { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { SlidersHorizontal, Sparkles, Volume2, Check, Loader2, ChevronDown } from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { LLMProviderConfig, TTSProviderConfig } from "../types";
import { cn } from "../lib/utils";

type QuickSettingsPopoverProps = {
  className?: string;
  onConfigChange?: () => void;
};

type PresetConfig = {
  baseUrlKeyword: string;
  models: string[];
};

const PRESET_MODELS_MAP: Record<string, PresetConfig> = {
  deepseek: {
    baseUrlKeyword: "deepseek",
    models: ["deepseek-v4-flash", "deepseek-v4-pro"],
  },
  openai: {
    baseUrlKeyword: "openai.com",
    models: ["gpt-5.5-instant", "gpt-5.4-mini", "gpt-5.4-pro"],
  },
  anthropic: {
    baseUrlKeyword: "anthropic",
    models: ["claude-sonnet-4.6", "claude-opus-4.8"],
  },
  ollama: {
    baseUrlKeyword: "11434",
    models: ["qwen2.5", "llama3"],
  },
  siliconflow: {
    baseUrlKeyword: "siliconflow",
    models: ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"],
  },
};

const STANDARD_TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"];

export function QuickSettingsPopover({ className, onConfigChange }: QuickSettingsPopoverProps) {
  const bridge = useBridge();
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  
  const [llmConfig, setLlmConfig] = useState<LLMProviderConfig | null>(null);
  const [ttsConfig, setTTSConfig] = useState<TTSProviderConfig | null>(null);
  
  const [savingField, setSavingField] = useState<"llm" | "tts" | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<"llm" | "tts" | null>(null);
  
  const popoverRef = useRef<HTMLDivElement>(null);

  const fetchConfigs = async () => {
    try {
      setLoading(true);
      const [llm, tts] = await Promise.all([bridge.showLLMConfig(), bridge.showTTSConfig()]);
      setLlmConfig(llm);
      setTTSConfig(tts);
    } catch (e) {
      console.error("Failed to load quick settings configs:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      void fetchConfigs();
    }
  }, [isOpen]);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Infer preset list
  const getPresetModels = () => {
    if (!llmConfig) return [];
    if (llmConfig.provider === "mock") return ["mock-model"];
    
    const url = llmConfig.base_url.toLowerCase();
    for (const preset of Object.values(PRESET_MODELS_MAP)) {
      if (url.includes(preset.baseUrlKeyword)) {
        return preset.models;
      }
    }
    return [];
  };

  const handleLLMModelChange = async (newModel: string) => {
    if (!llmConfig) return;
    setSavingField("llm");
    setSaveSuccess(null);
    try {
      const updated = await bridge.configureLLMProvider({
        provider: llmConfig.provider,
        base_url: llmConfig.base_url,
        api_key: llmConfig.api_key,
        model: newModel,
      });
      setLlmConfig(updated);
      setSaveSuccess("llm");
      setTimeout(() => setSaveSuccess(null), 1500);
      onConfigChange?.();
    } catch (e) {
      console.error("Failed to update inline LLM model:", e);
    } finally {
      setSavingField(null);
    }
  };

  const handleTTSVoiceChange = async (newVoice: string) => {
    if (!ttsConfig) return;
    setSavingField("tts");
    setSaveSuccess(null);
    try {
      const updated = await bridge.configureTTSProvider({
        provider: ttsConfig.provider,
        model: ttsConfig.model,
        base_url: ttsConfig.base_url,
        api_key: ttsConfig.api_key,
        voice: newVoice,
        audio_format: ttsConfig.audio_format,
        local_runtime: ttsConfig.local_runtime,
        local_model_path: ttsConfig.local_model_path,
        local_ref_audio_path: ttsConfig.local_ref_audio_path,
      });
      setTTSConfig(updated);
      setSaveSuccess("tts");
      setTimeout(() => setSaveSuccess(null), 1500);
      onConfigChange?.();
    } catch (e) {
      console.error("Failed to update inline TTS voice:", e);
    } finally {
      setSavingField(null);
    }
  };

  const presetModels = getPresetModels();
  const ttsUsesLocal = ttsConfig?.provider === "local_mlx";

  return (
    <div className={cn("relative z-30 inline-block", className)} ref={popoverRef}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-xl border border-outline bg-surface-container-high/50 text-secondary hover:text-primary hover:bg-surface-container-high hover:border-accent-amber/20 active:scale-95 transition-all",
          isOpen && "bg-surface-container-high border-accent-amber/20 text-accent-amber"
        )}
        title="Quick Settings"
      >
        <SlidersHorizontal className="w-4 h-4" />
      </button>

      {/* Floating Panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute right-0 mt-2.5 w-[260px] rounded-2xl theme-modal-surface backdrop-blur-2xl p-4 shadow-2xl text-primary"
          >
            <div className="flex items-center justify-between border-b border-outline pb-2.5 mb-3.5">
              <span className="text-[12px] font-semibold text-on-surface-variant font-headline tracking-wide uppercase">Quick Config</span>
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-secondary" />}
            </div>

            {loading ? (
              <div className="py-8 text-center text-xs text-secondary">Syncing settings…</div>
            ) : (
              <div className="space-y-4">
                
                {/* 1. LLM quick selector */}
                {llmConfig && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-1.5 text-secondary font-medium">
                        <Sparkles className="w-3.5 h-3.5 text-accent-amber" />
                        LLM Model
                      </span>
                      {savingField === "llm" && <Loader2 className="w-3 h-3 animate-spin text-accent-amber" />}
                      {saveSuccess === "llm" && <Check className="w-3 h-3 text-emerald-400" />}
                    </div>

                    {presetModels.length > 0 ? (
                      <div className="relative">
                        <select
                          value={llmConfig.model}
                          onChange={(e) => void handleLLMModelChange(e.target.value)}
                          disabled={savingField !== null}
                          className="w-full rounded-lg border border-outline bg-surface-container-high px-3 py-1.5 text-xs text-primary outline-none focus:border-accent-amber/50 cursor-pointer appearance-none"
                        >
                          {presetModels.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-secondary pointer-events-none" />
                      </div>
                    ) : (
                      <div className="px-3 py-1.5 rounded-lg bg-surface-container-high border border-outline text-[11px] text-secondary leading-normal truncate">
                        {llmConfig.model || "(No Model Selected)"}
                        <p className="text-[9px] text-secondary/70 mt-0.5">Edit endpoint in Settings Page</p>
                      </div>
                    )}
                  </div>
                )}

                {/* 2. TTS Voice quick selector */}
                {ttsConfig && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-1.5 text-secondary font-medium">
                        <Volume2 className="w-3.5 h-3.5 text-accent-amber" />
                        Audio Voice
                      </span>
                      {savingField === "tts" && <Loader2 className="w-3 h-3 animate-spin text-accent-amber" />}
                      {saveSuccess === "tts" && <Check className="w-3 h-3 text-emerald-400" />}
                    </div>

                    {ttsUsesLocal ? (
                      <div className="px-3 py-2 rounded-lg bg-accent-amber/5 border border-accent-amber/10 text-[10px] leading-relaxed text-accent-amber/90">
                        Local Qwen MLX synthesis is active. Voices are scoped per-script.
                      </div>
                    ) : ttsConfig.provider === "mock_remote" ? (
                      <div className="px-3 py-1.5 rounded-lg bg-surface-container-high border border-outline text-[11px] text-secondary">
                        Mock Voice Synthesizer
                      </div>
                    ) : (
                      <div className="relative">
                        <select
                          value={ttsConfig.voice}
                          onChange={(e) => void handleTTSVoiceChange(e.target.value)}
                          disabled={savingField !== null}
                          className="w-full rounded-lg border border-outline bg-surface-container-high px-3 py-1.5 text-xs text-primary outline-none focus:border-accent-amber/50 cursor-pointer appearance-none"
                        >
                          {STANDARD_TTS_VOICES.map((v) => (
                            <option key={v} value={v}>
                              {v}
                            </option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-secondary pointer-events-none" />
                      </div>
                    )}
                  </div>
                )}

              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
