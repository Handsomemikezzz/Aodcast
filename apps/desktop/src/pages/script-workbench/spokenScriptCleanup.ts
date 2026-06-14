import type { CleanupChange, CleanupPreview } from "./spokenScriptTypes";
import {
  STAGE_DIRECTION_SPAN_PATTERN,
  isStageDirectionSpan,
  stripSpeakerLabelLine,
} from "./spokenScriptPatterns";

const MARKDOWN_HEADING_PATTERN = /^(\s*)#{1,6}\s+(.*)$/;
const MARKDOWN_LIST_PATTERN = /^(\s*)(?:[-*+]\s+|\d+\.\s+)(.*)$/;
const MARKDOWN_QUOTE_PATTERN = /^(\s*)>\s+(.*)$/;
const MARKDOWN_RULE_PATTERN = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;

const FILLER_REPLACERS: Array<{ pattern: RegExp; label: string }> = [
  { pattern: /(?<=^|[\s，。！？；、,\.!?;:（(])嗯(?=[\s，。！？；、,\.!?;:）)]|$)/g, label: "嗯" },
  { pattern: /(?<=^|[\s，。！？；、,\.!?;:（(])呃(?=[\s，。！？；、,\.!?;:）)]|$)/g, label: "呃" },
  { pattern: /(?<=^|[\s，。！？；、,\.!?;:（(])那个(?=[\s，。！？；、,\.!?;:）)]|$)/g, label: "那个" },
  { pattern: /\byou know\b/gi, label: "you know" },
];

function cleanStageDirectionSpans(line: string): { nextLine: string; changes: CleanupChange[] } {
  const changes: CleanupChange[] = [];
  const nextLine = line.replace(new RegExp(STAGE_DIRECTION_SPAN_PATTERN.source, "g"), (match) => {
    if (!isStageDirectionSpan(match)) return match;
    changes.push({
      description: "Remove stage direction or production note",
      before: match,
      after: "",
    });
    return "";
  });

  if (changes.length === 0) {
    return { nextLine: line, changes };
  }

  const leadingWhitespace = nextLine.match(/^\s*/)?.[0] ?? "";
  const body = nextLine.slice(leadingWhitespace.length).replace(/[ \t]{2,}/g, " ").trimEnd();
  return {
    nextLine: `${leadingWhitespace}${body}`,
    changes,
  };
}

function cleanLineStructure(line: string): { nextLine: string; changes: CleanupChange[] } {
  const changes: CleanupChange[] = [];
  let current = line;

  const strippedSpeaker = stripSpeakerLabelLine(current);
  if (strippedSpeaker !== null) {
    changes.push({
      description: "Remove speaker label prefix",
      before: current,
      after: strippedSpeaker,
    });
    current = strippedSpeaker;
  }

  const headingMatch = current.match(MARKDOWN_HEADING_PATTERN);
  if (headingMatch) {
    const nextLine = `${headingMatch[1] ?? ""}${headingMatch[2] ?? ""}`;
    changes.push({
      description: "Remove markdown heading prefix",
      before: current,
      after: nextLine,
    });
    current = nextLine;
  }

  const listMatch = current.match(MARKDOWN_LIST_PATTERN);
  if (listMatch) {
    const nextLine = `${listMatch[1] ?? ""}${listMatch[3] ?? ""}`;
    changes.push({
      description: "Remove markdown list prefix",
      before: current,
      after: nextLine,
    });
    current = nextLine;
  }

  const quoteMatch = current.match(MARKDOWN_QUOTE_PATTERN);
  if (quoteMatch) {
    const nextLine = `${quoteMatch[1] ?? ""}${quoteMatch[2] ?? ""}`;
    changes.push({
      description: "Remove markdown quote prefix",
      before: current,
      after: nextLine,
    });
    current = nextLine;
  }

  if (MARKDOWN_RULE_PATTERN.test(current.trim())) {
    changes.push({
      description: "Remove horizontal rule line",
      before: current,
      after: "",
    });
    return { nextLine: "", changes };
  }

  const stageCleanup = cleanStageDirectionSpans(current);
  changes.push(...stageCleanup.changes);
  current = stageCleanup.nextLine;

  return { nextLine: current, changes };
}

function cleanFillerWords(text: string): { nextText: string; changes: CleanupChange[] } {
  const changes: CleanupChange[] = [];
  let current = text;

  FILLER_REPLACERS.forEach(({ pattern, label }) => {
    if (!pattern.test(current)) {
      pattern.lastIndex = 0;
      return;
    }
    pattern.lastIndex = 0;
    const nextText = current.replace(pattern, (match) => {
      changes.push({
        description: `Remove filler "${label}"`,
        before: match,
        after: "",
      });
      return "";
    });
    current = nextText.replace(/[ \t]{2,}/g, " ").replace(/([，。！？；、])\1+/g, "$1");
  });

  return { nextText: current, changes };
}

function normalizeBlankLines(text: string): string {
  return text
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+$/gm, "");
}

export function buildScriptCleanupPreview(text: string): CleanupPreview {
  const changes: CleanupChange[] = [];
  const cleanedLines: string[] = [];

  text.split("\n").forEach((line) => {
    const { nextLine, changes: lineChanges } = cleanLineStructure(line);
    changes.push(...lineChanges);
    if (nextLine.trim().length > 0 || line.trim().length === 0) {
      cleanedLines.push(nextLine);
    } else if (lineChanges.length > 0) {
      cleanedLines.push("");
    } else {
      cleanedLines.push(line);
    }
  });

  let cleaned = normalizeBlankLines(cleanedLines.join("\n"));
  const fillerCleanup = cleanFillerWords(cleaned);
  cleaned = normalizeBlankLines(fillerCleanup.nextText);
  changes.push(...fillerCleanup.changes);

  return {
    cleaned,
    changes,
    hasChanges: cleaned !== text && changes.length > 0,
  };
}

export function applyScriptCleanup(text: string): string {
  return buildScriptCleanupPreview(text).cleaned;
}
