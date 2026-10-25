import { ChangeEvent, DragEvent, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ChevronDown, Loader2, Upload } from "lucide-react";
import { useBridge } from "../lib/BridgeContext";
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

const CONVERSION_MODES: { value: ConversionMode; label: string; description: string }[] = [
  {
    value: "adapt",
    label: "Podcast adaptation",
    description: "Rewrite for listening while preserving the author's facts and point of view.",
  },
  {
    value: "narrate",
    label: "Faithful narration",
    description: "Keep the wording and order; only remove Markdown and visual-only phrasing.",
  },
];

export function NewEpisodePage({ onRefresh }: { onRefresh: () => Promise<void> }) {
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

  const modeDescription = CONVERSION_MODES.find((item) => item.value === conversionMode)?.description;
  const lengthHint = !rawMarkdown.trim()
    ? null
    : !canContinue
      ? readableCharacters > 300_000 ? "The source is over the 300,000-character limit." : "Add at least 20 characters of readable content."
      : null;

  return (
    <div className="h-full overflow-y-auto px-6 py-6 lg:px-10">
      <div className="mx-auto w-full max-w-3xl">
        <button
          type="button"
          onClick={() => navigate("/episodes/new")}
          className="-ml-2 mb-4 inline-flex h-9 items-center gap-1.5 rounded-lg px-2 text-[13px] text-secondary transition-colors hover:bg-primary/5 hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
          New episode
        </button>
        <h1 className="text-2xl font-headline font-semibold text-primary">Import a Markdown article</h1>
        <p className="mt-1.5 text-sm text-secondary">
          The original is kept as the episode source; the draft is written from it.
        </p>

        <div
          onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
          className={cn(
            "mt-6 rounded-xl border transition-colors",
            dragActive ? "border-accent-amber bg-accent-amber/5" : "border-outline focus-within:border-primary/20",
          )}
        >
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
            placeholder={"Paste Markdown here, or drop a .md file\n\n# Article title\n\nBody…"}
            className="block min-h-[320px] w-full resize-y rounded-t-xl bg-transparent px-4 py-4 font-mono text-[13px] leading-6 text-primary outline-none placeholder:text-secondary/60"
          />
          <div className="flex items-center gap-3 border-t border-outline px-3 py-2">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-primary transition-colors hover:bg-primary/5"
            >
              <Upload className="h-4 w-4" />
              Choose file
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,text/markdown,text/plain"
              onChange={handleFileChange}
              className="hidden"
            />
            <p className="min-w-0 flex-1 truncate text-xs text-secondary" title={importKind === "file" ? sourceName : undefined}>
              {importKind === "file" ? sourceName : ""}
            </p>
            <span className="text-xs tabular-nums text-secondary">
              {readableCharacters.toLocaleString()} / 300,000
            </span>
          </div>
        </div>

        {rawMarkdown.trim() ? (
          <p className="mt-3 truncate text-[13px] text-secondary" title={title}>
            <span className="font-medium text-primary">{title}</span>
            <span className="tabular-nums"> · ≈ {minutes.toFixed(1)} min source</span>
          </p>
        ) : null}

        <div className="mt-6 grid gap-4 sm:grid-cols-[1fr_200px]">
          <div>
            <p id="conversion-style-label" className="text-[13px] font-medium text-primary">Style</p>
            <div className="mt-2 inline-flex rounded-lg border border-outline p-0.5" role="radiogroup" aria-labelledby="conversion-style-label">
              {CONVERSION_MODES.map(({ value, label }) => (
                <label
                  key={value}
                  className={cn(
                    "cursor-pointer rounded-md px-3 py-1.5 text-[13px] transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent-amber/50",
                    conversionMode === value ? "bg-primary/[0.07] font-medium text-primary" : "text-secondary hover:text-primary",
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
                  {label}
                </label>
              ))}
            </div>
            <p className="mt-1.5 text-xs leading-5 text-secondary">{modeDescription}</p>
          </div>

          <div>
            <label htmlFor="target-length" className="block text-[13px] font-medium text-primary">Length</label>
            <select
              id="target-length"
              value={targetLength}
              disabled={conversionMode === "narrate"}
              onChange={(event) => setTargetLength(event.target.value as TargetLength)}
              title={conversionMode === "narrate" ? "Faithful narration keeps the source's natural length." : undefined}
              className="mt-2 h-9 w-full rounded-lg border border-outline bg-transparent px-2.5 text-[13px] text-primary outline-none focus:border-primary/25 disabled:cursor-not-allowed disabled:opacity-55"
            >
              <option value="auto">Follow the source</option>
              <option value="short">Short · 3–5 min</option>
              <option value="standard">Standard · 6–10 min</option>
              <option value="long">Long · 12–18 min</option>
            </select>
          </div>
        </div>

        <details className="group mt-4">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-[13px] text-secondary outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-accent-amber/50 [&::-webkit-details-marker]:hidden">
            Add a focus for listeners
            <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
          </summary>
          <label htmlFor="focus-instructions" className="sr-only">What should listeners remember?</label>
          <textarea
            id="focus-instructions"
            value={focusInstructions}
            onChange={(event) => setFocusInstructions(event.target.value.slice(0, 1000))}
            placeholder="What should listeners remember? For example: the practical lesson in the final section."
            className="mt-2 min-h-[72px] w-full resize-y rounded-lg border border-outline bg-transparent px-3 py-2 text-[13px] leading-5 text-primary outline-none placeholder:text-secondary/60 focus:border-primary/25"
          />
        </details>

        {error ? (
          <div role="alert" className="mt-5 rounded-xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
            <p>{error}</p>
            {savedSessionId ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => navigate(`/studio/${savedSessionId}`)}
                  className="rounded-lg border border-outline px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/5"
                >
                  Open saved source
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/settings")}
                  className="rounded-lg border border-outline px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/5"
                >
                  Open Settings
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-outline pt-5 pb-8">
          <button
            type="button"
            disabled={!canContinue || submitting !== null}
            onClick={() => void createEpisode("generate")}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-background transition-opacity disabled:cursor-not-allowed disabled:opacity-30"
          >
            {submitting === "generate" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {submitting === "generate" ? "Creating draft…" : "Create draft"}
          </button>
          <button
            type="button"
            disabled={!canContinue || submitting !== null}
            onClick={() => void createEpisode("discuss")}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium text-primary transition-colors hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-30"
          >
            {submitting === "discuss" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Discuss it first
          </button>
          <p className="ml-auto text-xs text-secondary">
            {lengthHint ?? "Saved locally; generation uses your configured language model."}
          </p>
        </div>
      </div>
    </div>
  );
}
