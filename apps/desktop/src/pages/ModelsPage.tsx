import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { getErrorMessage } from "../lib/requestState";
import { cn } from "../lib/utils";
import type { ModelStatus, TTSCapability, TTSProviderConfig } from "../types";

export function ModelsPage() {
  const bridge = useBridge();
  const navigate = useNavigate();
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [capability, setCapability] = useState<TTSCapability | null>(null);
  const [config, setConfig] = useState<TTSProviderConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [catalog, status, tts] = await Promise.all([
        bridge.listModelsStatus(), bridge.getLocalTTSCapability(), bridge.showTTSConfig(),
      ]);
      setModels(catalog);
      setCapability(status);
      setConfig(tts);
      setError("");
    } catch (err) {
      setError(getErrorMessage(err, "Could not read the speech service status."));
    } finally {
      setLoading(false);
    }
  }, [bridge]);
  useEffect(() => { void refresh(); }, [refresh]);

  const available = Boolean(capability?.available);
  return (
    <div className="h-full overflow-y-auto px-6 py-8 lg:px-10">
      <div className="mx-auto w-full max-w-3xl">
        <div className="mb-6 flex items-center justify-between gap-4">
          <h1 className="text-2xl font-headline font-semibold text-primary">Models</h1>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-secondary transition-colors hover:bg-primary/5 hover:text-primary disabled:opacity-50"
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
        {error ? <p role="alert" className="mb-4 text-sm text-red-700 dark:text-red-300">{error}</p> : null}

        <section className="rounded-xl border border-outline px-4 py-4">
          <div className="flex items-center gap-2">
            <span className={cn("h-2 w-2 shrink-0 rounded-full", available ? "bg-emerald-500" : "bg-amber-500")} aria-hidden />
            <h2 className="text-[14px] font-semibold text-primary">
              Local speech service · {loading && !capability ? "Checking…" : available ? "Running" : "Not available"}
            </h2>
          </div>
          <dl className="mt-3 grid grid-cols-[110px_1fr] gap-y-1.5 text-[13px]">
            <dt className="text-secondary">Address</dt>
            <dd className="break-all text-primary">{config?.base_url || "http://127.0.0.1:8090/v1"}</dd>
            <dt className="text-secondary">Active model</dt>
            <dd className="break-all text-primary">{capability?.current_model || "—"}</dd>
          </dl>
          {capability?.reasons.map((reason) => (
            <p key={reason} className="mt-2 text-[13px] text-amber-700 dark:text-amber-300">{reason}</p>
          ))}
          {!available && !loading ? (
            <p className="mt-3 text-[12px] text-secondary">
              Start it from the repository root with <code className="font-mono">./speech-service/service.sh start</code>.
            </p>
          ) : null}
        </section>

        <h2 className="mt-8 mb-2 text-[13px] font-semibold text-primary">Speech models</h2>
        <ul className="divide-y divide-outline rounded-xl border border-outline">
          {models.map((model) => (
            <li key={model.model_name} className="flex items-start justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <p className="text-[14px] font-medium text-primary">{model.display_name}</p>
                <p className="mt-0.5 break-all text-[12px] text-secondary">{model.hf_repo_id || model.model_name}</p>
                {model.recommendation ? <p className="mt-1 text-[12px] text-secondary">{model.recommendation}</p> : null}
              </div>
              {model.ready ? (
                <span className="shrink-0 rounded-md bg-emerald-500/10 px-2 py-0.5 text-[12px] font-medium text-emerald-700 dark:text-emerald-300">Active</span>
              ) : null}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[12px] leading-5 text-secondary">
          The speech service picks its model from <code className="font-mono">speech-service/.env</code> and handles downloads itself.
          It supports preset voices only — no cloning, styles, or speed changes.{" "}
          <button type="button" onClick={() => navigate("/settings")} className="text-primary underline underline-offset-2">
            Language models are configured in Settings.
          </button>
        </p>
      </div>
    </div>
  );
}
