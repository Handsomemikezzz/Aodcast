import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Brain,
  Loader2,
  Lock,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { getErrorMessage } from "../lib/requestState";
import type { MemoryEntry, MemoryOverview, MemoryType, MemoryUsageEvent } from "../types";

const TYPE_TABS: { key: MemoryType | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "profile", label: "Profile" },
  { key: "experience", label: "Experience" },
  { key: "viewpoint", label: "Viewpoint" },
  { key: "preference", label: "Preference" },
];

function Toggle({
  checked,
  disabled,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 cursor-pointer " +
        (checked ? "bg-accent-amber" : "bg-surface-container-high border border-outline")
      }
    >
      <span
        className={
          "inline-block h-3.5 w-3.5 transform rounded-full bg-on-primary transition-transform " +
          (checked ? "translate-x-4" : "translate-x-1")
        }
      />
    </button>
  );
}

function TypeBadge({ entry }: { entry: MemoryEntry }) {
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wide bg-accent-amber/10 border border-accent-amber/20 text-accent-amber">
        {entry.type}
      </span>
      {entry.origin === "explicit" && (
        <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wide bg-primary/8 border border-outline text-secondary">
          explicit
        </span>
      )}
      {entry.sensitive && (
        <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wide bg-amber-500/10 border border-amber-500/25 text-amber-600 dark:text-amber-400">
          <Lock className="w-2.5 h-2.5" />
          sensitive
        </span>
      )}
    </div>
  );
}

function MemoryCard({
  entry,
  onDelete,
}: {
  entry: MemoryEntry;
  onDelete: (entry: MemoryEntry) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-xl border border-outline bg-surface-container-low overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="min-w-0 flex-1 text-left"
        >
          <div className="flex items-center justify-between gap-2 mb-1">
            <p className="font-medium text-[14px] text-primary truncate">{entry.name}</p>
            <TypeBadge entry={entry} />
          </div>
          <p className="text-[12px] text-secondary leading-relaxed">{entry.description}</p>
        </button>
        <button
          type="button"
          aria-label={`Delete memory ${entry.name}`}
          onClick={() => onDelete(entry)}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-red-500/10 hover:text-red-400"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      {expanded && (
        <div className="border-t border-outline bg-surface/40 px-4 py-3 space-y-3">
          {entry.sensitive ? (
            <p className="text-[12px] text-amber-600 dark:text-amber-400">
              Sensitive memory — body shown locally only.
            </p>
          ) : null}
          {entry.body ? (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-secondary/70 mb-1">Memory</p>
              <p className="text-[13px] text-primary leading-relaxed whitespace-pre-wrap">{entry.body}</p>
            </div>
          ) : null}
          {entry.keywords && entry.keywords.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {entry.keywords.map((kw) => (
                <span key={kw} className="px-2 py-0.5 rounded-md text-[10px] bg-primary/5 border border-outline text-secondary">
                  {kw}
                </span>
              ))}
            </div>
          ) : null}
          {entry.evidence && entry.evidence.length > 0 ? (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-secondary/70 mb-1">
                Evidence ({entry.source_count})
              </p>
              <div className="space-y-1.5">
                {entry.evidence.map((ev, i) => (
                  <blockquote
                    key={`${ev.turn_id}-${i}`}
                    className="border-l-2 border-accent-amber/30 pl-2.5 text-[12px] text-secondary italic"
                  >
                    "{ev.quote}"
                  </blockquote>
                ))}
              </div>
            </div>
          ) : null}
          <p className="text-[10px] text-secondary/60">
            Used {entry.use_count} time{entry.use_count === 1 ? "" : "s"}
            {entry.last_used_at ? ` · last ${new Date(entry.last_used_at).toLocaleDateString()}` : ""}
          </p>
        </div>
      )}
    </div>
  );
}

