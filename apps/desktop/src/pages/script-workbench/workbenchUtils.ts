export type EditorTransform = {
  nextValue: string;
  selectionStart: number;
  selectionEnd: number;
};

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

export function formatSessionState(state: string | undefined): string {
  return (state || "draft").replace(/_/g, " ").toUpperCase();
}

export function formatEstimateMinutes(wordCount: number): string {
  if (wordCount <= 0) return "~0m";
  return `~${Math.max(1, Math.round(wordCount / 150))}m`;
}

export function wrapSelection(
  value: string,
  selectionStart: number,
  selectionEnd: number,
  prefix: string,
  suffix: string,
  placeholder: string,
): EditorTransform {
  const selectedText = value.slice(selectionStart, selectionEnd);
  const body = selectedText || placeholder;
  const nextValue = value.slice(0, selectionStart) + prefix + body + suffix + value.slice(selectionEnd);
  return {
    nextValue,
    selectionStart: selectionStart + prefix.length,
    selectionEnd: selectionStart + prefix.length + body.length,
  };
}

export function prefixLines(
  value: string,
  selectionStart: number,
  selectionEnd: number,
  prefix: string,
  placeholder: string,
): EditorTransform {
  const blockStart = value.lastIndexOf("\n", Math.max(0, selectionStart - 1)) + 1;
  const blockEndIndex = value.indexOf("\n", selectionEnd);
  const blockEnd = blockEndIndex === -1 ? value.length : blockEndIndex;
  const block = value.slice(blockStart, blockEnd);
  const source = block || placeholder;
  const nextBlock = source
    .split("\n")
    .map((line) => (line.trim().length > 0 ? `${prefix}${line}` : prefix.trimEnd()))
    .join("\n");
  const nextValue = value.slice(0, blockStart) + nextBlock + value.slice(blockEnd);
  return {
    nextValue,
    selectionStart: blockStart,
    selectionEnd: blockStart + nextBlock.length,
  };
}
