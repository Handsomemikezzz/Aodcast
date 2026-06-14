export const STAGE_DIRECTION_KEYWORDS =
  /(?:music|pause|sfx|sound|effect|opening|closing|intro|outro|停顿|音效|音乐|配乐|旁白|静音|渐弱|渐强)/i;

export const SPEAKER_LABEL_BODY_PATTERN =
  /^(?:host|narrator|speaker|guest|anchor|co-host|cohost|announcer|主播|旁白|主持人|嘉宾|解说|讲述者)\s*[:：]\s*/i;

export const SPEAKER_LABEL_LINE_PATTERN =
  /^(\s*)(?:host|narrator|speaker|guest|anchor|co-host|cohost|announcer|主播|旁白|主持人|嘉宾|解说|讲述者)\s*[:：]\s*(.*)$/i;

export const STAGE_DIRECTION_SPAN_PATTERN = /(\[[^\]]+\]|\([^)]+\)|【[^】]+】|（[^）]+）)/g;

export function lineHasSpeakerLabel(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.length > 0 && SPEAKER_LABEL_BODY_PATTERN.test(trimmed);
}

export function stripSpeakerLabelLine(line: string): string | null {
  const match = line.match(SPEAKER_LABEL_LINE_PATTERN);
  if (!match) return null;
  return `${match[1] ?? ""}${match[2] ?? ""}`;
}

export function isStageDirectionSpan(span: string): boolean {
  return STAGE_DIRECTION_KEYWORDS.test(span);
}

export function findStageDirectionSpans(text: string): Array<{ match: string; index: number }> {
  const results: Array<{ match: string; index: number }> = [];
  const pattern = new RegExp(STAGE_DIRECTION_SPAN_PATTERN.source, "g");
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (isStageDirectionSpan(match[0])) {
      results.push({ match: match[0], index: match.index });
    }
  }
  return results;
}

export function lineHasStageDirection(line: string): boolean {
  return findStageDirectionSpans(line).length > 0;
}
