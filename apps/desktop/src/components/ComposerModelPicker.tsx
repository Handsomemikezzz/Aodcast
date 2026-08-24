import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, Loader2 } from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { LLMProviderConfig, LLMProviderModel, LLMProviderStatus } from "../types";
import { cn } from "../lib/utils";

/** Compact Chinese labels for the composer trigger (matches Cursor-style intensity chips). */
const REASONING_EFFORT_LABELS: Record<string, string> = {
  auto: "自动",
  none: "无",
  minimal: "最低",
  low: "低",
  medium: "中",
  high: "高",
  xhigh: "极高",
  max: "最大",
  ultra: "超高",
};

const PRESET_MODELS_BY_URL: { keyword: string; models: string[] }[] = [
  { keyword: "deepseek", models: ["deepseek-v4-flash", "deepseek-v4-pro"] },
  { keyword: "openai.com", models: ["gpt-5.5-instant", "gpt-5.4-mini", "gpt-5.4-pro"] },
  { keyword: "anthropic", models: ["claude-sonnet-4.6", "claude-opus-4.8"] },
  { keyword: "11434", models: ["qwen2.5", "llama3"] },
  { keyword: "siliconflow", models: ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"] },
];

function reasoningEffortLabel(value: string): string {
  return REASONING_EFFORT_LABELS[value] ?? value;
}

function shortModelLabel(modelId: string, displayName?: string | null): string {
  const raw = (displayName || modelId || "模型").trim();
  // Prefer a compact chip: drop common vendor prefixes when the remainder stays readable.
  const withoutVendor = raw.replace(/^(openai\/|gpt-|claude-|google\/)/i, "");
  return withoutVendor.length >= 2 ? withoutVendor : raw;
}

function presetModelsFor(config: LLMProviderConfig): string[] {
  if (config.provider === "mock") return ["mock-model"];
  const url = config.base_url.toLowerCase();
  for (const preset of PRESET_MODELS_BY_URL) {
    if (url.includes(preset.keyword)) return preset.models;
  }
  return config.model ? [config.model] : [];
}

type ComposerModelPickerProps = {
  className?: string;
  disabled?: boolean;
  onConfigChange?: () => void;
};

export function ComposerModelPicker({
  className,
  disabled = false,
  onConfigChange,
}: ComposerModelPickerProps) {
  const bridge = useBridge();
  const navigate = useNavigate();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<LLMProviderConfig | null>(null);
  const [codexStatus, setCodexStatus] = useState<LLMProviderStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const llm = await bridge.showLLMConfig();
      setConfig(llm);
      if (llm.provider === "codex_subscription") {
        try {
          setCodexStatus(await bridge.showLLMProviderStatus());
        } catch {
          setCodexStatus(null);
        }
      } else {
        setCodexStatus(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法加载模型配置");
      setConfig(null);
      setCodexStatus(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [bridge]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const isCodex = config?.provider === "codex_subscription";
  const codexModels = isCodex ? (codexStatus?.models ?? []) : [];
  const selectedCodexModel: LLMProviderModel | null =
    codexModels.find((model) => model.id === config?.model) ?? null;
  const apiModels = config && !isCodex
    ? Array.from(new Set([...presetModelsFor(config), config.model].filter(Boolean)))
    : [];
  const reasoningOptions = selectedCodexModel?.supported_reasoning_efforts ?? [];
  const showReasoning = Boolean(isCodex && selectedCodexModel);

  const triggerModelLabel = isCodex
    ? shortModelLabel(config?.model ?? "", selectedCodexModel?.display_name)
    : shortModelLabel(config?.model ?? "");
  const effortValue = config?.reasoning_effort || "auto";
  const triggerEffortLabel = showReasoning
    ? effortValue === "auto"
      ? selectedCodexModel?.default_reasoning_effort
        ? reasoningEffortLabel(selectedCodexModel.default_reasoning_effort)
        : "自动"
      : reasoningEffortLabel(effortValue)
    : null;

  const persist = async (next: { model?: string; reasoning_effort?: string }) => {
    if (!config || saving) return;
    const model = next.model ?? config.model;
    let reasoningEffort = next.reasoning_effort ?? config.reasoning_effort ?? "auto";
    if (isCodex && next.model) {
      const nextModel = codexModels.find((entry) => entry.id === next.model);
      if (
        reasoningEffort !== "auto"
        && nextModel
        && !nextModel.supported_reasoning_efforts.includes(reasoningEffort)
      ) {
        reasoningEffort = "auto";
      }
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await bridge.configureLLMProvider({
        provider: config.provider,
        base_url: config.base_url,
        api_key: config.api_key,
        model,
        reasoning_effort: reasoningEffort,
      });
      setConfig(updated);
      onConfigChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存模型配置失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={cn("relative shrink-0", className)} ref={rootRef}>
      <button
        type="button"
        disabled={disabled || loading}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "inline-flex max-w-[220px] items-center gap-1 rounded-lg px-1.5 py-1 text-[12px] text-secondary",
          "hover:bg-surface-container-high/70 hover:text-primary transition-colors",
          "disabled:opacity-40 disabled:pointer-events-none",
          open && "bg-surface-container-high/70 text-primary",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="选择模型与推理强度"
      >
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
        ) : (
          <>
            <span className="truncate font-medium tracking-tight">
              {triggerModelLabel}
              {triggerEffortLabel ? ` ${triggerEffortLabel}` : ""}
            </span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-70" />
          </>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.14, ease: "easeOut" }}
            className="absolute bottom-full right-0 mb-2 w-[260px] rounded-2xl border border-outline theme-modal-surface backdrop-blur-2xl p-3 shadow-2xl z-40"
            role="listbox"
          >
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-outline">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-secondary">
                模型
              </span>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-amber" /> : null}
            </div>

            {error ? (
              <p className="mb-2 text-[11px] leading-relaxed text-red-300">{error}</p>
            ) : null}

            {loading ? (
              <div className="py-6 text-center text-xs text-secondary">加载中…</div>
            ) : !config ? (
              <div className="space-y-2 py-2">
                <p className="text-[12px] text-secondary leading-relaxed">尚未配置语言模型。</p>
                <button
                  type="button"
                  className="inline-flex text-[12px] font-medium text-accent-amber hover:underline"
                  onClick={() => {
                    setOpen(false);
                    navigate("/settings");
                  }}
                >
                  前往设置
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="max-h-44 overflow-y-auto space-y-0.5 mac-scrollbar">
                  {isCodex ? (
                    codexModels.length === 0 ? (
                      <p className="px-2 py-3 text-[12px] text-secondary leading-relaxed">
                        {codexStatus?.authenticated
                          ? "暂无可用模型。"
                          : "请先在设置中连接 ChatGPT 订阅。"}
                      </p>
                    ) : (
                      codexModels.map((model) => {
                        const selected = model.id === config.model;
                        return (
                          <button
                            key={model.id}
                            type="button"
                            disabled={saving}
                            onClick={() => void persist({ model: model.id })}
                            className={cn(
                              "w-full flex items-center justify-between gap-2 rounded-xl px-2.5 py-2 text-left text-[12px] transition-colors",
                              selected
                                ? "bg-accent-amber/10 text-accent-amber"
                                : "text-primary hover:bg-surface-container-high/80",
                            )}
                          >
                            <span className="truncate">
                              {model.display_name || model.id}
                              {model.is_default ? (
                                <span className="ml-1 text-[10px] text-secondary">推荐</span>
                              ) : null}
                            </span>
                            {selected ? <Check className="h-3.5 w-3.5 shrink-0" /> : null}
                          </button>
                        );
                      })
                    )
                  ) : (
                    apiModels.map((modelId) => {
                      const selected = modelId === config.model;
                      return (
                        <button
                          key={modelId}
                          type="button"
                          disabled={saving}
                          onClick={() => void persist({ model: modelId })}
                          className={cn(
                            "w-full flex items-center justify-between gap-2 rounded-xl px-2.5 py-2 text-left text-[12px] transition-colors",
                            selected
                              ? "bg-accent-amber/10 text-accent-amber"
                              : "text-primary hover:bg-surface-container-high/80",
                          )}
                        >
                          <span className="truncate">{modelId}</span>
                          {selected ? <Check className="h-3.5 w-3.5 shrink-0" /> : null}
                        </button>
                      );
                    })
                  )}
                </div>

                {showReasoning ? (
                  <div className="border-t border-outline pt-2.5 space-y-1.5">
                    <span className="px-1 text-[11px] font-semibold uppercase tracking-wider text-secondary">
                      推理强度
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => void persist({ reasoning_effort: "auto" })}
                        className={cn(
                          "rounded-lg px-2 py-1 text-[11px] font-medium transition-colors",
                          effortValue === "auto"
                            ? "bg-accent-amber/15 text-accent-amber"
                            : "bg-surface-container-high/70 text-secondary hover:text-primary",
                        )}
                      >
                        自动
                      </button>
                      {reasoningOptions.map((effort) => (
                        <button
                          key={effort}
                          type="button"
                          disabled={saving}
                          onClick={() => void persist({ reasoning_effort: effort })}
                          className={cn(
                            "rounded-lg px-2 py-1 text-[11px] font-medium transition-colors",
                            effortValue === effort
                              ? "bg-accent-amber/15 text-accent-amber"
                              : "bg-surface-container-high/70 text-secondary hover:text-primary",
                          )}
                        >
                          {reasoningEffortLabel(effort)}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
