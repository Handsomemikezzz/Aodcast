import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  CircleCheck,
  Download,
  ExternalLink,
  FolderOpen,
  HardDrive,
  Loader2,
  RotateCcw,
  Trash2,
  XCircle,
} from "lucide-react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useBridge } from "../lib/BridgeContext";
import { pickDirectory, revealInFinder } from "../lib/shellOps";
import type { ModelStatus, ModelStorageStatus, RequestState } from "../types";
import { cn } from "../lib/utils";
import {
  buildRequestState,
  getErrorMessage,
  getErrorRequestState,
  isActiveRequestState,
  isTerminalRequestState,
  withRequestStateFallback,
} from "../lib/requestState";

function formatSizeMb(sizeMb?: number): string {
  if (sizeMb == null || !Number.isFinite(sizeMb)) return "—";
  if (sizeMb < 1024) return `${Math.round(sizeMb)} MB`;
  return `${(sizeMb / 1024).toFixed(2)} GB`;
}

function formatProgress(value?: number): string {
  if (value == null || !Number.isFinite(value)) return "0%";
  return `${Math.round(Math.max(0, Math.min(100, value)))}%`;
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

type ProblemRecord = {
  id: string;
  operation: string;
  target?: string;
  message: string;
  createdAt: string;
};

function ProgressBar({ value }: { value?: number }) {
  const width = formatProgress(value);
  return (
    <div className="h-1.5 rounded-full bg-surface-container-high overflow-hidden">
      <div className="h-full rounded-full bg-accent-amber transition-[width] duration-300" style={{ width }} />
    </div>
  );
}

export function ModelsPage() {
  const bridge = useBridge();
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [storage, setStorage] = useState<ModelStorageStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyDownloadName, setBusyDownloadName] = useState<string | null>(null);
  const [busyDeleteName, setBusyDeleteName] = useState<string | null>(null);
  const [busyStorageAction, setBusyStorageAction] = useState<"migrate" | "reset" | null>(null);
  const [requestState, setRequestState] = useState<RequestState | null>(null);
  const [modelToDelete, setModelToDelete] = useState<ModelStatus | null>(null);
  const [problemsOpen, setProblemsOpen] = useState(false);
  const [problems, setProblems] = useState<ProblemRecord[]>([]);

  const currentStoragePath = storage?.current_base ?? "";
  const desktopShellAvailable = isTauriRuntime();

  const addProblem = useCallback((operation: string, message: string, target?: string) => {
    setProblems((prev) => [
      {
        id: `${operation}:${target ?? "global"}:${Date.now()}`,
        operation,
        target,
        message,
        createdAt: new Date().toISOString(),
      },
      ...prev,
    ]);
    setProblemsOpen(true);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [list, storageStatus] = await Promise.all([
        bridge.listModelsStatus(),
        bridge.showModelStorage(),
      ]);
      setModels(list);
      setStorage(storageStatus);
    } catch (e) {
      setError(getErrorMessage(e, "Failed to load models"));
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

  const pollTaskUntilTerminal = useCallback(
    async (taskId: string, fallbackOperation: string): Promise<RequestState | null> => {
      let latest: RequestState | null = null;
      for (let i = 0; i < 360; i += 1) {
        const state = await bridge.showTaskState(taskId).catch(() => null);
        if (state) {
          latest = state;
          setRequestState((prev) => {
            if ((prev?.phase === "cancelling" || prev?.phase === "cancelled") && state.phase === "running") return prev;
            return state;
          });
          if (isTerminalRequestState(state)) return state;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      return latest ?? buildRequestState(fallbackOperation, "failed", "Task timed out before reporting a final state.");
    },
    [bridge],
  );

  const handleDownload = async (m: ModelStatus) => {
    const taskId = `download_model:${m.model_name}`;
    setBusyDownloadName(m.model_name);
    setBusyDeleteName(null);
    setError(null);
    setRequestState(buildRequestState("download_model", "running", `Downloading model ${m.display_name}...`));
    try {
      const result = await bridge.downloadModel(m.model_name);
      const finalTaskId = result.task_id ?? taskId;
      const finalState = await pollTaskUntilTerminal(finalTaskId, "download_model");
      setRequestState(
        withRequestStateFallback(
          finalState ?? result.request_state,
          buildRequestState("download_model", "succeeded", result.path ? `Download finished: ${result.path}` : "Download finished."),
        ),
      );
      await refresh();
    } catch (e) {
      const errorState = getErrorRequestState(e);
      const message = getErrorMessage(e, "Download failed");
      if (errorState?.phase !== "cancelled") {
        setError(message);
        addProblem("download_model", message, m.model_name);
      }
      setRequestState(withRequestStateFallback(errorState, buildRequestState("download_model", "failed", "Download failed.")));
    } finally {
      setBusyDownloadName(null);
    }
  };

  const handleCancelDownload = async () => {
    if (!busyDownloadName) return;
    const taskId = `download_model:${busyDownloadName}`;
    try {
      const state = await bridge.cancelTask(taskId);
      setRequestState(state ?? buildRequestState("download_model", "cancelling", "Cancellation requested."));
    } catch (e) {
      const message = getErrorMessage(e, "Failed to request cancellation");
      setError(message);
      addProblem("cancel_task", message, busyDownloadName);
    }
  };

  const handleDelete = async (m: ModelStatus) => {
    setBusyDeleteName(m.model_name);
    setBusyDownloadName(null);
    setError(null);
    setRequestState(buildRequestState("delete_model", "running", `Removing model ${m.display_name}...`));
    try {
      await bridge.deleteModel(m.model_name);
      setRequestState(buildRequestState("delete_model", "succeeded", `Removed model ${m.display_name}.`));
      await refresh();
    } catch (e) {
      const message = getErrorMessage(e, "Delete failed");
      setError(message);
      addProblem("delete_model", message, m.model_name);
      setRequestState(withRequestStateFallback(getErrorRequestState(e), buildRequestState("delete_model", "failed", "Delete failed.")));
    } finally {
      setBusyDeleteName(null);
    }
  };

  const handleOpenStorage = async () => {
    if (!currentStoragePath) return;
    try {
      await revealInFinder(currentStoragePath);
    } catch (e) {
      const message = getErrorMessage(e, "Failed to open model storage folder");
      setError(message);
      addProblem("open_model_storage", message);
    }
  };

  const handleChangeStorage = async () => {
    try {
      const destination = await pickDirectory("Choose a folder for Aodcast local models");
      if (!destination) return;
      setBusyStorageAction("migrate");
      setError(null);
      setRequestState(buildRequestState("migrate_model_storage", "running", "Preparing model storage migration..."));
      const result = await bridge.migrateModelStorage(destination);
      const finalState = await pollTaskUntilTerminal(result.task_id ?? "migrate_model_storage", "migrate_model_storage");
      setRequestState(
        withRequestStateFallback(finalState ?? result.request_state, buildRequestState("migrate_model_storage", "succeeded", "Model storage migrated.")),
      );
      await refresh();
    } catch (e) {
      const message = getErrorMessage(e, "Model storage migration failed");
      setError(message);
      addProblem("migrate_model_storage", message);
      setRequestState(withRequestStateFallback(getErrorRequestState(e), buildRequestState("migrate_model_storage", "failed", message)));
    } finally {
      setBusyStorageAction(null);
    }
  };

  const handleResetStorage = async () => {
    setBusyStorageAction("reset");
    setError(null);
    setRequestState(buildRequestState("reset_model_storage", "running", "Resetting model storage..."));
    try {
      const status = await bridge.resetModelStorage();
      setStorage(status);
      setRequestState(buildRequestState("reset_model_storage", "succeeded", "Model storage reset to default."));
      await refresh();
    } catch (e) {
      const message = getErrorMessage(e, "Failed to reset model storage");
      setError(message);
      addProblem("reset_model_storage", message);
      setRequestState(withRequestStateFallback(getErrorRequestState(e), buildRequestState("reset_model_storage", "failed", message)));
    } finally {
      setBusyStorageAction(null);
    }
  };

  const activeDownloadState = useMemo(() => {
    if (!busyDownloadName || requestState?.operation !== "download_model") return null;
    return requestState;
  }, [busyDownloadName, requestState]);
  const pageTaskState =
    !error && isActiveRequestState(requestState) && requestState?.operation !== "download_model"
      ? requestState
      : null;
  const migrationTaskState =
    busyStorageAction === "migrate" && isActiveRequestState(requestState)
      ? requestState
      : null;

  const renderWithDialog = (content: JSX.Element) => (
    <>
      {content}
      <ConfirmDialog
        open={modelToDelete !== null}
        title="Remove local model?"
        message={modelToDelete ? `Remove ${modelToDelete.display_name} from the local models folder?` : ""}
        onClose={() => setModelToDelete(null)}
        actions={[
          { label: "Cancel", onClick: () => setModelToDelete(null) },
          {
            label: "Remove model",
            onClick: () => {
              const target = modelToDelete;
              setModelToDelete(null);
              if (!target) return;
              void handleDelete(target);
            },
            variant: "danger",
            disabled: modelToDelete !== null && busyDeleteName === modelToDelete.model_name,
          },
        ]}
      />
    </>
  );

  return renderWithDialog(
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="h-full flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-6 lg:px-12 py-8">
        <div className="max-w-4xl mx-auto">
          <header className="shrink-0 pb-4">
            <h1 className="text-lg font-headline font-semibold text-primary">Models</h1>
            <p className="text-sm text-secondary mt-1">Download, relocate, and recover local TTS voice models.</p>
          </header>

          {storage && (
            <section className="mb-4 rounded-xl border border-outline bg-surface-container-low/40 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex items-start gap-2">
                  <HardDrive className="h-4 w-4 text-secondary mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-xs font-semibold uppercase tracking-wider text-secondary">Model storage</p>
                      <span className={cn("text-[10px] px-1.5 py-0.5 rounded border", storage.is_custom ? "text-accent-amber border-accent-amber/30 bg-accent-amber/10" : "text-secondary border-outline")}>{storage.is_custom ? "Custom" : "Default"}</span>
                    </div>
                    <p className="mt-1 text-xs font-mono text-secondary truncate" title={storage.current_base}>{storage.current_base}</p>
                    {!storage.exists && <p className="mt-1 text-[11px] text-amber-400">This folder will be created when needed.</p>}
                  </div>
                </div>
                <div className="shrink-0 flex items-center gap-1.5">
                  <button type="button" onClick={() => void handleOpenStorage()} disabled={!desktopShellAvailable || !storage.exists} className="px-2 py-1 rounded border border-outline text-[11px] font-medium text-secondary hover:text-primary hover:bg-surface-container disabled:opacity-50">
                    <FolderOpen className="h-3.5 w-3.5 inline mr-1" />Open
                  </button>
                  <button type="button" onClick={() => void handleChangeStorage()} disabled={!desktopShellAvailable || busyStorageAction !== null} className="px-2 py-1 rounded border border-outline text-[11px] font-medium text-secondary hover:text-primary hover:bg-surface-container disabled:opacity-50">
                    {busyStorageAction === "migrate" ? <Loader2 className="h-3.5 w-3.5 inline mr-1 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5 inline mr-1" />}Change
                  </button>
                  {storage.is_custom && (
                    <button type="button" onClick={() => void handleResetStorage()} disabled={busyStorageAction !== null} className="px-2 py-1 rounded border border-outline text-[11px] font-medium text-secondary hover:text-primary hover:bg-surface-container disabled:opacity-50">
                      {busyStorageAction === "reset" ? <Loader2 className="h-3.5 w-3.5 inline mr-1 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5 inline mr-1" />}Reset
                    </button>
                  )}
                </div>
              </div>
            </section>
          )}

          {error && <div className="mb-4 p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-red-400 text-sm">{error}</div>}

          {pageTaskState && (
            <div className="mb-4 p-3 rounded-lg border border-outline text-secondary text-xs space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span>{`${formatProgress(pageTaskState.progress_percent)} · ${pageTaskState.message}`}</span>
              </div>
              <ProgressBar value={pageTaskState.progress_percent} />
            </div>
          )}
          {!error && requestState?.phase === "cancelled" && <div className="mb-4 p-3 rounded-lg border border-outline text-secondary text-xs">{requestState.message}</div>}

          {loading ? (
            <div className="flex items-center justify-center py-16 text-secondary"><Loader2 className="h-5 w-5 animate-spin" /></div>
          ) : (
            <div className="space-y-6">
              <div>
                <h2 className="text-[11px] font-semibold text-secondary uppercase tracking-wider mb-2 px-1">Voice generation</h2>
                <div className="rounded-xl border border-outline overflow-hidden divide-y divide-outline-variant bg-surface-container-low/30">
                  {models.map((m) => {
                    const isDownloading = busyDownloadName === m.model_name || m.downloading;
                    const isBusy = busyDownloadName !== null || busyDeleteName !== null || busyStorageAction !== null;
                    const rowState = busyDownloadName === m.model_name ? activeDownloadState : null;
                    return (
                      <div key={m.model_name} className="flex items-center gap-3 px-3 py-2.5 hover:bg-surface-container-high/40 transition-colors group">
                        <div className="shrink-0">
                          {isDownloading ? <Loader2 className="h-4 w-4 animate-spin text-secondary" /> : m.downloaded ? <CircleCheck className={cn("h-4 w-4", m.loaded ? "text-accent-amber" : "text-emerald-500/90")} /> : <Download className="h-4 w-4 text-secondary/50" />}
                        </div>

                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-primary">{m.display_name}</p>
                          {m.hf_repo_id && <a href={`https://huggingface.co/${m.hf_repo_id}`} target="_blank" rel="noopener noreferrer" className="text-[10px] text-secondary hover:text-accent-amber inline-flex items-center gap-0.5 truncate max-w-full"><span className="truncate">{m.hf_repo_id}</span><ExternalLink className="h-2.5 w-2.5 shrink-0" /></a>}
                          {rowState && (
                            <div className="mt-1.5 space-y-1">
                              <ProgressBar value={rowState.progress_percent} />
                              <p className="text-[10px] text-secondary truncate">{formatProgress(rowState.progress_percent)} · {rowState.message}</p>
                            </div>
                          )}
                        </div>

                        <div className="shrink-0 flex items-center gap-2">
                          {m.loaded && <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-accent-amber/15 text-accent-amber border border-accent-amber/25">Loaded</span>}
                          {m.downloaded && !isDownloading && <span className="text-xs text-secondary tabular-nums">{formatSizeMb(m.size_mb)}</span>}
                          {isDownloading && busyDownloadName === m.model_name && requestState?.phase === "running" && <button type="button" onClick={() => void handleCancelDownload()} className="px-2 py-1 rounded border border-outline text-[11px] font-medium hover:bg-surface-container">Cancel</button>}
                          {!m.downloaded && !isDownloading && <button type="button" onClick={() => void handleDownload(m)} disabled={isBusy} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-surface-container-high text-primary border border-outline hover:bg-surface-container-highest disabled:opacity-50"><Download className="h-3.5 w-3.5" />Download</button>}
                          {m.downloaded && !isDownloading && <button type="button" title="Delete local files" onClick={() => setModelToDelete(m)} disabled={isBusy} className="p-1.5 rounded-md border border-outline text-secondary hover:text-primary hover:bg-surface-container-high disabled:opacity-50"><Trash2 className="h-3.5 w-3.5" /></button>}
                        </div>

                        <ChevronRight className="h-4 w-4 text-secondary/30 group-hover:text-secondary/60 shrink-0" />
                      </div>
                    );
                  })}
                </div>
              </div>

              {problems.length > 0 && (
                <div className="rounded-xl border border-outline overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 bg-surface-container-low/60 text-xs text-secondary">
                    <button type="button" onClick={() => setProblemsOpen((v) => !v)} className="inline-flex items-center gap-2 hover:text-primary">
                      {problemsOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                      Problems
                      <span className="rounded-full bg-red-500/15 text-red-300 px-1.5 py-0.5">{problems.length}</span>
                    </button>
                    <button type="button" onClick={() => setProblems([])} className="inline-flex items-center gap-1 hover:text-primary"><RotateCcw className="h-3.5 w-3.5" />Clear</button>
                  </div>
                  {problemsOpen && <div className="bg-[#1e1e1e] text-[#d4d4d4] p-3 max-h-48 overflow-auto font-mono text-xs leading-relaxed space-y-2">{problems.map((problem) => <div key={problem.id}><span className="text-[#f44747]">[error]</span> <span className="text-[#569cd6]">{problem.operation}</span>{problem.target ? <span className="text-[#9cdcfe]"> {problem.target}</span> : null}: <span className="text-[#ce9178] whitespace-pre-wrap break-all">{problem.message}</span><div className="text-[#6a9955] mt-0.5">{new Date(problem.createdAt).toLocaleString()}</div>{problem.operation === "download_model" && problem.target && <button type="button" className="mt-1 inline-flex items-center gap-1 text-[#dcdcaa] hover:underline" onClick={() => { const target = models.find((m) => m.model_name === problem.target); if (target) void handleDownload(target); }}><Download className="h-3 w-3" />Retry</button>}</div>)}</div>}
                </div>
              )}

              <p className="text-[11px] text-outline px-1 leading-relaxed">
                Downloads are stored under the model storage folder above. Change storage to move existing Aodcast local model folders; reset returns to the default HuggingFace/application cache base.
              </p>
            </div>
          )}
        </div>
      </div>

      {migrationTaskState && (
        <div className="fixed inset-0 z-50 bg-surface/90 backdrop-blur-sm flex items-center justify-center">
          <div className="w-full max-w-md px-8 space-y-5 text-center">
            <Loader2 className="h-8 w-8 animate-spin mx-auto text-secondary" />
            <div>
              <h2 className="text-lg font-headline font-semibold text-primary">Migrating model storage</h2>
              <p className="text-sm text-secondary mt-1">Keep Aodcast open while model files are moved.</p>
            </div>
            <div className="space-y-2 text-left">
              <ProgressBar value={migrationTaskState.progress_percent} />
              <p className="text-xs text-secondary truncate">{formatProgress(migrationTaskState.progress_percent)} · {migrationTaskState.message}</p>
            </div>
          </div>
        </div>
      )}
    </motion.div>,
  );
}
