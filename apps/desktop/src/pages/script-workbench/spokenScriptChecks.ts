import type { ScriptCheckResult, ScriptIssue } from "./spokenScriptTypes";
import { countHanCharacters, countLatinWords, isCjkHeavyText } from "./spokenScriptUtils";
import { findStageDirectionSpans, lineHasSpeakerLabel, lineHasStageDirection } from "./spokenScriptPatterns";

const MARKDOWN_HEADING_PATTERN = /^\s*#{1,6}\s+/;
const MARKDOWN_LIST_PATTERN = /^\s*(?:[-*+]\s+|\d+\.\s+)/;
const MARKDOWN_QUOTE_PATTERN = /^\s*>\s+/;
const MARKDOWN_RULE_PATTERN = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;

const FILLER_PATTERNS: Array<{ pattern: RegExp; label: string }> = [
  { pattern: /(?<=^|[\s，。！？；、,\.!?;:（(])嗯(?=[\s，。！？；、,\.!?;:）)]|$)/g, label: "嗯" },
  { pattern: /(?<=^|[\s，。！？；、,\.!?;:（(])呃(?=[\s，。！？；、,\.!?;:）)]|$)/g, label: "呃" },
  { pattern: /(?<=^|[\s，。！？；、,\.!?;:（(])那个(?=[\s，。！？；、,\.!?;:）)]|$)/g, label: "那个" },
  { pattern: /\byou know\b/gi, label: "you know" },
];

const CHINESE_SENTENCE_END = /[。！？!?]/;
const ENGLISH_SENTENCE_END = /[.!?]/;
const CHINESE_PAUSE_MARKS = /[，、；：…,;:]/;

function issueId(prefix: string, line: number, index: number): string {
  return `${prefix}-${line}-${index}`;
}

function detectSpeakerLabels(lines: string[]): ScriptIssue[] {
  const issues: ScriptIssue[] = [];
  lines.forEach((line, index) => {
    if (!lineHasSpeakerLabel(line)) return;
    issues.push({
      id: issueId("speaker", index + 1, issues.length),
      level: "blocking",
      message: `Line ${index + 1} starts with a speaker label that would be read aloud.`,
      line: index + 1,
      cleanable: true,
    });
  });
  return issues;
}

function detectStageDirections(lines: string[]): ScriptIssue[] {
  const issues: ScriptIssue[] = [];
  lines.forEach((line, index) => {
    if (!line.trim() || !lineHasStageDirection(line)) return;
    issues.push({
      id: issueId("stage", index + 1, issues.length),
      level: "blocking",
      message: `Line ${index + 1} contains a stage direction or production note.`,
      line: index + 1,
      cleanable: true,
    });
  });
  return issues;
}

function detectMarkdownLeftovers(lines: string[]): ScriptIssue[] {
  const issues: ScriptIssue[] = [];
  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    if (
      MARKDOWN_HEADING_PATTERN.test(line) ||
      MARKDOWN_LIST_PATTERN.test(line) ||
      MARKDOWN_QUOTE_PATTERN.test(line) ||
      MARKDOWN_RULE_PATTERN.test(trimmed)
    ) {
      issues.push({
        id: issueId("markdown", index + 1, issues.length),
        level: "blocking",
        message: `Line ${index + 1} still contains markdown structure that would be spoken.`,
        line: index + 1,
        cleanable: true,
      });
    }
  });
  return issues;
}

