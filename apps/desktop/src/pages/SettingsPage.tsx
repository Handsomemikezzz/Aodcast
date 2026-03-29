import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Cpu, Volume2 } from "lucide-react";
import {
  loadUserSettings,
  saveUserSettings,
  type LlmProviderId,
  type UserAppSettings,
} from "../lib/userSettings";
import { cn } from "../lib/utils";

const LLM_OPTIONS: { id: LlmProviderId; label: string }[] = [
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Google Gemini" },
  { id: "anthropic", label: "Anthropic" },
  { id: "custom", label: "Custom (OpenAI-compatible)" },
];

export function SettingsPage() {
  const [form, setForm] = useState<UserAppSettings>(() => loadUserSettings());
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    setForm(loadUserSettings());
  }, []);

  const update = <K extends keyof UserAppSettings>(key: K, value: UserAppSettings[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    saveUserSettings(form);
    setSavedFlash(true);
    window.setTimeout(() => setSavedFlash(false), 2000);
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
            API keys for chat, script summarization, and cloud TTS. Stored only on this device.
          </p>
        </header>

        <section className="mb-10">
          <div className="flex items-center gap-2 mb-4 text-secondary">
            <Cpu className="w-4 h-4" />
            <h2 className="text-[11px] font-semibold uppercase tracking-wider">Chat &amp; summarization (LLM)</h2>
          </div>
          <div className="space-y-4 rounded-xl border border-outline bg-surface-container p-4">
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Provider</span>
              <select
                value={form.llmProvider}
                onChange={(e) => update("llmProvider", e.target.value as LlmProviderId)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary outline-none focus:border-accent-amber/40"
              >
                {LLM_OPTIONS.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            {form.llmProvider === "custom" && (
              <label className="block">
                <span className="text-[12px] font-medium text-secondary mb-1.5 block">Base URL</span>
                <input
                  type="url"
                  autoComplete="off"
                  placeholder="https://…"
                  value={form.llmBaseUrl}
                  onChange={(e) => update("llmBaseUrl", e.target.value)}
                  className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
                />
              </label>
            )}
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">API key</span>
              <input
                type="password"
                autoComplete="off"
                placeholder="sk-… or your provider key"
                value={form.llmApiKey}
                onChange={(e) => update("llmApiKey", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40 font-mono"
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Model (optional)</span>
              <input
                type="text"
                autoComplete="off"
                placeholder="e.g. gpt-4o, gemini-2.0-flash"
                value={form.llmModel}
                onChange={(e) => update("llmModel", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
              />
            </label>
          </div>
        </section>

        <section className="mb-10">
          <div className="flex items-center gap-2 mb-4 text-secondary">
            <Volume2 className="w-4 h-4" />
            <h2 className="text-[11px] font-semibold uppercase tracking-wider">Text-to-speech (API)</h2>
          </div>
          <div className="space-y-4 rounded-xl border border-outline bg-surface-container p-4">
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Provider name</span>
              <input
                type="text"
                autoComplete="off"
                placeholder="e.g. openai, elevenlabs, your-vendor"
                value={form.ttsProvider}
                onChange={(e) => update("ttsProvider", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">API key</span>
              <input
                type="password"
                autoComplete="off"
                placeholder="TTS service API key"
                value={form.ttsApiKey}
                onChange={(e) => update("ttsApiKey", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40 font-mono"
              />
            </label>
          </div>
        </section>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-2 rounded-lg bg-accent-amber hover:bg-accent-amber/90 text-black text-sm font-medium transition-colors"
          >
            Save
          </button>
          <span
            className={cn(
              "text-xs text-secondary transition-opacity",
              savedFlash ? "opacity-100" : "opacity-0",
            )}
          >
            Saved
          </span>
        </div>

        <p className="text-[11px] text-outline mt-8 leading-relaxed">
          Local orchestration may still use its own environment or config files until the desktop bridge exposes these
          fields.
        </p>
      </div>
    </motion.div>
  );
}
