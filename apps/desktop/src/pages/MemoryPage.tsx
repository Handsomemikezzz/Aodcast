import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, Loader2, Lock, Trash2, Wand2 } from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { OverflowMenu } from "../components/OverflowMenu";
import { cn } from "../lib/utils";
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
    <div className="flex items-center gap-1.5 shrink-0 text-[11px] text-secondary">
      <span className="capitalize">{entry.type}</span>
      {entry.origin === "explicit" ? <span>· Saved on request</span> : null}
      {entry.sensitive ? (
        <span className="inline-flex items-center gap-0.5 text-amber-700 dark:text-amber-300">
          · <Lock className="h-3 w-3" /> Sensitive
        </span>
      ) : null}
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
    <li className="group">
      <div className="flex items-start gap-2 px-4 py-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="min-w-0 flex-1 text-left"
        >
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium text-[14px] text-primary truncate">{entry.name}</p>
            <TypeBadge entry={entry} />
          </div>
          <p className="mt-0.5 text-[12px] text-secondary leading-relaxed">{entry.description}</p>
        </button>
        <button
          type="button"
          aria-label={`Delete memory ${entry.name}`}
          title="Delete"
          onClick={() => onDelete(entry)}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-secondary opacity-0 transition hover:bg-red-500/10 hover:text-red-600 focus-visible:opacity-100 group-hover:opacity-100 dark:hover:text-red-300"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      {expanded && (
        <div className="space-y-3 px-4 pb-4">
          {entry.sensitive ? (
            <p className="text-[12px] text-amber-700 dark:text-amber-300">Sensitive — the full text is only shown on this device.</p>
          ) : null}
          {entry.body ? (
            <p className="text-[13px] text-primary leading-relaxed whitespace-pre-wrap">{entry.body}</p>
          ) : null}
          {entry.keywords && entry.keywords.length > 0 ? (
            <p className="text-[12px] text-secondary">{entry.keywords.join(" · ")}</p>
          ) : null}
          {entry.evidence && entry.evidence.length > 0 ? (
            <div className="space-y-1.5">
              <p className="text-[12px] font-medium text-secondary">From your words ({entry.source_count})</p>
              {entry.evidence.map((ev, i) => (
                <blockquote
                  key={`${ev.turn_id}-${i}`}
                  className="border-l-2 border-outline pl-2.5 text-[12px] text-secondary"
                >
                  “{ev.quote}”
                </blockquote>
              ))}
            </div>
          ) : null}
          <p className="text-[11px] text-secondary">
            Used {entry.use_count} time{entry.use_count === 1 ? "" : "s"}
            {entry.last_used_at ? ` · last ${new Date(entry.last_used_at).toLocaleDateString()}` : ""}
          </p>
        </div>
      )}
    </li>
  );
}

