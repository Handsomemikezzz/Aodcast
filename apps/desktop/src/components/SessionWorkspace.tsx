import { useEffect, useState } from "react";

import { DesktopBridge } from "../lib/desktopBridge";
import { formatTimestamp } from "../lib/time";
import {
  AudioRenderResult,
  GenerationResult,
  InterviewTurnResult,
  SessionProject,
  TTSCapability,
} from "../types";
import { StatusBadge } from "./StatusBadge";

type Props = {
  bridge: DesktopBridge;
  project: SessionProject | null;
  onProjectChange: (project: SessionProject) => void;
};

export function SessionWorkspace({ bridge, project, onProjectChange }: Props) {
  const [reply, setReply] = useState("");
  const [draftText, setDraftText] = useState("");
  const [activityNote, setActivityNote] = useState("Select a session to begin.");
  const [localCapability, setLocalCapability] = useState<TTSCapability | null>(null);

  useEffect(() => {
    setDraftText(project?.script?.final || project?.script?.draft || "");
    if (project) {
      setActivityNote("Session loaded.");
    }
  }, [project?.session.session_id, project?.script?.draft, project?.script?.final]);

  useEffect(() => {
    void bridge.getLocalTTSCapability().then(setLocalCapability);
  }, [bridge]);

  if (!project) {
    return (
      <section className="panel workspace-empty">
        <h2>No Session Selected</h2>
        <p>Create a session from the left rail or select one of the seeded examples.</p>
      </section>
    );
  }

  const currentProject = project;

  async function runAction(
    action: () => Promise<InterviewTurnResult | GenerationResult | AudioRenderResult | SessionProject>,
  ) {
    const result = await action();
    if ("project" in result) {
      onProjectChange(result.project);
      if ("provider" in result && !("audio_path" in result)) {
        setDraftText(result.project.script?.final || result.project.script?.draft || "");
      }
    } else {
      onProjectChange(result);
      setDraftText(result.script?.final || result.script?.draft || "");
    }
  }

  async function handleStartInterview() {
    await runAction(() => bridge.startInterview(currentProject.session.session_id));
    setActivityNote("Interview started.");
  }

  async function handleReply(userRequestedFinish = false) {
    if (!reply.trim()) {
      return;
    }
    await runAction(() =>
      bridge.submitReply(currentProject.session.session_id, reply.trim(), userRequestedFinish),
    );
    setReply("");
    setActivityNote(
      userRequestedFinish ? "User requested generation." : "Interview turn submitted.",
    );
  }

  async function handleFinish() {
    await runAction(() => bridge.requestFinish(currentProject.session.session_id));
    setActivityNote("Session marked ready to generate.");
  }

  async function handleGenerateScript() {
    await runAction(() => bridge.generateScript(currentProject.session.session_id));
    setActivityNote("Draft generated.");
  }

  async function handleSaveDraft() {
    await runAction(() => bridge.saveEditedScript(currentProject.session.session_id, draftText));
    setActivityNote("Edited script saved.");
  }

  async function handleRenderAudio() {
    await runAction(() => bridge.renderAudio(currentProject.session.session_id));
    setActivityNote("Audio rendered.");
  }

  const turns = currentProject.transcript?.turns ?? [];
  const canStartInterview = turns.length === 0;
  const canGenerate =
    currentProject.session.state === "ready_to_generate" || currentProject.session.state === "failed";
  const canEdit =
    currentProject.session.state === "script_generated" ||
    currentProject.session.state === "script_edited";
  const canRenderAudio = canEdit || currentProject.session.state === "failed";

  return (
    <section className="workspace">
      <div className="panel session-overview">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Session</p>
            <h2>{currentProject.session.topic}</h2>
          </div>
          <StatusBadge state={currentProject.session.state} />
        </div>
        <p className="session-intent">{currentProject.session.creation_intent}</p>
        <div className="session-meta">
          <span>Updated {formatTimestamp(currentProject.session.updated_at)}</span>
          <span>LLM {currentProject.session.llm_provider || "not selected"}</span>
          <span>{activityNote}</span>
        </div>
        {currentProject.session.last_error ? (
          <div className="error-banner">{currentProject.session.last_error}</div>
        ) : null}
      </div>

      <div className="workspace-grid">
        <section className="panel interview-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Interview</p>
              <h2>Capture Raw Material</h2>
            </div>
            <p>{turns.length} turns</p>
          </div>

          <div className="transcript-list">
            {turns.length === 0 ? (
              <p className="muted-text">No interview turns yet. Start the interview to get the first question.</p>
            ) : (
              turns.map((turn) => (
                <article className={`transcript-turn transcript-${turn.speaker}`} key={`${turn.created_at}-${turn.content}`}>
                  <div className="transcript-turn-header">
                    <strong>{turn.speaker === "agent" ? "Interviewer" : "User"}</strong>
                    <span>{formatTimestamp(turn.created_at)}</span>
                  </div>
                  <p>{turn.content}</p>
                </article>
              ))
            )}
          </div>

          <div className="interview-actions">
            {canStartInterview ? (
              <button className="primary-button" onClick={handleStartInterview} type="button">
                Start Interview
              </button>
            ) : null}
            <textarea
              value={reply}
              onChange={(event) => setReply(event.target.value)}
              placeholder="Write the next answer in your own words."
              rows={4}
            />
            <div className="button-row">
              <button className="primary-button" onClick={() => handleReply(false)} type="button">
                Submit Answer
              </button>
              <button className="ghost-button" onClick={() => handleReply(true)} type="button">
                Submit And Finish
              </button>
              <button className="ghost-button" onClick={handleFinish} type="button">
                Finish Without Reply
              </button>
            </div>
          </div>
        </section>

        <section className="panel script-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Draft</p>
              <h2>Review And Edit</h2>
            </div>
            <p>{currentProject.script?.draft ? "Draft available" : "Waiting for generation"}</p>
          </div>

          <div className="draft-summary">
            <div>
              <h3>Generation Gate</h3>
              <p>
                Draft generation unlocks when the session reaches{" "}
                <code>ready_to_generate</code>.
              </p>
            </div>
            <button
              className="primary-button"
              disabled={!canGenerate}
              onClick={handleGenerateScript}
              type="button"
            >
              Generate Draft
            </button>
          </div>

          <label className="field">
            <span>Editable Script</span>
            <textarea
              className="draft-editor"
              value={draftText}
              onChange={(event) => setDraftText(event.target.value)}
              placeholder="Generated draft will appear here."
              rows={16}
            />
          </label>

          <div className="button-row">
            <button
              className="primary-button"
              disabled={!canEdit && !draftText.trim()}
              onClick={handleSaveDraft}
              type="button"
            >
              Save Edited Script
            </button>
            <span className="muted-text">
              {currentProject.script?.updated_at
                ? `Script updated ${formatTimestamp(currentProject.script.updated_at)}`
                : "No script saved yet."}
            </span>
          </div>

          <div className="artifact-box">
            <div>
              <h3>Final Audio</h3>
              <p>
                Render the current final script into an audio artifact once the
                draft is ready.
              </p>
            </div>
            <div className="button-row">
              <button
                className="primary-button"
                disabled={!canRenderAudio}
                onClick={handleRenderAudio}
                type="button"
              >
                Render Audio
              </button>
              <span className="muted-text">
                TTS {currentProject.session.tts_provider || "not selected"}
              </span>
            </div>
            <div className="artifact-list">
              <div>
                <strong>Transcript</strong>
                <p>{currentProject.artifact?.transcript_path || "Not generated yet."}</p>
              </div>
              <div>
                <strong>Audio</strong>
                <p>{currentProject.artifact?.audio_path || "Not generated yet."}</p>
              </div>
            </div>
            {localCapability ? (
              <div className="capability-box">
                <div>
                  <strong>Local MLX Capability</strong>
                  <p>
                    {localCapability.available
                      ? "Local MLX TTS is available."
                      : `Local MLX TTS unavailable. Fallback provider: ${localCapability.fallback_provider}.`}
                  </p>
                </div>
                {!localCapability.available ? (
                  <ul className="capability-list">
                    {localCapability.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </section>
  );
}