function detectFillerWords(text: string): ScriptIssue[] {
  const issues: ScriptIssue[] = [];
  FILLER_PATTERNS.forEach(({ pattern, label }) => {
    const globalPattern = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`);
    let match: RegExpExecArray | null;
    let index = 0;
    while ((match = globalPattern.exec(text)) !== null) {
      const line = text.slice(0, match.index).split("\n").length;
      issues.push({
        id: issueId("filler", line, index),
        level: "warning",
        message: `High-confidence filler "${label}" may sound odd when synthesized.`,
        line,
        cleanable: true,
      });
      index += 1;
    }
  });
  return issues;
}

function detectLongChineseSentences(text: string): ScriptIssue[] {
  const issues: ScriptIssue[] = [];
  const segments = text.split(CHINESE_SENTENCE_END);
  segments.forEach((segment, index) => {
    const hanCount = countHanCharacters(segment);
    if (hanCount > 80 && !CHINESE_PAUSE_MARKS.test(segment)) {
      issues.push({
        id: issueId("long-cn-sentence", index + 1, issues.length),
        level: "warning",
        message: `A Chinese sentence has about ${hanCount} characters without a clear pause mark.`,
        cleanable: false,
      });
    }
  });
  return issues;
}

function detectLongEnglishSentences(text: string): ScriptIssue[] {
  const issues: ScriptIssue[] = [];
  const segments = text.split(ENGLISH_SENTENCE_END);
  segments.forEach((segment, index) => {
    const words = countLatinWords(segment);
    if (words > 45) {
      issues.push({
        id: issueId("long-en-sentence", index + 1, issues.length),
        level: "warning",
        message: `An English sentence has about ${words} words; shorter phrasing may sound clearer.`,
        cleanable: false,
      });
    }
  });
  return issues;
}

function splitParagraphs(text: string): string[] {
  const blocks = text.split(/\n\s*\n/).map((block) => block.trim()).filter(Boolean);
  if (blocks.length > 1) return blocks;
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function detectLongParagraphs(text: string): ScriptIssue[] {
  const issues: ScriptIssue[] = [];
  splitParagraphs(text).forEach((paragraph, index) => {
    const hanCount = countHanCharacters(paragraph);
    if (hanCount > 260) {
      issues.push({
        id: issueId("long-cn-paragraph", index + 1, issues.length),
        level: "warning",
        message: `Paragraph ${index + 1} has about ${hanCount} Chinese characters; shorter paragraphs are easier to listen to.`,
        cleanable: false,
      });
      return;
    }
    const words = countLatinWords(paragraph);
    if (words > 160) {
      issues.push({
        id: issueId("long-en-paragraph", index + 1, issues.length),
        level: "warning",
        message: `Paragraph ${index + 1} has about ${words} English words; shorter paragraphs are easier to listen to.`,
        cleanable: false,
      });
    }
  });
  return issues;
}

function detectWeakPauseStructure(text: string): ScriptIssue[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const paragraphs = splitParagraphs(trimmed);
  const hanCount = countHanCharacters(trimmed);
  const wordCount = countLatinWords(trimmed);
  const denseChinese = hanCount >= 320 && paragraphs.length <= 1;
  const denseEnglish = wordCount >= 180 && paragraphs.length <= 1;
  if (!denseChinese && !denseEnglish) return [];

  return [
    {
      id: issueId("pause-structure", 1, 0),
      level: "warning",
      message: "The script has very few paragraph breaks for its length; adding pauses may improve listening comfort.",
      cleanable: false,
    },
  ];
}

function buildInfoIssues(text: string): ScriptIssue[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const paragraphs = splitParagraphs(trimmed);
  const hanCount = countHanCharacters(trimmed);
  const wordCount = countLatinWords(trimmed);
  const cjkHeavy = isCjkHeavyText(trimmed);

  const statsMessage = cjkHeavy
    ? `About ${hanCount} Chinese characters across ${paragraphs.length} paragraph${paragraphs.length === 1 ? "" : "s"}.`
    : `About ${wordCount} spoken words across ${paragraphs.length} paragraph${paragraphs.length === 1 ? "" : "s"}.`;

  return [
    {
      id: issueId("info-stats", 1, 0),
      level: "info",
      message: statsMessage,
      cleanable: false,
    },
  ];
}

function buildStatusLabel(blockingCount: number, warningCount: number): string {
  if (blockingCount > 0) {
    return `${blockingCount} blocking issue${blockingCount === 1 ? "" : "s"}`;
  }
  if (warningCount > 0) {
    return `${warningCount} suggestion${warningCount === 1 ? "" : "s"}`;
  }
  return "Ready for TTS";
}

function buildBlockingSummary(blockingIssues: ScriptIssue[]): string | null {
  if (blockingIssues.length === 0) return null;
  const labels = blockingIssues.slice(0, 2).map((issue) => {
    if (issue.line) return `line ${issue.line}`;
    return issue.message;
  });
  const suffix = blockingIssues.length > 2 ? ` (+${blockingIssues.length - 2} more)` : "";
  return `Fix ${blockingIssues.length} blocking issue${blockingIssues.length === 1 ? "" : "s"}: ${labels.join(", ")}${suffix}`;
}

export function getPersistedScriptText(finalScript?: string | null, draftScript?: string | null): string {
  return finalScript || draftScript || "";
}

export function analyzeSpokenScript(text: string): ScriptCheckResult {
  const trimmed = text.trim();
  const lines = text.split("\n");
  const issues: ScriptIssue[] = [];

  if (!trimmed) {
    issues.push({
      id: issueId("empty", 1, 0),
      level: "blocking",
      message: "Script is empty; add spoken narration before generating audio.",
      cleanable: false,
    });
  } else {
    issues.push(
      ...detectSpeakerLabels(lines),
      ...detectStageDirections(lines),
      ...detectMarkdownLeftovers(lines),
      ...detectFillerWords(text),
      ...detectLongChineseSentences(text),
      ...detectLongEnglishSentences(text),
      ...detectLongParagraphs(text),
      ...detectWeakPauseStructure(text),
      ...buildInfoIssues(text),
    );
  }

  const blockingCount = issues.filter((issue) => issue.level === "blocking").length;
  const warningCount = issues.filter((issue) => issue.level === "warning").length;
  const infoCount = issues.filter((issue) => issue.level === "info").length;
  const blockingIssues = issues.filter((issue) => issue.level === "blocking");

  return {
    issues,
    blockingCount,
    warningCount,
    infoCount,
    statusLabel: buildStatusLabel(blockingCount, warningCount),
    blockingSummary: buildBlockingSummary(blockingIssues),
    canRender: blockingCount === 0 && trimmed.length > 0,
    hasCleanableIssues: issues.some((issue) => issue.cleanable),
  };
}

// Re-export for tests that assert inline span detection directly.
export { findStageDirectionSpans };
