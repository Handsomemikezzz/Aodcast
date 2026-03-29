import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ChevronRight,
  CircleCheck,
  Download,
  ExternalLink,
  Loader2,
  Trash2,
} from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import type { ModelStatus } from "../types";
import { cn } from "../lib/utils";

function formatSizeMb(sizeMb?: number): string {
  if (sizeMb == null || !Number.isFinite(sizeMb)) return "—";
  if (sizeMb < 1024) return `${Math.round(sizeMb)} MB`;
  return `${(sizeMb / 1024).toFixed(2)} GB`;
}

export function ModelsPage() {
  const bridge = useBridge();
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyName, setBusyName] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const list = await bridge.listModelsStatus();
      setModels(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load models");
    } finally {
      setLoading(false);
    }
  }, [bridge]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const t = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const voiceModels = models.filter((m) => m.category === "voice");
  const whisperModels = models.filter((m) => m.category === "transcription");

  const sections: { label: string; items: ModelStatus[] }[] = [
    { label: "Voice generation", items: voiceModels },
    { label: "Transcription", items: whisperModels },
  ];

  const handleDownload = async (m: ModelStatus) => {
    if (m.category !== "voice") return;
    setBusyName(m.model_name);
    try {
      const result = await bridge.downloadModel(m.model_name);
      window.alert(result.path ? `Download finished.\n\n${result.path}` : "Download finished.");
      await refresh();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusyName(null);
    }
  };

  const handleDelete = async (m: ModelStatus) => {
    if (m.category !== "voice") return;
    if (!window.confirm(`Remove ${m.display_name} from the local models folder?`)) return;
    setBusyName(m.model_name);
    try {
      await bridge.deleteModel(m.model_name);
      await refresh();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusyName(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="h-full flex flex-col overflow-hidden"
    >
      <div className="flex-1 overflow-y-auto px-6 lg:px-12 py-8">
        <div className="max-w-4xl mx-auto">
          <header className="shrink-0 pb-4">
            <h1 className="text-lg font-headline font-semibold text-primary">Models</h1>
            <p className="text-sm text-secondary mt-1">
              Download and manage AI models for voice generation and transcription.
            </p>
          </header>

          {error && (
            <div className="mb-4 p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-red-400 text-sm">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-16 text-secondary">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : (
            <div className="space-y-6">
              {sections.map((section) => (
                <div key={section.label}>
                  <h2 className="text-[11px] font-semibold text-secondary uppercase tracking-wider mb-2 px-1">
                    {section.label}
                  </h2>
                  <div className="rounded-xl border border-outline overflow-hidden divide-y divide-outline-variant bg-surface-container-low/30">
                    {section.items.map((m) => {
                      const busy = busyName === m.model_name;
                      const isDownloading = busy || m.downloading;
                      return (
                        <div
                          key={m.model_name}
                          className="flex items-center gap-3 px-3 py-2.5 hover:bg-surface-container-high/40 transition-colors group"
                        >
                          <div className="shrink-0">
                            {isDownloading ? (
                              <Loader2 className="h-4 w-4 animate-spin text-secondary" />
                            ) : m.downloaded ? (
                              <CircleCheck
                                className={cn(
                                  "h-4 w-4",
                                  m.loaded ? "text-accent-amber" : "text-emerald-500/90",
                                )}
                              />
                            ) : (
                              <Download className="h-4 w-4 text-secondary/50" />
                            )}
                          </div>

                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-primary">{m.display_name}</p>
                            {m.hf_repo_id ? (
                              <a
                                href={`https://huggingface.co/${m.hf_repo_id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[10px] text-secondary hover:text-accent-amber inline-flex items-center gap-0.5 truncate max-w-full"
                              >
                                <span className="truncate">{m.hf_repo_id}</span>
                                <ExternalLink className="h-2.5 w-2.5 shrink-0" />
                              </a>
                            ) : (
                              <p className="text-[10px] text-secondary/80">On-device ASR</p>
                            )}
                          </div>

                          <div className="shrink-0 flex items-center gap-2">
                            {m.loaded && (
                              <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-accent-amber/15 text-accent-amber border border-accent-amber/25">
                                Loaded
                              </span>
                            )}
                            {m.downloaded && !isDownloading && (
                              <span className="text-xs text-secondary tabular-nums">
                                {formatSizeMb(m.size_mb)}
                              </span>
                            )}
                            {m.category === "voice" && !m.downloaded && !isDownloading && (
                              <button
                                type="button"
                                onClick={() => void handleDownload(m)}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-surface-container-high text-primary border border-outline hover:bg-surface-container-highest"
                              >
                                <Download className="h-3.5 w-3.5" />
                                Download
                              </button>
                            )}
                            {m.category === "voice" && m.downloaded && !isDownloading && (
                              <button
                                type="button"
                                title="Delete local files"
                                onClick={() => void handleDelete(m)}
                                className="p-1.5 rounded-md border border-outline text-secondary hover:text-primary hover:bg-surface-container-high"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            )}
                            {m.category === "transcription" && !m.downloaded && (
                              <button
                                type="button"
                                disabled
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-surface-container-low text-secondary border border-outline opacity-50 cursor-not-allowed"
                              >
                                <Download className="h-3.5 w-3.5" />
                                Download
                              </button>
                            )}
                          </div>

                          <ChevronRight className="h-4 w-4 text-secondary/30 group-hover:text-secondary/60 shrink-0" />
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              <p className="text-[11px] text-outline px-1 leading-relaxed">
                Voice downloads use{" "}
                <code className="text-secondary">scripts/model-download/download_qwen3_tts_mlx.py</code> (requires{" "}
                <code className="text-secondary">huggingface_hub</code>
                ). Set <code className="text-secondary">AODCAST_HF_MODEL_BASE</code> to choose a storage folder; default
                is <code className="text-secondary">&lt;repo&gt;/models</code>.
              </p>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
