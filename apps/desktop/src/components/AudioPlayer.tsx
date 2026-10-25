import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from "react";
import { Play, Pause, AlertCircle } from "lucide-react";
import { cn } from "../lib/utils";
import { accentRangeBackground } from "../lib/theme";

interface AudioPlayerProps {
  src: string;
  className?: string;
  onError?: () => void;
}

/** Compact single-row player: play/pause, elapsed time, seek bar, duration. */
export const AudioPlayer = forwardRef<HTMLAudioElement, AudioPlayerProps>(
  ({ src, className, onError }, ref) => {
    const audioRef = useRef<HTMLAudioElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [duration, setDuration] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [hasError, setHasError] = useState(false);

    useImperativeHandle(ref, () => audioRef.current!);

    const togglePlay = () => {
      if (!audioRef.current || hasError) return;
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        audioRef.current.play().catch(() => {
          setHasError(true);
          if (onError) onError();
        });
        setIsPlaying(true);
      }
    };

    const handleTimeUpdate = () => {
      if (!audioRef.current) return;
      setCurrentTime(audioRef.current.currentTime);
    };

    const handleLoadedMetadata = () => {
      if (!audioRef.current) return;
      setDuration(audioRef.current.duration);
      setHasError(false);
    };

    const handleEnded = () => {
      setIsPlaying(false);
      setCurrentTime(0);
    };

    const handleAudioError = () => {
      setHasError(true);
      setIsPlaying(false);
      if (onError) onError();
    };

    const handleSeekChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!audioRef.current) return;
      const seekTime = parseFloat(e.target.value);
      audioRef.current.currentTime = seekTime;
      setCurrentTime(seekTime);
    };

    useEffect(() => {
      setIsPlaying(false);
      setCurrentTime(0);
      setDuration(0);
      setHasError(false);
      audioRef.current?.load();
    }, [src]);

    const formatTime = (time: number) => {
      if (isNaN(time) || !isFinite(time)) return "0:00";
      const minutes = Math.floor(time / 60);
      const seconds = Math.floor(time % 60);
      return `${minutes}:${String(seconds).padStart(2, "0")}`;
    };

    const seekPercent = duration ? (currentTime / duration) * 100 : 0;

    return (
      <div className={cn("flex items-center gap-2.5", className)}>
        <audio
          ref={audioRef}
          src={src}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleEnded}
          onError={handleAudioError}
          preload="metadata"
        />

        <button
          type="button"
          onClick={togglePlay}
          disabled={hasError || !src}
          aria-label={hasError ? "Audio unavailable" : isPlaying ? "Pause audio" : "Play audio"}
          title={hasError ? "Audio unavailable" : undefined}
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/60",
            hasError
              ? "bg-red-500/10 text-red-600 dark:text-red-300 cursor-not-allowed"
              : !src
                ? "bg-primary/5 text-secondary/40 cursor-not-allowed"
                : "bg-accent-amber text-on-primary hover:opacity-90",
          )}
        >
          {hasError ? (
            <AlertCircle className="h-4 w-4" />
          ) : isPlaying ? (
            <Pause className="h-3.5 w-3.5 fill-current" />
          ) : (
            <Play className="h-3.5 w-3.5 fill-current ml-0.5" />
          )}
        </button>

        <span className="w-9 shrink-0 text-right text-[11px] tabular-nums text-secondary">{formatTime(currentTime)}</span>
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.1}
          value={currentTime}
          onChange={handleSeekChange}
          disabled={hasError || !src || duration === 0}
          aria-label="Seek audio"
          className="premium-slider h-1 min-w-0 flex-1"
          style={{ background: accentRangeBackground(seekPercent) }}
        />
        <span className="w-9 shrink-0 text-[11px] tabular-nums text-secondary">{formatTime(duration)}</span>
      </div>
    );
  }
);
