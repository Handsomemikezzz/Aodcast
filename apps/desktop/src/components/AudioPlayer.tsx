import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from "react";
import { Play, Pause, Volume2, VolumeX, AlertCircle } from "lucide-react";
import { cn } from "../lib/utils";

interface AudioPlayerProps {
  src: string;
  className?: string;
  onError?: () => void;
}

export const AudioPlayer = forwardRef<HTMLAudioElement, AudioPlayerProps>(
  ({ src, className, onError }, ref) => {
    const audioRef = useRef<HTMLAudioElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [duration, setDuration] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [volume, setVolume] = useState(0.85);
    const [isMuted, setIsMuted] = useState(false);
    const [hasError, setHasError] = useState(false);

    useImperativeHandle(ref, () => audioRef.current!);

    // Sync isPlaying with audio element state
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
      // Reset player states when source changes
      setIsPlaying(false);
      setCurrentTime(0);
      setDuration(0);
      setHasError(false);

      if (audioRef.current) {
        audioRef.current.load();
        audioRef.current.volume = isMuted ? 0 : volume;
      }
    }, [src]);

    // Format time (e.g. 153.2 -> "02:33")
    const formatTime = (time: number) => {
      if (isNaN(time) || !isFinite(time)) return "00:00";
      const minutes = Math.floor(time / 60);
      const seconds = Math.floor(time % 60);
      const padMin = String(minutes).padStart(2, "0");
      const padSec = String(seconds).padStart(2, "0");
      return `${padMin}:${padSec}`;
    };

    return (
      <div 
        className={cn(
          "flex flex-col gap-3 rounded-2xl border border-white/5 bg-[rgba(20,20,24,0.45)] p-3.5 backdrop-blur-md shadow-sm transition-all duration-200", 
          className
        )}
      >
        {/* Hidden audio element */}
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
          {/* Play/Pause Button */}
          <button
            type="button"
            onClick={togglePlay}
            disabled={hasError || !src}
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-black shadow-md transition-all duration-200 focus:outline-none",
              hasError
                ? "bg-red-500/20 text-red-200 cursor-not-allowed border border-red-500/20"
                : !src
                ? "bg-white/10 text-white/40 cursor-not-allowed"
                : "bg-gradient-to-b from-[#f2bf57] to-[#d79b2f] hover:scale-105 active:scale-95 hover:shadow-lg hover:shadow-accent-amber/15"
            )}
          >
            {hasError ? (
              <AlertCircle className="h-4.5 w-4.5 text-red-400" />
            ) : isPlaying ? (
              <Pause className="h-4.5 w-4.5 fill-current text-black" />
            ) : (
              <Play className="h-4.5 w-4.5 fill-current ml-0.5 text-black" />
            )}
          </button>

          {/* Progress Slider Bar */}
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
                style={{
                  background: `linear-gradient(to right, #f2bf57 0%, #f2bf57 ${duration ? (currentTime / duration) * 100 : 0}%, rgba(255, 255, 255, 0.08) ${duration ? (currentTime / duration) * 100 : 0}%, rgba(255, 255, 255, 0.08) 100%)`
                }}
              />
            </div>
          </div>

          {/* Volume Controller */}
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
              style={{
                background: `linear-gradient(to right, #f2bf57 0%, #f2bf57 ${(isMuted ? 0 : volume) * 100}%, rgba(255, 255, 255, 0.08) ${(isMuted ? 0 : volume) * 100}%, rgba(255, 255, 255, 0.08) 100%)`
              }}
            />
          </div>
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
