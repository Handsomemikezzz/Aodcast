import {
  ArtifactRecord,
  ScriptRecord,
  SessionProject,
  SessionRecord,
  TranscriptRecord,
} from "../types";

function session(
  overrides: Partial<SessionRecord> & Pick<SessionRecord, "session_id" | "topic" | "creation_intent" | "state">,
): SessionRecord {
  const now = new Date().toISOString();
  return {
    llm_provider: "",
    tts_provider: "",
    last_error: "",
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function transcript(sessionId: string, turns: TranscriptRecord["turns"]): TranscriptRecord {
  return {
    session_id: sessionId,
    turns,
  };
}

function script(sessionId: string, draft: string, finalText = ""): ScriptRecord {
  const now = new Date().toISOString();
  return {
    session_id: sessionId,
    script_id: "00000000-0000-4000-8000-000000000001",
    name: "Mock script",
    draft,
    final: finalText,
    created_at: now,
    updated_at: now,
  };
}

function artifact(sessionId: string): ArtifactRecord {
  return {
    session_id: sessionId,
    transcript_path: `sessions/${sessionId}/transcript.json`,
    audio_path: "",
    provider: "",
    created_at: new Date().toISOString(),
  };
}

export const seededProjects: SessionProject[] = [
  {
    session: session({
      session_id: "session-in-flight",
      topic: "Maintaining agent-owned repositories",
      creation_intent: "Find the one lesson worth turning into an episode",
      state: "interview_in_progress",
      updated_at: "2026-03-28T02:28:00.000Z",
    }),
    transcript: transcript("session-in-flight", [
      {
        speaker: "agent",
        content: "What made this topic feel important enough to turn into an episode?",
        created_at: "2026-03-28T02:27:00.000Z",
      },
      {
        speaker: "user",
        content:
          "I think agent-owned repos drift fast unless somebody actively curates contracts and docs.",
        created_at: "2026-03-28T02:27:45.000Z",
      },
      {
        speaker: "agent",
        content:
          "Can you give me one concrete example of that drift showing up in practice?",
        created_at: "2026-03-28T02:28:00.000Z",
      },
    ]),
    script: script("session-in-flight", ""),
    artifact: artifact("session-in-flight"),
  },
  {
    session: session({
      session_id: "session-draft",
      topic: "Why local-first scaffolding matters",
      creation_intent: "Turn a bootstrap lesson into a solo monologue draft",
      state: "script_generated",
      llm_provider: "mock",
      updated_at: "2026-03-28T02:31:00.000Z",
    }),
    transcript: transcript("session-draft", [
      {
        speaker: "agent",
        content: "What prompted this topic for you right now?",
        created_at: "2026-03-28T02:29:10.000Z",
      },
      {
        speaker: "user",
        content:
          "I think local-first scaffolding matters because it lets teams validate the workflow before cloud dependencies exist. For example, this week I used a mock provider to prove the script path, and the takeaway is that reliability has to come before polish.",
        created_at: "2026-03-28T02:30:40.000Z",
      },
    ]),
    script: script(
      "session-draft",
      "Opening\n\nToday I want to talk about why local-first scaffolding matters before the rest of the platform is finished.\n\nBody\n\nWhen a project depends on many moving parts, the safest way to move fast is to prove the workflow end to end with the smallest dependable pieces.\n\nClosing\n\nThe takeaway is simple: build the path that lets the team recover before you build the path that only looks impressive.",
      "Opening\n\nToday I want to talk about why local-first scaffolding matters before the rest of the platform is finished.\n\nBody\n\nWhen a project depends on many moving parts, the safest way to move fast is to prove the workflow end to end with the smallest dependable pieces.\n\nClosing\n\nThe takeaway is simple: build the path that lets the team recover before you build the path that only looks impressive.",
    ),
    artifact: artifact("session-draft"),
  },
];
