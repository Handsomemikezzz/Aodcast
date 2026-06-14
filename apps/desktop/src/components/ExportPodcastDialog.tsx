import { useEffect, useState } from "react";
import { X, Download, Loader2, FileAudio, ShieldAlert, CheckCircle2 } from "lucide-react";
import { cn } from "../lib/utils";
import type { DesktopBridge } from "../lib/desktopBridge";

type ExportPodcastDialogProps = {
  open: boolean;
  audioPath: string;
  sessionTopic: string;
  bridge: DesktopBridge;
  onClose: () => void;
};

const slugify = (text: string) => {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
};

export function ExportPodcastDialog({
  open,
  audioPath,
  sessionTopic,
  bridge,
  onClose,
}: ExportPodcastDialogProps) {
  const [filename, setFilename] = useState("");
  const [format, setFormat] = useState<"m4a" | "mp3" | "wav">("m4a");
  const [quality, setQuality] = useState<"128k" | "192k" | "256k">("192k");
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (open && sessionTopic) {
      setFilename(slugify(sessionTopic));
      setError(null);
      setSuccess(false);
    }
  }, [open, sessionTopic]);

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

  const handleExport = async () => {
    if (!audioPath || exporting) return;
    setExporting(true);
    setError(null);
    try {
      const result = await bridge.exportPodcastAudio(
        audioPath,
        format,
        quality,
        filename.trim() || "podcast-episode"
      );

      // Trigger standard browser download for the returned URL
      const link = document.createElement("a");
      link.href = result.audio_url;
      link.download = result.file_name;
      document.body.appendChild(link);
      link.click();
      link.remove();

      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        onClose();
      }, 1500);
    } catch (err: any) {
      const rawMessage = err.message || String(err);
      setError(rawMessage);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center theme-modal-overlay px-4 py-6 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-lg rounded-2xl theme-modal-surface backdrop-blur-2xl p-6 shadow-2xl text-left relative overflow-hidden flex flex-col gap-5">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-outline pb-4 -mx-6 px-6">
          <div className="flex items-center gap-2.5">
            <FileAudio className="w-5 h-5 text-accent-amber" />
            <div>
              <h2 className="text-base font-headline font-bold text-primary tracking-wide">Export Podcast</h2>
              <p className="text-xs text-secondary mt-0.5">Compress and optimize audio for platform publishing</p>
            </div>
          </div>
          {!exporting && (
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-secondary hover:text-primary hover:bg-surface-container-high transition-all duration-200"
              aria-label="Close dialog"
            >
              <X className="w-4.5 h-4.5" />
            </button>
          )}
        </div>

        {/* Content Body */}
        {success ? (
          <div className="py-8 flex flex-col items-center justify-center gap-3 animate-in zoom-in-95 duration-200">
            <CheckCircle2 className="w-12 h-12 text-emerald-500 animate-pulse" />
            <h3 className="text-sm font-semibold text-primary mt-1">Export Completed!</h3>
            <p className="text-xs text-secondary">Initiating file download...</p>
          </div>
        ) : (
          <div className="space-y-4.5 py-1">
            
            {/* Error Message Panel */}
            {error && (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-3.5 flex items-start gap-3 text-red-300 text-xs leading-relaxed animate-in slide-in-from-top-2 duration-300">
                <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0 text-red-400" />
                <div className="flex-1 space-y-1">
                  <p className="font-semibold">Export Failed</p>
                  <p className="opacity-90">{error}</p>
                </div>
              </div>
            )}

            {/* Custom Filename Field */}
            <div className="space-y-2">
              <label htmlFor="filename" className="text-[11px] font-bold uppercase tracking-wider text-secondary">
                Output Filename
              </label>
              <div className="flex items-center gap-2 rounded-xl border border-outline bg-surface-container-low px-3.5 py-2.5 focus-within:border-accent-amber/35 transition-all">
                <input
                  id="filename"
                  disabled={exporting}
                  value={filename}
                  onChange={(e) => setFilename(e.target.value.replace(/[^a-zA-Z0-9\s-_]/g, ""))}
                  placeholder="podcast-episode"
                  className="flex-1 bg-transparent text-[13px] text-primary outline-none placeholder:text-secondary/60 py-0.5"
                />
                <span className="text-xs font-semibold text-secondary select-none uppercase tracking-wider bg-surface-container-high px-2 py-1 rounded border border-outline-variant">
                  .{format}
                </span>
              </div>
            </div>

            {/* Format Segmented Selection */}
            <div className="space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-secondary">
                Format
              </span>
              <div className="grid grid-cols-3 gap-2 bg-surface-container-low p-1 rounded-xl border border-outline">
                {(["m4a", "mp3", "wav"] as const).map((fmt) => (
                  <button
                    key={fmt}
                    type="button"
                    disabled={exporting}
                    onClick={() => {
                      setFormat(fmt);
                      setError(null);
                    }}
                    className={cn(
                      "py-2 rounded-lg text-xs font-semibold select-none transition-all duration-200",
                      format === fmt
                        ? "theme-accent-gradient text-on-primary shadow-md shadow-accent-amber/10"
                        : "text-secondary hover:text-primary hover:bg-surface-container-high"
                    )}
                  >
                    {fmt === "m4a" ? "M4A (AAC)" : fmt === "mp3" ? "MP3 (Lame)" : "WAV (Lossless)"}
                  </button>
                ))}
              </div>
            </div>

            {/* Quality Preset Selectors (hidden if format is WAV) */}
            {format !== "wav" && (
              <div className="space-y-2 animate-in fade-in duration-200">
                <span className="text-[11px] font-bold uppercase tracking-wider text-secondary">
                  Quality Settings
                </span>
                <div className="grid grid-cols-3 gap-2.5">
                  {[
                    { key: "128k", label: "Standard", desc: "128 kbps (Mobile)" },
                    { key: "192k", label: "High Quality", desc: "192 kbps (Feeds)" },
                    { key: "256k", label: "Pristine", desc: "256 kbps (Studio)" },
                  ].map((q) => (
                    <button
                      key={q.key}
                      type="button"
                      disabled={exporting}
                      onClick={() => setQuality(q.key as any)}
                      className={cn(
                        "flex flex-col items-center justify-center p-3 rounded-xl border transition-all text-center select-none",
                        quality === q.key
                          ? "border-accent-amber bg-accent-amber/5 text-primary"
                          : "border-outline bg-surface-container-low text-secondary hover:border-accent-amber/20 hover:text-primary"
                      )}
                    >
                      <span className="text-[12px] font-semibold">{q.label}</span>
                      <span className="text-[9px] opacity-75 mt-1 block tracking-tight font-medium">{q.desc}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            
            {/* Format Descriptive Help text */}
            <div className="bg-surface-container-low border border-outline rounded-xl px-4 py-3">
              <p className="text-[11px] leading-relaxed text-secondary font-medium">
                {format === "m4a" && "💡 M4A (AAC) provides pristine audio compression at tiny file sizes. Built-in macOS hardware-acceleration ensures lightning-fast exports."}
                {format === "mp3" && "💡 MP3 ensures universal compatibility with legacy devices and older podcast directory dashboards. Requires FFmpeg on the system."}
                {format === "wav" && "💡 WAV exports the lossless, uncompressed studio master. File sizes will be very large (~10MB/minute). Perfect for archive backups."}
              </p>
            </div>

          </div>
        )}

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-3 border-t border-outline pt-4 -mx-6 px-6">
          {!success && (
            <>
              <button
                type="button"
                disabled={exporting}
                onClick={onClose}
                className="px-4 py-2 border border-outline hover:border-accent-amber/20 text-secondary hover:text-primary rounded-xl text-xs font-semibold transition-all"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={exporting}
                onClick={handleExport}
                className="inline-flex items-center gap-1.5 px-4.5 py-2 theme-accent-gradient text-on-primary rounded-xl text-xs font-semibold hover:scale-[1.02] active:scale-[0.98] shadow-md shadow-accent-amber/10 transition-all disabled:opacity-50 disabled:scale-100 disabled:cursor-not-allowed"
              >
                {exporting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Exporting...
                  </>
                ) : (
                  <>
                    <Download className="w-3.5 h-3.5" />
                    Export Podcast
                  </>
                )}
              </button>
            </>
          )}
        </div>

      </div>
    </div>
  );
}