export function MemoryPage() {
  const bridge = useBridge();
  const [overview, setOverview] = useState<MemoryOverview | null>(null);
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [usage, setUsage] = useState<MemoryUsageEvent[]>([]);
  const [superseded, setSuperseded] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<MemoryType | "all">("all");
  const [deleteTarget, setDeleteTarget] = useState<MemoryEntry | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [busy, setBusy] = useState(false);
  const [maintaining, setMaintaining] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [ov, items, events, sup] = await Promise.all([
        bridge.getMemoryOverview(),
        bridge.listMemories({
          search: search.trim() || undefined,
          type: typeFilter === "all" ? undefined : typeFilter,
        }),
        bridge.listMemoryUsage(),
        bridge.listMemorySuperseded(),
      ]);
      setOverview(ov);
      setEntries(items);
      setUsage(events);
      setSuperseded(sup);
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

  const handleMaintain = async () => {
    setMaintaining(true);
    setError(null);
    try {
      await bridge.runMemoryMaintenance();
      // Maintenance runs in the background; reflect the queued/running state.
      await load();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to start maintenance."));
    } finally {
      setMaintaining(false);
    }
  };

  const workerLabel = useMemo(() => {
    if (!worker) return "";
    if (worker.status === "error") return worker.last_error || "Background update failed";
    if (worker.status === "running") return "Updating…";
    return "Up to date";
  }, [worker]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        <Loader2 className="w-4 h-4 animate-spin mr-2" />
        Loading memory…
      </div>
    );
  }

  const toggleRowClass = "flex items-center justify-between gap-3 py-3";
  return (
    <>
      <div className="flex flex-col h-full w-full overflow-y-auto px-6 lg:px-10 py-8 mac-scrollbar">
        <div className="max-w-3xl mx-auto w-full">
          <div className="mb-1 flex items-center justify-between gap-4">
            <h1 className="text-2xl font-headline font-semibold text-primary">Memory</h1>
            {entries.length > 0 ? (
              <OverflowMenu
                label="More memory actions"
                items={[{ label: "Clear all memory", icon: Trash2, danger: true, onSelect: () => setConfirmClear(true) }]}
              />
            ) : null}
          </div>
          <p className="mb-6 text-sm text-secondary">
            Reusable facts from your own words, kept on this device so interviews and scripts stay consistent.
          </p>

          {error ? (
            <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          ) : null}

          {needsFirstRun ? (
            <div className="mb-6 rounded-xl border border-outline p-5">
              <p className="font-semibold text-primary">Turn on long-term memory?</p>
              <ul className="mt-2 mb-4 list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-secondary">
                <li>Memory is stored only on this machine.</li>
                <li>Aodcast saves information you share that is reusable across episodes.</li>
                <li>You can view, delete, or clear it at any time, and turn it off globally or per episode.</li>
                <li>Secrets like passwords, API keys, and payment details are never saved.</li>
              </ul>
              <button
                type="button"
                onClick={() => void handleAcknowledge()}
                disabled={busy}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3.5 text-[13px] font-semibold text-background transition-opacity disabled:opacity-50"
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                Turn on memory
              </button>
            </div>
          ) : (
            <div className="mb-6 divide-y divide-outline border-y border-outline">
              <div className={toggleRowClass}>
                <div>
                  <p className="text-[13px] font-medium text-primary">Learn from new conversations</p>
                  <p className="text-[12px] text-secondary">Save reusable facts from what you say in interviews.</p>
                </div>
                <Toggle
                  checked={Boolean(settings?.writing_enabled)}
                  disabled={busy}
                  onChange={(next) => void handleToggle("writing", next)}
                />
              </div>
              <div className={toggleRowClass}>
                <div>
                  <p className="text-[13px] font-medium text-primary">Use memory</p>
                  <p className="text-[12px] text-secondary">Bring saved facts into interviews and script generation.</p>
                </div>
                <Toggle
                  checked={Boolean(settings?.usage_enabled)}
                  disabled={busy}
                  onChange={(next) => void handleToggle("usage", next)}
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 py-2.5 text-[12px] text-secondary">
                <span className="flex items-center gap-1.5">
                  {worker?.status === "error" ? <AlertTriangle className="w-3.5 h-3.5 text-amber-500" /> : null}
                  {overview?.entry_count ?? 0} memories · {workerLabel}
                  {overview && overview.pending_job_count > 0 ? ` · ${overview.pending_job_count} queued` : ""}
                  {settings?.last_maintenance_at
                    ? ` · Tidied ${new Date(settings.last_maintenance_at).toLocaleString()}`
                    : ""}
                </span>
                <button
                  type="button"
                  onClick={() => void handleMaintain()}
                  disabled={maintaining || busy}
                  title="Merge duplicates and remove stale memories"
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12px] font-medium text-primary transition-colors hover:bg-primary/5 disabled:opacity-50"
                >
                  {maintaining ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                  Tidy up
                </button>
              </div>
            </div>
          )}

          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search memories…"
              aria-label="Search memories"
              className="h-9 w-full rounded-lg border border-outline bg-transparent px-3 text-[13px] text-primary placeholder:text-secondary/60 outline-none focus:border-primary/25 sm:flex-1"
            />
            <div className="inline-flex shrink-0 rounded-lg border border-outline p-0.5" role="group" aria-label="Filter by type">
              {TYPE_TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setTypeFilter(tab.key)}
                  aria-pressed={typeFilter === tab.key}
                  className={cn(
                    "h-7 rounded-md px-2.5 text-[12px] font-medium transition-colors",
                    typeFilter === tab.key ? "bg-primary/[0.07] text-primary" : "text-secondary hover:text-primary",
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {entries.length === 0 ? (
            <div className="rounded-xl border border-dashed border-outline p-8 text-center text-secondary text-sm">
              {search || typeFilter !== "all"
                ? "No memories match this filter."
                : "No memories yet. They form as you talk through episodes."}
            </div>
          ) : (
            <ul className="divide-y divide-outline rounded-xl border border-outline">
              {entries.map((entry) => (
                <MemoryCard key={entry.id} entry={entry} onDelete={setDeleteTarget} />
              ))}
            </ul>
          )}

          {usage.length > 0 || superseded.length > 0 ? (
            <details className="group mt-6">
              <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-[13px] text-secondary outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-accent-amber/50 [&::-webkit-details-marker]:hidden">
                History
                <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
              </summary>
              {usage.length > 0 ? (
                <>
                  <p className="mt-3 mb-1.5 text-[12px] font-medium text-secondary">Recently used</p>
                  <ul className="divide-y divide-outline rounded-xl border border-outline">
                    {usage.slice(0, 10).map((event, i) => (
                      <li key={`${event.session_id}-${i}`} className="flex items-center justify-between gap-3 px-4 py-2 text-[12px]">
                        <span className="text-primary truncate">{event.session_topic || "Untitled"}</span>
                        <span className="text-secondary shrink-0">
                          {event.memory_ids.length} memor{event.memory_ids.length === 1 ? "y" : "ies"} · {event.operation}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {superseded.length > 0 ? (
                <>
                  <p className="mt-4 mb-1.5 text-[12px] font-medium text-secondary">Replaced by newer memories</p>
                  <ul className="divide-y divide-outline rounded-xl border border-outline">
                    {superseded.slice(0, 10).map((entry) => (
                      <li key={entry.id} className="flex items-center justify-between gap-3 px-4 py-2 text-[12px]">
                        <span className="text-secondary truncate">{entry.name}</span>
                        <span className="text-secondary shrink-0 capitalize">{entry.type}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </details>
          ) : null}
        </div>
      </div>

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
