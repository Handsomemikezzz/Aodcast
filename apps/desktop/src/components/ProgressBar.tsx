type ProgressBarProps = {
  value: number;
  className?: string;
};

function clampProgress(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

export function ProgressBar({ value, className = "" }: ProgressBarProps) {
  const progress = clampProgress(value);
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-outline/30 ${className}`}>
      <div
        className="h-full rounded-full bg-accent-amber transition-[width] duration-300 ease-out"
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}
