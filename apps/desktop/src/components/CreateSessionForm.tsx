import { FormEvent, useState } from "react";

type Props = {
  onCreate: (input: { topic: string; creationIntent: string }) => Promise<void>;
};

export function CreateSessionForm({ onCreate }: Props) {
  const [topic, setTopic] = useState("");
  const [creationIntent, setCreationIntent] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!topic.trim() || !creationIntent.trim()) {
      return;
    }
    await onCreate({
      topic: topic.trim(),
      creationIntent: creationIntent.trim(),
    });
    setTopic("");
    setCreationIntent("");
  }

  return (
    <form className="panel create-session" onSubmit={handleSubmit}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Create</p>
          <h2>New Session</h2>
        </div>
        <p>Start from a topic and intent, then let the interview loop do the rest.</p>
      </div>
      <label className="field">
        <span>Topic</span>
        <input
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder="Why local-first tooling matters"
        />
      </label>
      <label className="field">
        <span>Creation Intent</span>
        <textarea
          value={creationIntent}
          onChange={(event) => setCreationIntent(event.target.value)}
          placeholder="Turn a bootstrap lesson into a clear solo monologue."
          rows={3}
        />
      </label>
      <button className="primary-button" type="submit">
        Create Session
      </button>
    </form>
  );
}
