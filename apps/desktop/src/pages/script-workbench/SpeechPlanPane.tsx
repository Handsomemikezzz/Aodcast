import {
  AlertTriangle,
  AudioLines,
  CheckCircle2,
  ChevronRight,
  CircleX,
  Clock3,
  Languages,
  Loader2,
  Pause,
  RotateCcw,
  Sparkles,
  Timer,
  Type,
} from "lucide-react";
import { AudioPlayer } from "../../components/AudioPlayer";
import { resolveAudioFileUrl } from "../../lib/audioFile";
import { cn } from "../../lib/utils";
import type {
  RenderManifest,
  RenderedSegment,
  RequestState,
  SpeechPlan,
  SpeechSegment,
} from "../../types";

type SegmentDisplayStatus = "waiting" | "rendering" | "ready" | "stale" | "failed";

const ACTIVE_REQUEST_PHASES = new Set<RequestState["phase"]>(["running", "cancelling"]);

const STATUS_PRESENTATION: Record<
  SegmentDisplayStatus,
  { label: string; icon: typeof Clock3; className: string }
> = {
  waiting: {
    label: "等待生成",
    icon: Clock3,
    className: "border-outline bg-surface-container-high/60 text-secondary",
  },
  rendering: {
    label: "生成中",
    icon: Loader2,
    className: "border-accent-amber/25 bg-accent-amber/10 text-accent-amber",
  },
  ready: {
    label: "可试听",
    icon: CheckCircle2,
    className: "border-emerald-500/20 bg-emerald-500/10 text-emerald-300",
  },
  stale: {
    label: "已过期",
    icon: AlertTriangle,
    className: "border-amber-500/20 bg-amber-500/10 text-amber-200",
  },
  failed: {
    label: "生成失败",
    icon: CircleX,
    className: "border-red-500/20 bg-red-500/10 text-red-300",
  },
};

function formatDuration(durationMs: number): string {
  if (durationMs >= 1_000) {
    const seconds = durationMs / 1_000;
    return `${Number.isInteger(seconds) ? seconds.toFixed(0) : seconds.toFixed(1)} 秒`;
  }
  return `${durationMs} 毫秒`;
}

function codePointSlice(text: string, start: number, end: number): string {
  return Array.from(text).slice(start, end).join("");
}

function resolveStatus({
  segment,
  renderedSegment,
  planIsStale,
  requestState,
  requestAppliesToSegment,
}: {
  segment: SpeechSegment;
  renderedSegment: RenderedSegment | undefined;
  planIsStale: boolean;
  requestState: RequestState | null;
  requestAppliesToSegment: boolean;
}): SegmentDisplayStatus {
  if (planIsStale || (renderedSegment && renderedSegment.segment_hash !== segment.segment_hash)) {
    return "stale";
  }
  if (requestAppliesToSegment && requestState && ACTIVE_REQUEST_PHASES.has(requestState.phase)) return "rendering";
  if (requestAppliesToSegment && requestState?.phase === "failed") return "failed";
  if (renderedSegment?.audio_path) return "ready";
  return "waiting";
}

function StatusChip({ status }: { status: SegmentDisplayStatus }) {
  const presentation = STATUS_PRESENTATION[status];
  const Icon = presentation.icon;

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold",
        presentation.className,
      )}
    >
      <Icon className={cn("h-3.5 w-3.5", status === "rendering" && "animate-spin")} aria-hidden="true" />
      {presentation.label}
    </span>
  );
}

function AnnotationGroup({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Pause;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-outline bg-surface-container-high/45 p-3">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-bold text-secondary">
        <Icon className="h-3.5 w-3.5 text-accent-amber" aria-hidden="true" />
        {title}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function AnnotationChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-lg border border-outline bg-surface-container px-2.5 py-1.5 text-xs leading-5 text-primary">
      {children}
    </span>
  );
}

export type SpeechSegmentRowProps = {
  segment: SpeechSegment;
  renderedSegment?: RenderedSegment;
  planIsStale: boolean;
  activeRequestState: RequestState | null;
  disabled?: boolean;
  isAffected?: boolean;
  onRequestRegeneration: (segmentId: string) => void | Promise<void>;
};