export function MemoryPage() {
  const bridge = useBridge();
  const [overview, setOverview] = useState<MemoryOverview | null>(null);
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [usage, setUsage] = useState<MemoryUsageEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<MemoryType | "all">("all");
  const [deleteTarget, setDeleteTarget] = useState<MemoryEntry | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [ov, items, events] = await Promise.all([
        bridge.getMemoryOverview(),
        bridge.listMemories({
          search: search.trim() || undefined,
          type: typeFilter === "all" ? undefined : typeFilter,
        }),
        bridge.listMemoryUsage(),
      ]);
      setOverview(ov);
      setEntries(items);
      setUsage(events);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load memory."));
    } finally {
      setLoading(false);
    }
  }, [bridge, search, typeFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const settings = overview?.settings;
  const worker = overview?.worker;
  const needsFirstRun = settings ? !settings.first_run_acknowledged : false;

  const handleAcknowledge = async () => {
    setBusy(true);
    try {
      const ov = await bridge.acknowledgeMemory();
      setOverview(ov);
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to enable memory."));
    } finally {
      setBusy(false);
    }
  };

  const handleToggle = async (field: "writing" | "usage", next: boolean) => {
    setBusy(true);
    try {
      const ov = await bridge.updateMemorySettings(
        field === "writing" ? { writingEnabled: next } : { usageEnabled: next },
      );
      setOverview(ov);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to update settings."));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (entry: MemoryEntry) => {
    try {
      await bridge.deleteMemory(entry.id);
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to delete memory."));
    }
  };

  const handleClearAll = async () => {
    try {
      await bridge.clearAllMemory();
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to clear memory."));
    }
  };

  const workerLabel = useMemo(() => {
    if (!worker) return "";
    if (worker.status === "error") return worker.last_error || "Background update failed";
    if (worker.status === "running") return "Updating…";
    return "Idle";
  }, [worker]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        <Loader2 className="w-4 h-4 animate-spin mr-2" />
        Loading memory…
      </div>
    );
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col h-full w-full overflow-y-auto px-6 lg:px-12 py-8 mac-scrollbar"
      >
        <div className="max-w-2xl mx-auto w-full">
          <div className="mb-6 border-b border-outline pb-6">
            <div className="flex items-center gap-2.5 mb-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-amber/10 border border-accent-amber/20">
                <Brain className="w-4 h-4 text-accent-amber" />
              </div>
              <h1 className="text-2xl font-headline font-bold text-primary">Memory</h1>
            </div>
            <p className="text-secondary text-sm">
              Reusable knowledge from your own words, saved locally to keep interviews and scripts consistent across episodes.
            </p>
          </div>

          {error ? (
            <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          ) : null}

          {needsFirstRun ? (
            <div className="mb-6 rounded-xl border border-accent-amber/25 bg-accent-amber/8 p-5">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="w-4 h-4 text-accent-amber" />
                <p className="font-semibold text-primary">Enable long-term memory</p>
              </div>
              <ul className="text-[13px] text-secondary leading-relaxed space-y-1 mb-4 list-disc pl-5">
                <li>Memory is stored only on this machine.</li>
                <li>Aodcast automatically saves information that is reusable across episodes.</li>
                <li>You can view, delete, or clear it at any time, and turn it off globally or per episode.</li>
                <li>Secrets like passwords, API keys, and payment details are never saved.</li>
              </ul>
              <button
                type="button"
                onClick={() => void handleAcknowledge()}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-xl bg-accent-amber px-4 py-2 text-sm font-bold text-on-primary hover:bg-accent-amber/90 transition-colors disabled:opacity-50 cursor-pointer"
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                Enable memory
              </button>
            </div>
          ) : (
            <div className="mb-6 rounded-xl border border-outline bg-surface-container-low p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[13px] font-medium text-primary">Automatically record memory</p>
                  <p className="text-[11px] text-secondary/70">Extract reusable knowledge from new conversations.</p>
                </div>
                <Toggle
                  checked={Boolean(settings?.writing_enabled)}
                  disabled={busy}
                  onChange={(next) => void handleToggle("writing", next)}
                />
              </div>
              <div className="flex items-center justify-between gap-3 border-t border-outline pt-3">
                <div>
                  <p className="text-[13px] font-medium text-primary">Use memory</p>
                  <p className="text-[11px] text-secondary/70">Apply memory during interviews and script generation.</p>
                </div>
                <Toggle
                  checked={Boolean(settings?.usage_enabled)}
                  disabled={busy}
                  onChange={(next) => void handleToggle("usage", next)}
                />
              </div>
              <div className="flex items-center justify-between gap-3 border-t border-outline pt-3 text-[11px] text-secondary/70">
                <span className="flex items-center gap-1.5">
                  {worker?.status === "error" ? (
                    <AlertTriangle className="w-3 h-3 text-amber-500" />
                  ) : null}
                  Background: {workerLabel}
                  {overview && overview.pending_job_count > 0 ? ` · ${overview.pending_job_count} queued` : ""}
                </span>
                <span>{overview?.entry_count ?? 0} memories</span>
              </div>
            </div>
          )}

          {/* Search + type filter */}
          <div className="flex flex-col gap-3 mb-4">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search memories…"
              className="w-full rounded-lg border border-outline bg-surface-container-low px-3 py-2 text-[13px] text-primary placeholder:text-outline outline-none focus:border-accent-amber/30"
            />
            <div className="flex flex-wrap gap-1.5">
              {TYPE_TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setTypeFilter(tab.key)}
                  className={
                    "px-3 py-1 rounded-lg text-[12px] font-medium transition-colors cursor-pointer border " +
                    (typeFilter === tab.key
                      ? "bg-accent-amber/10 border-accent-amber/25 text-accent-amber"
                      : "border-transparent text-secondary hover:bg-primary/5 hover:text-primary")
                  }
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Entries */}
          <div className="space-y-2.5">
            {entries.length === 0 ? (
              <div className="rounded-xl border border-dashed border-outline bg-surface/30 p-8 text-center text-secondary text-sm">
                {search || typeFilter !== "all"
                  ? "No memories match this filter."
                  : "No memories yet. They form automatically as you talk through episodes."}
              </div>
            ) : (
              entries.map((entry) => (
                <MemoryCard key={entry.id} entry={entry} onDelete={setDeleteTarget} />
              ))
            )}
          </div>

          {/* Recently used */}
          {usage.length > 0 ? (
            <div className="mt-8">
              <p className="text-[10px] font-bold uppercase tracking-wide text-secondary/70 mb-2">Recently used</p>
              <div className="rounded-xl border border-outline bg-surface-container-low divide-y divide-outline-variant overflow-hidden">
                {usage.slice(0, 10).map((event, i) => (
                  <div key={`${event.session_id}-${i}`} className="flex items-center justify-between gap-3 px-4 py-2.5 text-[12px]">
                    <span className="text-primary truncate">{event.session_topic || "Untitled"}</span>
                    <span className="text-secondary/60 shrink-0">
                      {event.memory_ids.length} memor{event.memory_ids.length === 1 ? "y" : "ies"} · {event.operation}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* Clear all */}
          {entries.length > 0 ? (
            <div className="mt-8 border-t border-outline pt-5">
              <button
                type="button"
                onClick={() => setConfirmClear(true)}
                className="inline-flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/8 px-3 py-2 text-[13px] font-medium text-red-400 hover:bg-red-500/15 transition-colors cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Clear all memory
              </button>
            </div>
          ) : null}
        </div>
      </motion.div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete this memory?"
        message={
          deleteTarget
            ? `"${deleteTarget.name}" will be permanently removed. The same evidence won't recreate it.`
            : ""
        }
        onClose={() => setDeleteTarget(null)}
        actions={[
          { label: "Cancel", onClick: () => setDeleteTarget(null) },
          {
            label: "Delete",
            onClick: () => {
              const target = deleteTarget;
              setDeleteTarget(null);
              if (target) void handleDelete(target);
            },
            variant: "danger",
          },
        ]}
      />
      <ConfirmDialog
        open={confirmClear}
        title="Clear all memory?"
        message="Every memory, its evidence, and recent-use history will be permanently deleted. This cannot be undone."
        onClose={() => setConfirmClear(false)}
        actions={[
          { label: "Cancel", onClick: () => setConfirmClear(false) },
          {
            label: "Clear everything",
            onClick: () => {
              setConfirmClear(false);
              void handleClearAll();
            },
            variant: "danger",
          },
        ]}
      />
    </>
  );
}
