import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { getErrorMessage } from "../lib/requestState";
import type { ModelStatus, TTSCapability, TTSProviderConfig } from "../types";

export function ModelsPage() {
  const bridge = useBridge();
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
      setError(getErrorMessage(err, "无法读取语音服务状态。"));
    } finally {
      setLoading(false);
    }
  }, [bridge]);
  useEffect(() => { void refresh(); }, [refresh]);
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-primary">语音服务与模型</h1>
        <button type="button" onClick={() => void refresh()} disabled={loading}
          className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-outline px-4 text-sm text-primary disabled:opacity-50">
          <RefreshCw className="h-4 w-4" />{loading ? "读取中…" : "刷新"}
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
      <section className="space-y-3 rounded-2xl border border-outline bg-surface-container-low p-5">
        <h2 className="text-sm font-semibold text-primary">本机 HTTP 服务 · {capability?.available ? "可用" : "不可用"}</h2>
        <p className="break-all text-sm text-secondary">{config?.base_url || "http://127.0.0.1:8090/v1"}</p>
        <p className="text-sm text-secondary">当前模型：{capability?.current_model || "尚未读取"}</p>
        {capability?.reasons.map((reason) => <p key={reason} className="text-sm text-amber-600">{reason}</p>)}
        <p className="text-xs leading-6 text-secondary">在独立语音服务目录运行 ./service.sh start。模型由该服务的 .env 选择，Aodcast 不管理下载或权重目录。服务负责长文切片、拼接和内存管理。</p>
      </section>
      <div className="grid gap-4 sm:grid-cols-2">
        {models.map((model) => (
          <article key={model.model_name} className="space-y-2 rounded-2xl border border-outline p-5">
            <h2 className="text-sm font-semibold text-primary">{model.display_name}</h2>
            <p className="break-all text-xs text-secondary">{model.hf_repo_id || model.model_name}</p>
            <p className="text-xs text-secondary">{model.ready ? "服务当前模型" : "可在服务 .env 中切换"}</p>
            <p className="text-xs leading-6 text-secondary">{model.recommendation || "预设音色 · WAV · 正常语速"}</p>
          </article>
        ))}
      </div>
      <p className="text-xs text-secondary">本机服务不支持音色克隆、参考音频、风格或变速。云端 LLM 模型仍在设置及对话模型选择器中配置。</p>
    </div>
  );
}