export function SpeechSegmentRow({
  segment,
  renderedSegment,
  planIsStale,
  activeRequestState,
  disabled = false,
  isAffected = true,
  onRequestRegeneration,
}: SpeechSegmentRowProps) {
  const requestIsActive = Boolean(
    activeRequestState && ACTIVE_REQUEST_PHASES.has(activeRequestState.phase),
  );
  const status = resolveStatus({
    segment,
    renderedSegment,
    planIsStale,
    requestState: activeRequestState,
    requestAppliesToSegment: isAffected,
  });
  const segmentIsStale = planIsStale
    || Boolean(renderedSegment && renderedSegment.segment_hash !== segment.segment_hash);
  const canRegenerate = Boolean(renderedSegment?.audio_path) && !segmentIsStale && !requestIsActive && !disabled;
  const audioSrc = renderedSegment?.audio_path
    ? resolveAudioFileUrl(renderedSegment.audio_path)
    : "";

  const regenerationHint = segmentIsStale
    ? "Speech Plan 已过期，请先完整生成音频。"
    : requestIsActive
      ? "当前已有音频任务正在进行。"
      : !renderedSegment?.audio_path
        ? "请先生成完整音频。"
        : disabled
          ? "当前不可局部重生成。"
          : undefined;

  return (
    <details className="group rounded-2xl border border-outline bg-surface-container-low transition-colors open:bg-surface-container">
      <summary className="flex min-h-16 cursor-pointer list-none items-center gap-3 px-4 py-3 outline-none transition-colors hover:bg-surface-container-high/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-amber/50 [&::-webkit-details-marker]:hidden">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-outline bg-surface-container-high text-xs font-bold tabular-nums text-secondary">
          {segment.position + 1}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-primary">{segment.text}</span>
          <span className="mt-1 block truncate text-[11px] text-secondary/75">
            {segment.delivery.intent} · {segment.delivery.emotion} · 能量 {Math.round(segment.delivery.energy * 100)}% · 语速 {segment.delivery.pace.toFixed(2)}×
          </span>
        </span>
        <StatusChip status={status} />
        <ChevronRight
          className="h-4 w-4 shrink-0 text-secondary transition-transform duration-200 group-open:rotate-90"
          aria-hidden="true"
        />
      </summary>

      <div className="border-t border-outline px-4 pb-4 pt-4">
        <p className="whitespace-pre-wrap text-sm leading-7 text-primary">{segment.text}</p>

        <dl className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-outline bg-surface-container-high/45 px-3 py-2.5">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-secondary/70">表达意图</dt>
            <dd className="mt-1 text-xs font-semibold text-primary">{segment.delivery.intent}</dd>
          </div>
          <div className="rounded-xl border border-outline bg-surface-container-high/45 px-3 py-2.5">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-secondary/70">情绪</dt>
            <dd className="mt-1 text-xs font-semibold text-primary">{segment.delivery.emotion}</dd>
          </div>
          <div className="rounded-xl border border-outline bg-surface-container-high/45 px-3 py-2.5">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-secondary/70">能量</dt>
            <dd className="mt-1 text-xs font-semibold tabular-nums text-primary">
              {Math.round(segment.delivery.energy * 100)}%
            </dd>
          </div>
          <div className="rounded-xl border border-outline bg-surface-container-high/45 px-3 py-2.5">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-secondary/70">语速</dt>
            <dd className="mt-1 text-xs font-semibold tabular-nums text-primary">
              {segment.delivery.pace.toFixed(2)}×
            </dd>
          </div>
        </dl>

        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <AnnotationGroup icon={Pause} title={`段内停顿 · ${segment.breaks.length}`}>
            {segment.breaks.length ? (
              segment.breaks.map((speechBreak, index) => (
                <AnnotationChip key={`${speechBreak.offset}-${speechBreak.duration_ms}-${index}`}>
                  字符 {speechBreak.offset} · {formatDuration(speechBreak.duration_ms)}
                </AnnotationChip>
              ))
            ) : (
              <span className="text-xs text-secondary/60">无段内停顿</span>
            )}
          </AnnotationGroup>

          <AnnotationGroup icon={Type} title={`重音 · ${segment.emphasis.length}`}>
            {segment.emphasis.length ? (
              segment.emphasis.map((emphasis, index) => (
                <AnnotationChip key={`${emphasis.start}-${emphasis.end}-${index}`}>
                  “{codePointSlice(segment.text, emphasis.start, emphasis.end)}” · {emphasis.level}
                </AnnotationChip>
              ))
            ) : (
              <span className="text-xs text-secondary/60">无重音标记</span>
            )}
          </AnnotationGroup>

          <AnnotationGroup icon={Languages} title={`发音 · ${segment.pronunciations.length}`}>
            {segment.pronunciations.length ? (
              segment.pronunciations.map((pronunciation, index) => (
                <AnnotationChip key={`${pronunciation.start}-${pronunciation.end}-${index}`}>
                  “{codePointSlice(segment.text, pronunciation.start, pronunciation.end)}” → “{pronunciation.spoken_as}”
                </AnnotationChip>
              ))
            ) : (
              <span className="text-xs text-secondary/60">无发音替换</span>
            )}
          </AnnotationGroup>

          <AnnotationGroup icon={Timer} title="段后停顿">
            <AnnotationChip>{formatDuration(segment.pause_after_ms)}</AnnotationChip>
          </AnnotationGroup>
        </div>

        <div className="mt-4 flex flex-col gap-3 border-t border-outline pt-4">
          {audioSrc ? (
            <div>
              <div className="mb-2 flex items-center justify-between gap-3 text-[11px] text-secondary/75">
                <span className="inline-flex items-center gap-1.5 font-semibold">
                  <AudioLines className="h-3.5 w-3.5 text-accent-amber" aria-hidden="true" />
                  分段音频
                </span>
                {renderedSegment ? (
                  <span className="tabular-nums">{formatDuration(renderedSegment.duration_ms)}</span>
                ) : null}
              </div>
              <AudioPlayer src={audioSrc} variant="minimal" />
            </div>
          ) : (
            <div className="flex min-h-12 items-center gap-2 rounded-xl border border-dashed border-outline px-3 text-xs text-secondary/70">
              <Clock3 className="h-4 w-4" aria-hidden="true" />
              此段尚无可试听音频。
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="min-w-0 flex-1 text-xs leading-5 text-secondary/70">
              局部重生成会同时更新当前段及相邻上下文段。
            </p>
            <button
              type="button"
              onClick={() => void onRequestRegeneration(segment.segment_id)}
              disabled={!canRegenerate}
              title={regenerationHint}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container-high px-4 text-xs font-bold text-primary transition-colors hover:border-accent-amber/30 hover:bg-accent-amber/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {requestIsActive ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
              )}
              {requestIsActive ? "音频任务进行中" : "局部重生成"}
            </button>
          </div>
        </div>
      </div>
    </details>
  );
}

export type SpeechPlanPaneProps = {
  plan: SpeechPlan | null;
  manifest?: RenderManifest | null;
  activeRequestState?: RequestState | null;
  disabled?: boolean;
  stale?: boolean;
  affectedSegmentIds?: string[];
  onRequestRegeneration: (segmentId: string) => void | Promise<void>;
};

export function SpeechPlanPane({
  plan,
  manifest = null,
  activeRequestState = null,
  disabled = false,
  stale = false,
  affectedSegmentIds = [],
  onRequestRegeneration,
}: SpeechPlanPaneProps) {
  if (!plan || plan.segments.length === 0) {
    return (
      <section className="flex h-full min-h-[420px] items-center justify-center rounded-[28px] border border-outline bg-surface-container p-6">
        <div className="max-w-sm text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-outline bg-surface-container-high text-accent-amber">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </span>
          <h2 className="mt-4 text-base font-bold text-primary">还没有 Speech Plan</h2>
          <p className="mt-2 text-sm leading-6 text-secondary/75">
            生成完整音频时会先创建停顿与表达计划，完成后可在这里逐段查看和试听。
          </p>
        </div>
      </section>
    );
  }

  const manifestMatchesPlan = Boolean(
    manifest
      && manifest.script_hash === plan.script_hash
      && manifest.speech_plan.plan_id === plan.plan_id
      && manifest.speech_plan.version === plan.version
      && manifest.speech_plan.plan_hash === plan.plan_hash,
  );
  const planIsStale = stale || Boolean(manifest && !manifestMatchesPlan);
  const renderedBySegmentId = new Map<string, RenderedSegment>(
    manifest?.segments.map((segment) => [segment.segment_id, segment]) ?? [],
  );
  const requestIsActive = Boolean(
    activeRequestState && ACTIVE_REQUEST_PHASES.has(activeRequestState.phase),
  );
  const affectedSet = new Set(affectedSegmentIds);
  const allSegmentsAffected = affectedSet.size === 0;

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] border border-outline bg-surface-container shadow-[0_12px_32px_rgba(0,0,0,0.04)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline px-5 py-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-bold text-primary">Speech Plan</h2>
            <span className="rounded-full border border-outline bg-surface-container-high px-2 py-0.5 text-[10px] font-bold text-secondary">
              v{plan.version}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-secondary/75">
            {plan.segments.length} 个分段 · {plan.language} · 只读表达计划
          </p>
        </div>
        <div className="flex items-center gap-2" aria-live="polite" aria-atomic="true">
          {requestIsActive ? (
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent-amber">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              {activeRequestState?.message || "正在生成音频"}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-xs text-secondary/70">
              <AudioLines className="h-3.5 w-3.5" aria-hidden="true" />
              展开分段查看细节
            </span>
          )}
        </div>
      </div>

      {planIsStale ? (
        <div className="mx-5 mt-4 flex items-start gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-amber-100" role="status">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-xs font-bold">Speech Plan 已过期</p>
            <p className="mt-1 text-xs leading-5 text-amber-100/75">
              脚本或计划版本已变化。旧分段仍可试听，但需要完整生成后才能局部重生成。
            </p>
          </div>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 mac-scrollbar">
        <div className="space-y-3">
          {plan.segments.map((segment) => (
            <SpeechSegmentRow
              key={segment.segment_id}
              segment={segment}
              renderedSegment={renderedBySegmentId.get(segment.segment_id)}
              planIsStale={planIsStale}
              activeRequestState={activeRequestState}
              isAffected={allSegmentsAffected || affectedSet.has(segment.segment_id)}
              disabled={disabled}
              onRequestRegeneration={onRequestRegeneration}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
