import { Speaker, TranscriptRecord } from "../types";

export function evaluateReadiness(transcript: TranscriptRecord | null) {
  const userTurns =
    transcript?.turns
      .filter((turn) => turn.speaker === "user")
      .map((turn) => turn.content.trim().toLowerCase())
      .filter(Boolean) ?? [];
  const combined = userTurns.join("\n");

  const topic_context =
    userTurns.length >= 1 && userTurns.some((turn) => turn.split(/\s+/).length >= 8);
  const core_viewpoint = containsKeyword(combined, [
    "i think",
    "i believe",
    "my view",
    "because",
    "important",
    "what matters",
    "i realized",
  ]);
  const example_or_detail = containsKeyword(combined, [
    "for example",
    "for instance",
    "when i",
    "last week",
    "specifically",
    "in practice",
    "example",
  ]);
  const conclusion = containsKeyword(combined, [
    "the takeaway",
    "overall",
    "in the end",
    "that means",
    "therefore",
    "what i want people to know",
  ]);

  const missing_dimensions = [
    !topic_context && "topic_context",
    !core_viewpoint && "core_viewpoint",
    !example_or_detail && "example_or_detail",
    !conclusion && "conclusion",
  ].filter(Boolean) as string[];

  return {
    topic_context,
    core_viewpoint,
    example_or_detail,
    conclusion,
    is_ready:
      topic_context && core_viewpoint && example_or_detail && conclusion,
    missing_dimensions,
  };
}

function containsKeyword(text: string, keywords: string[]): boolean {
  return keywords.some((keyword) => text.includes(keyword));
}

export function nextQuestion(topic: string, missingDimensions: string[]): string {
  const focus = missingDimensions[0] ?? "ready_to_generate";

  switch (focus) {
    case "topic_context":
      return `You want to turn "${topic}" into a podcast. What prompted this topic for you right now?`;
    case "core_viewpoint":
      return "What is the main thing you believe or want to argue about this topic?";
    case "example_or_detail":
      return "Can you give me one concrete example, story, or detail that makes this point feel real?";
    case "conclusion":
      return "If listeners remember one takeaway from this episode, what should it be?";
    default:
      return "I have enough material to draft the episode. If you want, we can move to script generation.";
  }
}

export function transcriptToText(transcript: TranscriptRecord | null): string {
  return (
    transcript?.turns
      .map((turn) => `${turn.speaker}: ${turn.content}`)
      .join("\n") ?? ""
  );
}

export function appendTurn(
  transcript: TranscriptRecord,
  speaker: Speaker,
  content: string,
  createdAt: string,
): TranscriptRecord {
  return {
    ...transcript,
    turns: [...transcript.turns, { speaker, content, created_at: createdAt }],
  };
}
