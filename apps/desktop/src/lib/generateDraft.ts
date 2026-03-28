export function generateMockDraft(topic: string, creationIntent: string, transcriptText: string) {
  const lines = transcriptText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const supportingLine = lines.length > 0
    ? lines[lines.length - 1]
    : "The interview transcript is still sparse.";

  return [
    "Opening",
    `Today I want to talk about ${topic.toLowerCase()} and why it matters right now.`,
    "Body",
    `My core intent for this episode is: ${creationIntent}. One useful detail from the interview is: ${supportingLine}`,
    "Closing",
    "If there is one takeaway from this conversation, it is that better tools make complex work more understandable and recoverable.",
  ].join("\n\n");
}
