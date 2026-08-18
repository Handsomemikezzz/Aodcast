import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  FileAudio,
  FolderOpen,
  Loader2,
  ShieldAlert,
  X,
} from "lucide-react";
import type { DesktopBridge } from "../lib/desktopBridge";
import { revealInFinder } from "../lib/shellOps";
import {
  XIAOYUZHOU_AUDIO_BITRATE,
  XIAOYUZHOU_AUDIO_FORMAT,
  XIAOYUZHOU_PODCASTER_URL,
  xiaoyuzhouExportFilename,
} from "../pages/script-workbench/xiaoyuzhouPublishPrep";

type ExportResult = {
  audio_url: string;
  file_name: string;
  audio_path: string;
};

type XiaoyuzhouPublishDialogProps = {
  open: boolean;
  audioPath: string;
  episodeTitle: string;
  initialShowNotes: string;
  bridge: DesktopBridge;
  onClose: () => void;
};

function triggerDownload(result: ExportResult): void {
  const link = document.createElement("a");
  link.href = result.audio_url;
  link.download = result.file_name;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export function XiaoyuzhouPublishDialog({
  open,
  audioPath,
  episodeTitle,
  initialShowNotes,
  bridge,
  onClose,
}: XiaoyuzhouPublishDialogProps) {
  const [title, setTitle] = useState(episodeTitle);
  const [showNotes, setShowNotes] = useState(initialShowNotes);
  const [filename, setFilename] = useState(() => xiaoyuzhouExportFilename(episodeTitle));
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<ExportResult | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle(episodeTitle);
    setShowNotes(initialShowNotes);
    setFilename(xiaoyuzhouExportFilename(episodeTitle));
    setError(null);
    setNotice(null);
    setExportResult(null);
  }, [open, episodeTitle, initialShowNotes]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !exporting) {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose, exporting]);

  if (!open) return null;

  const copyText = async (label: string, value: string) => {
    if (!value.trim()) return;
    try {
      await navigator.clipboard.writeText(value.trim());
      setNotice(`${label} copied.`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to copy ${label.toLowerCase()}.`);
    }
  };

  const handleExport = async () => {
    if (!audioPath || exporting || !title.trim()) return;
    setExporting(true);
    setError(null);
    setNotice(null);
    setExportResult(null);
    try {
      const result = await bridge.exportPodcastAudio(
        audioPath,
        XIAOYUZHOU_AUDIO_FORMAT,
        XIAOYUZHOU_AUDIO_BITRATE,
        filename.trim() || "podcast-episode",
      );
      setExportResult(result);
      triggerDownload(result);
      setNotice("MP3 is ready. Copy the metadata, then upload it in Xiaoyuzhou.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to prepare the Xiaoyuzhou MP3.");
    } finally {
      setExporting(false);
    }
  };

  const handleReveal = async () => {
    if (!exportResult?.audio_path) return;
    try {
      await revealInFinder(exportResult.audio_path);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reveal the exported MP3.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center theme-modal-overlay px-4 py-6 backdrop-blur-md animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="xiaoyuzhou-publish-title"
        className="relative flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl theme-modal-surface shadow-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-outline px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-accent-amber/30 bg-accent-amber/10">
              <FileAudio className="h-5 w-5 text-accent-amber" />
            </div>
            <div>
              <h2 id="xiaoyuzhou-publish-title" className="text-base font-headline font-bold text-primary">小宇宙发布准备</h2>
              <p className="mt-1 text-xs text-secondary">导出 MP3 和文案，然后前往小宇宙主播后台手动上传。</p>
            </div>
          </div>
          {!exporting ? (
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-secondary transition-colors hover:bg-surface-container-high hover:text-primary"
              aria-label="Close Xiaoyuzhou publish preparation"
            >
              <X className="h-4.5 w-4.5" />
            </button>
          ) : null}
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          <ol className="grid gap-3 sm:grid-cols-3" aria-label="Manual publishing steps">
            {[
              ["1", "导出 MP3", "固定为 MP3 · 192 kbps"],
              ["2", "复制发布文案", "标题和简介由你最终确认"],
              ["3", "上传小宇宙", "小宇宙负责托管和 RSS"],
            ].map(([step, heading, detail]) => (
              <li key={step} className="rounded-2xl border border-outline bg-surface-container-low p-3.5">
                <div className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-accent-amber/15 text-xs font-bold text-accent-amber">{step}</div>
                <p className="text-sm font-semibold text-primary">{heading}</p>
                <p className="mt-1 text-xs leading-relaxed text-secondary">{detail}</p>
              </li>
            ))}
          </ol>

          {error ? (
            <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-3.5 text-xs leading-relaxed text-red-300">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
              <div>
                <p className="font-semibold">Preparation failed</p>
                <p className="mt-1 opacity-90">{error}</p>
              </div>
            </div>
          ) : null}

          {notice ? (
            <div aria-live="polite" className="flex items-start gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3.5 text-xs text-emerald-300">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <p>{notice}</p>
            </div>
          ) : null}

          <div className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="xiaoyuzhou-title" className="block text-[11px] font-bold uppercase tracking-wider text-secondary">Episode title *</label>
              <div className="flex gap-2">
                <input
                  id="xiaoyuzhou-title"
                  required
                  autoFocus
                  value={title}
                  disabled={exporting}
                  onChange={(event) => setTitle(event.target.value)}
                  className="h-11 min-w-0 flex-1 rounded-xl border border-outline bg-surface-container-low px-3.5 text-sm text-primary outline-none transition-colors focus:border-accent-amber/40"
                />
                <button
                  type="button"
                  disabled={!title.trim()}
                  onClick={() => void copyText("Title", title)}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline px-3 text-xs font-bold text-primary transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Copy className="h-4 w-4" />
                  Copy
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="xiaoyuzhou-notes" className="block text-[11px] font-bold uppercase tracking-wider text-secondary">Show notes</label>
              <textarea
                id="xiaoyuzhou-notes"
                value={showNotes}
                disabled={exporting}
                onChange={(event) => setShowNotes(event.target.value)}
                placeholder="本期内容简介、相关链接或时间轴……"
                className="min-h-28 w-full resize-y rounded-xl border border-outline bg-surface-container-low px-3.5 py-3 text-sm leading-relaxed text-primary outline-none transition-colors placeholder:text-secondary/60 focus:border-accent-amber/40"
              />
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-secondary">简介仅用于复制，不会写入平台或项目文件。</p>
                <button
                  type="button"
                  disabled={!showNotes.trim()}
                  onClick={() => void copyText("Show notes", showNotes)}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline px-3 text-xs font-bold text-primary transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Copy className="h-4 w-4" />
                  Copy notes
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="xiaoyuzhou-filename" className="block text-[11px] font-bold uppercase tracking-wider text-secondary">MP3 filename</label>
              <div className="flex h-11 items-center rounded-xl border border-outline bg-surface-container-low px-3.5 focus-within:border-accent-amber/40">
                <input
                  id="xiaoyuzhou-filename"
                  value={filename}
                  disabled={exporting}
                  onChange={(event) => setFilename(event.target.value.replace(/[^a-zA-Z0-9\s-_]/g, ""))}
                  className="min-w-0 flex-1 bg-transparent text-sm text-primary outline-none"
                />
                <span className="rounded-lg border border-outline-variant bg-surface-container-high px-2 py-1 text-xs font-semibold text-secondary">.mp3</span>
              </div>
            </div>
          </div>

          {exportResult ? (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-primary">MP3 ready for upload</p>
                  <p className="mt-1 truncate text-xs text-secondary">{exportResult.file_name}</p>
                </div>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => triggerDownload(exportResult)}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container-high/60 text-xs font-bold text-primary transition-colors hover:bg-surface-container-high"
                >
                  <Download className="h-4 w-4" />
                  Download again
                </button>
                <button
                  type="button"
                  onClick={() => void handleReveal()}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container-high/60 text-xs font-bold text-primary transition-colors hover:bg-surface-container-high"
                >
                  <FolderOpen className="h-4 w-4" />
                  Reveal in Finder
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex flex-col-reverse gap-3 border-t border-outline px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            disabled={exporting}
            onClick={onClose}
            className="inline-flex h-11 items-center justify-center rounded-xl border border-outline px-4 text-xs font-bold text-secondary transition-colors hover:bg-surface-container-high hover:text-primary disabled:opacity-50"
          >
            Close
          </button>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              disabled={exporting || !audioPath || !title.trim()}
              onClick={() => void handleExport()}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container-high px-4 text-xs font-bold text-primary transition-colors hover:bg-surface-container-highest disabled:cursor-not-allowed disabled:opacity-50"
            >
              {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              {exporting ? "Preparing..." : exportResult ? "Export another MP3" : "Export MP3"}
            </button>
            {exportResult ? (
              <a
                href={XIAOYUZHOU_PODCASTER_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl theme-accent-gradient px-4 text-xs font-bold text-on-primary shadow-md shadow-accent-amber/10 transition-transform hover:scale-[1.02] active:scale-[0.98]"
              >
                <ExternalLink className="h-4 w-4" />
                打开小宇宙主播后台
              </a>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
