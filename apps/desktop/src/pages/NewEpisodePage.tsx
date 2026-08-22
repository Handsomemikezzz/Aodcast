import { ChangeEvent, DragEvent, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  FileText,
  Loader2,
  MessageSquare,
  Sparkles,
  Upload,
  Volume2,
} from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
import { SafeMarkdown } from "../components/SafeMarkdown";
import type { EpisodeSourceInput } from "../lib/desktopBridge";
import { cn } from "../lib/utils";

type ConversionMode = EpisodeSourceInput["conversionMode"];
type TargetLength = EpisodeSourceInput["targetLength"];

function inferMarkdownTitle(markdown: string, name: string): string {
  const frontMatter = markdown.match(/^---\s*\n[\s\S]*?^title:\s*["']?(.+?)["']?\s*$[\s\S]*?^---\s*$/m);
  if (frontMatter?.[1]?.trim()) return frontMatter[1].trim();
  const heading = markdown.match(/^#\s+(.+)$/m);
  if (heading?.[1]?.trim()) return heading[1].trim();
  return name.replace(/\.md$/i, "").trim() || "Untitled Episode";
}

function estimateMinutes(markdown: string): number {
  const cjk = (markdown.match(/[\u3400-\u9fff\uf900-\ufaff]/g) ?? []).length;
  const latin = (markdown.match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g) ?? []).length;
  return Math.max(0.1, cjk / 300 + latin / 160);
}

function ChoiceCard({
  icon: Icon,
  title,
  description,
  action,
  onClick,
  accent = false,
}: {
  icon: typeof MessageSquare;
  title: string;
  description: string;
  action: string;
  onClick: () => void;
  accent?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group min-h-[220px] rounded-2xl border p-6 text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/60",
        accent
          ? "border-accent-amber/30 bg-accent-amber/8 hover:bg-accent-amber/12"
          : "border-outline bg-surface-container-low hover:border-outline-variant hover:bg-surface-container",
      )}
    >
      <span className={cn(
        "mb-8 flex h-11 w-11 items-center justify-center rounded-xl border",
        accent
          ? "border-accent-amber/25 bg-accent-amber/10 text-accent-amber"
          : "border-outline bg-surface-container-high text-primary",
      )}>
        <Icon className="h-5 w-5" />
      </span>
      <span className="block text-lg font-semibold text-primary">{title}</span>
      <span className="mt-2 block max-w-sm text-sm leading-6 text-secondary">{description}</span>
      <span className={cn(
        "mt-7 inline-flex items-center gap-2 text-sm font-semibold",
        accent ? "text-accent-amber" : "text-primary",
      )}>
        {action}
        <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
      </span>
    </button>
  );
}

