import { ChangeEvent, useRef, useState } from "react";
import { AlertTriangle, FileText, Loader2, MessageSquare, RefreshCw, Sparkles, Upload, X } from "lucide-react";
import { useBridge } from "../../lib/BridgeContext";
import { SafeMarkdown } from "../../components/SafeMarkdown";
import { getErrorMessage } from "../../lib/requestState";
import type { SessionProject } from "../../types";
import { cn } from "../../lib/utils";

export function SourceDrawer({
  project,
  isOpen,
  onClose,
  onDiscuss,
  onUpdated,
  onGenerateScript,
}: {
  project: SessionProject;
  isOpen: boolean;
  onClose: () => void;
  onDiscuss: () => void;
  onUpdated: () => Promise<void>;
  onGenerateScript: () => Promise<void>;
}) {
  const bridge = useBridge();
  const inputRef = useRef<HTMLInputElement>(null);
  const [replacing, setReplacing] = useState(false);
  const [generatingScript, setGeneratingScript] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const source = project.source;
  if (!isOpen || !source) return null;

  const generatedSource = project.script?.generation_metadata?.source;
  const stale = Boolean(
    generatedSource &&
      (generatedSource.version !== source.version || generatedSource.content_hash !== source.content_hash),
  );
  const hasAudio = Boolean(project.artifact?.audio_path);

  const handleReplace = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".md")) {
      setError("Choose a Markdown (.md) file.");
      return;
    }
    setReplacing(true);
    setError(null);
    try {
      const rawMarkdown = await file.text();
      await bridge.updateEpisodeSource(project.session.session_id, {
        rawMarkdown,
        name: file.name,
        importKind: "file",
        conversionMode: source.conversion_mode,
        targetLength: source.target_length,
        focusInstructions: source.focus_instructions,
      });
      await onUpdated();
    } catch (reason) {
      setError(getErrorMessage(reason, "Could not replace the Markdown source."));
    } finally {
      setReplacing(false);
    }
  };

  const handleGenerateScript = async () => {
    setGeneratingScript(true);
    setError(null);
    try {
      await onGenerateScript();
    } catch (reason) {
      setError(getErrorMessage(reason, "Could not generate a new script from this source."));
    } finally {
      setGeneratingScript(false);
    }
  };

  return (
    <>
      <div className="transcript-overlay-backdrop transcript-overlay-backdrop-visible" onClick={onClose} aria-hidden="true" />
      <aside className={cn("transcript-overlay", "transcript-overlay-open")} aria-label="Imported Markdown source">
        <div className="flex shrink-0 items-center justify-between border-b border-outline px-4 py-3">
          <div className="flex min-w-0 items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-secondary/70">
            <FileText className="h-3.5 w-3.5 shrink-0" />
            <span>Imported source</span>
            <span className="rounded-full bg-surface-container-high/60 px-1.5 py-0.5 text-[9px] font-medium text-secondary">v{source.version}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-surface-container-high/60 hover:text-primary"
            aria-label="Close source"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="shrink-0 border-b border-outline px-4 py-3">
          <h2 className="truncate text-sm font-semibold text-primary" title={source.title}>{source.title}</h2>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-secondary">
            <span>{source.name}</span>
            <span>{source.word_count.toLocaleString()} readable units</span>
            <span>≈ {source.estimated_audio_minutes.toFixed(1)} min source</span>
            <span>{source.conversion_mode === "adapt" ? "Podcast adaptation" : "Faithful narration"}</span>
          </div>
        </div>

        {stale ? (
          <div className="flex shrink-0 items-start gap-2 border-b border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs leading-5 text-amber-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              The source changed after this script was generated. The existing script{hasAudio ? " and audio were" : " was"} kept; generate a new script snapshot when ready.
            </span>
          </div>
        ) : null}

        {source.warnings.length > 0 ? (
          <div className="shrink-0 border-b border-outline bg-surface-container-low/50 px-4 py-2.5">
            {source.warnings.map((warning) => (
              <p key={warning} className="flex items-start gap-2 text-[11px] leading-5 text-secondary">
                <AlertTriangle className="mt-1 h-3 w-3 shrink-0 text-accent-amber" />
                {warning}
              </p>
            ))}
          </div>
        ) : null}

        <div className="flex-1 overflow-y-auto px-5 py-4 mac-scrollbar">
          <div className="prose prose-sm prose-theme max-w-none text-[13px] leading-6 [&_h1]:text-xl [&_h2]:text-base [&_p]:my-3">
            <SafeMarkdown>{source.raw_markdown}</SafeMarkdown>
          </div>
        </div>

        {error ? <div role="alert" className="shrink-0 border-t border-red-500/20 bg-red-500/10 px-4 py-2.5 text-xs text-red-300">{error}</div> : null}
        <div className="grid shrink-0 grid-cols-2 gap-2 border-t border-outline bg-surface-container-low/90 p-3">
          {stale ? (
            <button
              type="button"
              disabled={generatingScript || replacing}
              onClick={() => void handleGenerateScript()}
              className="col-span-2 flex h-11 items-center justify-center gap-2 rounded-xl theme-accent-gradient px-4 text-xs font-semibold text-on-primary transition-opacity disabled:opacity-50"
            >
              {generatingScript ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              {generatingScript ? "Generating new script…" : "Generate new script from v" + source.version}
            </button>
          ) : null}
          <input ref={inputRef} type="file" accept=".md,text/markdown" onChange={handleReplace} className="hidden" />
          <button
            type="button"
            disabled={replacing}
            onClick={() => inputRef.current?.click()}
            className="flex h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container text-xs font-semibold text-primary transition-colors hover:bg-surface-container-high disabled:opacity-50"
          >
            {replacing ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            Replace source
          </button>
          <button
            type="button"
            onClick={onDiscuss}
            className="flex h-11 items-center justify-center gap-2 rounded-xl border border-accent-amber/25 bg-accent-amber/8 text-xs font-semibold text-accent-amber transition-colors hover:bg-accent-amber/12"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Discuss source
          </button>
        </div>
      </aside>
    </>
  );
}
