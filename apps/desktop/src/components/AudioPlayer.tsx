import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from "react";
import { Play, Pause, Volume2, VolumeX, AlertCircle } from "lucide-react";
import { cn } from "../lib/utils";
import { accentRangeBackground } from "../lib/theme";

interface AudioPlayerProps {
  src: string;
  className?: string;
  onError?: () => void;
  variant?: "full" | "minimal";
}

export const AudioPlayer = forwardRef<HTMLAudioElement, AudioPlayerProps>(
  ({ src, className, onError, variant = "full" }, ref) => {
    const audioRef = useRef<HTMLAudioElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [duration, setDuration] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [volume, setVolume] = useState(0.85);
    const [isMuted, setIsMuted] = useState(false);
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

    const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const nextVolume = parseFloat(e.target.value);
      setVolume(nextVolume);
      if (audioRef.current) {
        audioRef.current.volume = nextVolume;
      }
      if (nextVolume > 0 && isMuted) {
        setIsMuted(false);
      }
    };

    const toggleMute = () => {
      if (!audioRef.current) return;
      const nextMute = !isMuted;
      setIsMuted(nextMute);
      audioRef.current.muted = nextMute;
    };

    useEffect(() => {
      setIsPlaying(false);
      setCurrentTime(0);
      setDuration(0);
      setHasError(false);

      if (audioRef.current) {
        audioRef.current.load();
        audioRef.current.volume = isMuted ? 0 : volume;
      }
    }, [src]);

    const formatTime = (time: number) => {
      if (isNaN(time) || !isFinite(time)) return "00:00";
      const minutes = Math.floor(time / 60);
      const seconds = Math.floor(time % 60);
      const padMin = String(minutes).padStart(2, "0");
      const padSec = String(seconds).padStart(2, "0");
      return `${padMin}:${padSec}`;
    };

    const seekPercent = duration ? (currentTime / duration) * 100 : 0;
    const volumePercent = (isMuted ? 0 : volume) * 100;

    return (
      <div
        className={cn(
          "flex flex-col rounded-2xl border border-outline theme-panel-surface backdrop-blur-md shadow-sm transition-all duration-200",
          variant === "minimal" ? "p-2.5 px-3 gap-0" : "p-3.5 gap-3",
          className
        )}
      >
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

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={togglePlay}
            disabled={hasError || !src}
            className={cn(
              "flex shrink-0 items-center justify-center rounded-full text-on-primary shadow-md transition-all duration-200 focus:outline-none",
              variant === "minimal" ? "h-9 w-9" : "h-10 w-10",
              hasError
                ? "bg-red-500/20 text-red-400 cursor-not-allowed border border-red-500/20"
                : !src
                ? "bg-surface-container-high text-secondary/40 cursor-not-allowed"
                : "theme-accent-gradient hover:scale-105 active:scale-95 hover:shadow-lg hover:shadow-accent-amber/15"
            )}
          >
            {hasError ? (
              <AlertCircle className={variant === "minimal" ? "h-4 w-4 text-red-400" : "h-4.5 w-4.5 text-red-400"} />
            ) : isPlaying ? (
              <Pause className={variant === "minimal" ? "h-4 w-4 fill-current" : "h-4.5 w-4.5 fill-current"} />
            ) : (
              <Play className={variant === "minimal" ? "h-4 w-4 fill-current ml-0.5" : "h-4.5 w-4.5 fill-current ml-0.5"} />
            )}
          </button>

          {variant === "minimal" ? (
            <div className="flex-1 flex flex-col gap-1 min-w-0">
              <div className="flex items-center justify-between text-[10px] font-headline tracking-wide text-secondary/70 px-0.5">
                <span>{formatTime(currentTime)}</span>
                <span>{formatTime(duration)}</span>
              </div>

              <div className="relative w-full h-1 bg-surface-container-high rounded-full overflow-hidden">
                <div
                  className="h-full theme-accent-gradient transition-all duration-100 rounded-full"
                  style={{ width: `${seekPercent}%` }}
                />
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-[11px] font-headline tracking-wide text-secondary/90 px-0.5">
                <span>{formatTime(currentTime)}</span>
                <span>{formatTime(duration)}</span>
              </div>

              <div className="relative group w-full flex items-center h-4">
                <input
                  type="range"
                  min={0}
                  max={duration || 100}
                  value={currentTime}
                  onChange={handleSeekChange}
                  disabled={hasError || !src || duration === 0}
                  className="premium-slider w-full h-1"
                  style={{ background: accentRangeBackground(seekPercent) }}
                />
              </div>
            </div>
          )}

          {variant === "full" && (
            <div className="flex items-center gap-2 group/volume shrink-0">
              <button
                type="button"
                onClick={toggleMute}
                disabled={hasError}
                className="p-1.5 rounded-lg text-secondary hover:text-primary transition-colors focus:outline-none"
              >
                {isMuted || volume === 0 ? (
                  <VolumeX className="h-4 w-4" />
                ) : (
                  <Volume2 className="h-4 w-4" />
                )}
              </button>

              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={isMuted ? 0 : volume}
                onChange={handleVolumeChange}
                disabled={hasError}
                className="premium-slider w-16 h-1 opacity-60 group-hover/volume:opacity-100 transition-opacity"
                style={{ background: accentRangeBackground(volumePercent) }}
              />
            </div>
          )}
        </div>

        {hasError && (
          <p className="text-[11px] text-red-400/90 leading-none pl-1 flex items-center gap-1">
            <AlertCircle className="h-3 w-3" /> Error loading audio sample
          </p>
        )}
      </div>
    );
  }
);