export function NewEpisodePage({
  mode,
  onRefresh,
}: {
  mode: "choose" | "markdown";
  onRefresh: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const bridge = useBridge();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [rawMarkdown, setRawMarkdown] = useState("");
  const [sourceName, setSourceName] = useState("Pasted Markdown");
  const [importKind, setImportKind] = useState<"file" | "paste">("paste");
  const [conversionMode, setConversionMode] = useState<ConversionMode>("adapt");
  const [targetLength, setTargetLength] = useState<TargetLength>("auto");
  const [focusInstructions, setFocusInstructions] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [submitting, setSubmitting] = useState<"generate" | "discuss" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedSessionId, setSavedSessionId] = useState("");

  const title = useMemo(() => inferMarkdownTitle(rawMarkdown, sourceName), [rawMarkdown, sourceName]);
  const minutes = useMemo(() => estimateMinutes(rawMarkdown), [rawMarkdown]);
  const readableCharacters = rawMarkdown.trim().length;
  const canContinue = readableCharacters >= 20 && readableCharacters <= 300_000;

  const loadFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".md") && file.type !== "text/markdown" && file.type !== "text/plain") {
      setError("Choose a Markdown (.md) file.");
      return;
    }
    if (file.size > 1_200_000) {
      setError("This file is too large. Markdown sources are limited to 300,000 characters.");
      return;
    }
    try {
      const text = await file.text();
      setRawMarkdown(text);
      setSourceName(file.name);
      setImportKind("file");
      setError(null);
    } catch {
      setError("Aodcast could not read this file. Try pasting the Markdown instead.");
    }
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void loadFile(file);
    event.target.value = "";
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void loadFile(file);
  };

  const createSourceInput = (): EpisodeSourceInput => ({
    rawMarkdown,
    name: sourceName,
    importKind,
    conversionMode,
    targetLength,
    focusInstructions,
  });

  const createEpisode = async (next: "generate" | "discuss") => {
    if (!canContinue || submitting) return;
    setSubmitting(next);
    setError(null);
    setSavedSessionId("");
    try {
      const created = await bridge.createSession({
        topic: title,
        creationIntent: "Turn an imported Markdown article into a solo podcast.",
        source: createSourceInput(),
      });
      const sessionId = created.session.session_id;
      setSavedSessionId(sessionId);
      await onRefresh();

      if (next === "discuss") {
        navigate(`/studio/${sessionId}?panel=conversation`);
        return;
      }

      const preflight = await bridge.checkLLMConfig();
      if (!preflight.ready) {
        throw new Error(preflight.message || "Set up a language model before generating the script.");
      }
      const result = await bridge.generateScript(sessionId);
      const scriptId = result.script_id ?? result.project.script?.script_id;
      await onRefresh();
      navigate(scriptId ? `/studio/${sessionId}/${scriptId}` : `/studio/${sessionId}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create this episode.");
    } finally {
      setSubmitting(null);
    }
  };

  if (mode === "choose") {
    return (
      <div className="h-full overflow-y-auto px-6 py-10 lg:px-12">
        <div className="mx-auto w-full max-w-4xl">
          <button
            type="button"
            onClick={() => navigate("/episodes")}
            className="mb-8 inline-flex h-11 items-center gap-2 rounded-xl px-3 text-sm text-secondary transition-colors hover:bg-surface-container hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" />
            Episodes
          </button>
          <div className="mb-8">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-accent-amber">New episode</p>
            <h1 className="text-3xl font-bold text-primary">How would you like to begin?</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-secondary">
              Start with a conversation, or turn something you have already written into a spoken episode.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <ChoiceCard
              icon={MessageSquare}
              title="Start from an idea"
              description="Talk with AI to shape your angle, examples, and takeaway before creating a draft."
              action="Talk through the idea"
              onClick={() => navigate("/chat")}
            />
            <ChoiceCard
              icon={FileText}
              title="Start from content"
              description="Import an article, note, or Markdown file and turn it into a natural spoken draft."
              action="Import content"
              onClick={() => navigate("/episodes/new/markdown")}
              accent
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between border-b border-outline px-5 py-3">
        <button
          type="button"
          onClick={() => navigate("/episodes/new")}
          className="inline-flex h-11 items-center gap-2 rounded-xl px-3 text-sm text-secondary transition-colors hover:bg-surface-container hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
          Choose another start
        </button>
        <div className="hidden items-center gap-2 text-xs text-secondary sm:flex">
          <FileText className="h-4 w-4 text-accent-amber" />
          Source is saved locally; generation uses your configured LLM provider
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-6 lg:px-8">
        <div className="mx-auto grid w-full max-w-6xl gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
          <section className="min-w-0 space-y-4">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-accent-amber">Source</p>
              <h1 className="text-2xl font-bold text-primary">Import a Markdown article</h1>
              <p className="mt-2 text-sm leading-6 text-secondary">
                Drop in a file or paste Markdown below. The original is preserved as the episode source.
              </p>
            </div>

            <div
              onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              className={cn(
                "rounded-2xl border bg-surface-container-low p-3 transition-colors",
                dragActive ? "border-accent-amber bg-accent-amber/8" : "border-outline",
              )}
            >
              <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-outline pb-3">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="inline-flex h-11 items-center gap-2 rounded-xl border border-outline bg-surface-container px-4 text-sm font-medium text-primary transition-colors hover:bg-surface-container-high"
                >
                  <Upload className="h-4 w-4" />
                  Choose .md file
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".md,text/markdown,text/plain"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <p className="min-w-0 flex-1 truncate text-xs text-secondary" title={sourceName}>
                  {importKind === "file" ? sourceName : "Or paste Markdown directly"}
                </p>
                <span className="text-xs tabular-nums text-secondary">
                  {readableCharacters.toLocaleString()} / 300,000
                </span>
              </div>
              <label htmlFor="markdown-source" className="sr-only">Markdown source</label>
              <textarea
                id="markdown-source"
                value={rawMarkdown}
                onChange={(event) => {
                  setRawMarkdown(event.target.value);
                  if (importKind !== "paste") {
                    setImportKind("paste");
                    setSourceName("Pasted Markdown");
                  }
                  setError(null);
                }}
                placeholder="# Your article title\n\nPaste the Markdown you want to turn into a podcast…"
                className="min-h-[360px] w-full resize-y rounded-xl border border-transparent bg-background/45 px-4 py-4 font-mono text-[13px] leading-6 text-primary outline-none transition-colors placeholder:text-secondary/60 focus:border-accent-amber/35"
              />
            </div>

            {error ? (
              <div role="alert" className="rounded-xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                <p>{error}</p>
                {savedSessionId ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => navigate(`/studio/${savedSessionId}`)}
                      className="rounded-lg border border-red-300/25 px-3 py-1.5 text-xs font-semibold text-red-200 hover:bg-red-500/10"
                    >
                      Open saved source
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate("/settings")}
                      className="rounded-lg border border-outline px-3 py-1.5 text-xs font-semibold text-primary hover:bg-surface-container"
                    >
                      Open Settings
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>

          <aside className="min-w-0 space-y-4">
            <section className="rounded-2xl border border-outline bg-surface-container-low p-4">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">Preview</p>
                  <h2 className="mt-1 truncate text-base font-semibold text-primary" title={title}>{title}</h2>
                </div>
                <span className="shrink-0 rounded-full border border-outline bg-background/40 px-2.5 py-1 text-[11px] tabular-nums text-secondary">
                  ≈ {minutes.toFixed(1)} min source
                </span>
              </div>
              <div className="max-h-[210px] overflow-y-auto rounded-xl border border-outline bg-background/35 px-4 py-3 mac-scrollbar">
                {rawMarkdown.trim() ? (
                  <div className="prose prose-sm prose-theme max-w-none text-[13px] leading-6 [&_h1]:text-lg [&_h2]:text-base [&_p]:my-2">
                    <SafeMarkdown>{rawMarkdown}</SafeMarkdown>
                  </div>
                ) : (
                  <p className="py-8 text-center text-sm text-secondary">Your article preview will appear here.</p>
                )}
              </div>
            </section>

            <details className="group rounded-2xl border border-outline bg-surface-container-low">
              <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between px-4 text-sm font-semibold text-primary outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-amber/50 [&::-webkit-details-marker]:hidden">
                <span>
                  Customize
                  <span className="ml-2 text-xs font-normal text-secondary">Optional</span>
                </span>
                <ChevronDown className="h-4 w-4 text-secondary transition-transform group-open:rotate-180" />
              </summary>
              <div className="border-t border-outline p-4">
              <fieldset>
                <legend className="text-sm font-semibold text-primary">How should Aodcast use it?</legend>
                <div className="mt-3 grid gap-2">
                  {([
                    ["adapt", Sparkles, "Podcast adaptation", "Rewrite for listening while preserving the author's facts and point of view."],
                    ["narrate", Volume2, "Faithful narration", "Keep the wording and order; only remove Markdown and visual-only phrasing."],
                  ] as const).map(([value, Icon, label, description]) => (
                    <label
                      key={value}
                      className={cn(
                        "flex cursor-pointer gap-3 rounded-xl border p-3 transition-colors",
                        conversionMode === value
                          ? "border-accent-amber/35 bg-accent-amber/8"
                          : "border-outline bg-background/20 hover:bg-surface-container",
                      )}
                    >
                      <input
                        type="radio"
                        name="conversion-mode"
                        value={value}
                        checked={conversionMode === value}
                        onChange={() => {
                          setConversionMode(value);
                          if (value === "narrate") setTargetLength("auto");
                        }}
                        className="sr-only"
                      />
                      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", conversionMode === value ? "text-accent-amber" : "text-secondary")} />
                      <span>
                        <span className="block text-sm font-medium text-primary">{label}</span>
                        <span className="mt-1 block text-xs leading-5 text-secondary">{description}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="mt-5">
                <label htmlFor="target-length" className="text-sm font-semibold text-primary">Target length</label>
                <select
                  id="target-length"
                  value={targetLength}
                  disabled={conversionMode === "narrate"}
                  onChange={(event) => setTargetLength(event.target.value as TargetLength)}
                  className="mt-2 h-11 w-full rounded-xl border border-outline bg-background/45 px-3 text-sm text-primary outline-none focus:border-accent-amber/40 disabled:cursor-not-allowed disabled:opacity-55"
                >
                  <option value="auto">Auto — follow the source</option>
                  <option value="short">Short — about 3–5 minutes</option>
                  <option value="standard">Standard — about 6–10 minutes</option>
                  <option value="long">Long — about 12–18 minutes</option>
                </select>
                {conversionMode === "narrate" ? (
                  <p className="mt-1.5 text-xs leading-5 text-secondary">Faithful narration keeps the source's natural length.</p>
                ) : null}
              </div>

              <div className="mt-5">
                <label htmlFor="focus-instructions" className="text-sm font-semibold text-primary">What should listeners remember?</label>
                <p className="mt-1 text-xs leading-5 text-secondary">Optional. Use this to emphasize one idea without changing the source facts.</p>
                <textarea
                  id="focus-instructions"
                  value={focusInstructions}
                  onChange={(event) => setFocusInstructions(event.target.value.slice(0, 1000))}
                  placeholder="For example: focus on the practical lesson in the final section."
                  className="mt-2 min-h-[88px] w-full resize-y rounded-xl border border-outline bg-background/45 px-3 py-2.5 text-sm leading-5 text-primary outline-none placeholder:text-secondary/60 focus:border-accent-amber/40"
                />
              </div>
              </div>
            </details>

            <div className="sticky bottom-0 rounded-2xl border border-outline bg-background/90 p-3 shadow-xl backdrop-blur-xl">
              {!canContinue && rawMarkdown.trim() ? (
                <p className="mb-2 px-1 text-xs text-red-300">
                  {readableCharacters > 300_000 ? "The source is over the 300,000-character limit." : "Add at least 20 characters of readable content."}
                </p>
              ) : null}
              <button
                type="button"
                disabled={!canContinue || submitting !== null}
                onClick={() => void createEpisode("generate")}
                className="flex h-11 w-full items-center justify-center gap-2 rounded-xl theme-accent-gradient px-4 text-sm font-semibold text-on-primary transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
              >
                {submitting === "generate" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {submitting === "generate" ? "Creating draft…" : "Create draft"}
              </button>
              <button
                type="button"
                disabled={!canContinue || submitting !== null}
                onClick={() => void createEpisode("discuss")}
                className="mt-2 flex h-11 w-full items-center justify-center gap-2 rounded-xl text-sm font-medium text-secondary transition-colors hover:bg-surface-container hover:text-primary disabled:cursor-not-allowed disabled:opacity-35"
              >
                {submitting === "discuss" ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}
                Discuss the source first
              </button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
