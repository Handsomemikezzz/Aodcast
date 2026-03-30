import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Volume2 } from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { TTSProviderConfig } from "../types";
import { cn } from "../lib/utils";

type SettingsForm = {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  voice: string;
  audio_format: string;
  local_runtime: string;
  local_model_path: string;
};

function toForm(config: TTSProviderConfig): SettingsForm {
  return {
    provider: config.provider,
    model: config.model,
    base_url: config.base_url,
    api_key: config.api_key,
    voice: config.voice,
    audio_format: config.audio_format,
    local_runtime: config.local_runtime,
    local_model_path: config.local_model_path,
  };
}

export function SettingsPage() {
  const bridge = useBridge();
  const [form, setForm] = useState<SettingsForm>({
    provider: "mock_remote",
    model: "mock-voice",
    base_url: "",
    api_key: "",
    voice: "alloy",
    audio_format: "wav",
    local_runtime: "mlx",
    local_model_path: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        setError(null);
        const config = await bridge.showTTSConfig();
        if (!active) return;
        setForm(toForm(config));
      } catch (e) {
        if (!active) return;
        setError(e instanceof Error ? e.message : "Failed to load TTS settings.");
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

  const update = <K extends keyof SettingsForm>(key: K, value: SettingsForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const next = await bridge.configureTTSProvider({
        provider: form.provider,
        model: form.model,
        base_url: form.base_url,
        api_key: form.api_key,
        voice: form.voice,
        audio_format: form.audio_format,
        local_runtime: form.local_runtime,
        local_model_path: form.local_model_path,
      });
      setForm(toForm(next));
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save TTS settings.");
    } finally {
      setSaving(false);
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
          <p className="text-secondary text-sm mt-2">Global TTS provider config. Stored only on this device.</p>
        </header>

        {loading ? (
          <div className="py-16 flex justify-center text-secondary">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : (
          <section className="mb-10">
          <div className="flex items-center gap-2 mb-4 text-secondary">
            <Volume2 className="w-4 h-4" />
            <h2 className="text-[11px] font-semibold uppercase tracking-wider">Text-to-speech</h2>
          </div>
          <div className="space-y-4 rounded-xl border border-outline bg-surface-container p-4">
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Provider</span>
              <select
                value={form.provider}
                onChange={(e) => update("provider", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
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
                value={form.model}
                onChange={(e) => update("model", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Base URL</span>
              <input
                type="url"
                autoComplete="off"
                placeholder="https://..."
                value={form.base_url}
                onChange={(e) => update("base_url", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">API key</span>
              <input
                type="password"
                autoComplete="off"
                placeholder="TTS service API key"
                value={form.api_key}
                onChange={(e) => update("api_key", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40 font-mono"
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Voice</span>
              <input
                type="text"
                autoComplete="off"
                placeholder="alloy"
                value={form.voice}
                onChange={(e) => update("voice", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Audio format</span>
              <input
                type="text"
                autoComplete="off"
                placeholder="wav or mp3"
                value={form.audio_format}
                onChange={(e) => update("audio_format", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Local runtime</span>
              <input
                type="text"
                autoComplete="off"
                placeholder="mlx"
                value={form.local_runtime}
                onChange={(e) => update("local_runtime", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
              />
            </label>
            <label className="block">
              <span className="text-[12px] font-medium text-secondary mb-1.5 block">Local model path</span>
              <input
                type="text"
                autoComplete="off"
                placeholder="/absolute/path/to/model (optional)"
                value={form.local_model_path}
                onChange={(e) => update("local_model_path", e.target.value)}
                className="w-full rounded-lg border border-outline bg-background px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/40"
              />
            </label>
          </div>
          </section>
        )}

        {error && (
          <div className="mb-4 p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-red-400 text-sm">
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={loading || saving}
            className="px-4 py-2 rounded-lg bg-accent-amber hover:bg-accent-amber/90 text-black text-sm font-medium transition-colors"
          >
            {saving ? "Saving..." : "Save"}
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
          Settings are persisted via Python core config files and shared globally across all sessions.
        </p>
      </div>
    </motion.div>
  );
}
