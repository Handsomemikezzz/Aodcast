import type { SpeechSegment } from "../../types";

export function contextWindowSegmentIds(
  segments: Pick<SpeechSegment, "segment_id">[],
  targetSegmentId: string,
): string[] {
  const targetIndex = segments.findIndex((segment) => segment.segment_id === targetSegmentId);
  if (targetIndex < 0) return [];
  return segments
    .slice(Math.max(0, targetIndex - 1), Math.min(segments.length, targetIndex + 2))
    .map((segment) => segment.segment_id);
}

export function estimateWordCount(text: string): number {
  const normalized = text.trim();
  if (!normalized) return 0;
  const cjkMatches = normalized.match(/[\u3400-\u9FFF\uF900-\uFAFF]/g);
  if (cjkMatches && cjkMatches.length > 0) {
    const latinWordCount = normalized
      .replace(/[\u3400-\u9FFF\uF900-\uFAFF]/g, " ")
      .split(/\s+/)
      .filter(Boolean).length;
    return Math.max(latinWordCount, Math.ceil(cjkMatches.length / 2));
  }
  return normalized.split(/\s+/).filter(Boolean).length;
}

export function formatEstimateMinutes(wordCount: number): string {
  if (wordCount <= 0) return "~0m";
  return `~${Math.max(1, Math.round(wordCount / 150))}m`;
}
