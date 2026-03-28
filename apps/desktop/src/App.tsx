type Milestone = {
  title: string;
  status: "done" | "in_progress" | "pending" | "blocked";
  note: string;
};

const milestones: Milestone[] = [
  {
    title: "Repository bootstrap",
    status: "in_progress",
    note: "Desktop and Python scaffolds are being initialized.",
  },
  {
    title: "Session contracts",
    status: "in_progress",
    note: "Shared schemas and local persistence are being defined.",
  },
  {
    title: "Interview orchestration",
    status: "pending",
    note: "State machine and prompt assembly will land after storage contracts stabilize.",
  },
  {
    title: "Audio output",
    status: "pending",
    note: "Remote TTS and local MLX-backed TTS follow once the edit flow is stable.",
  },
];

const statusLabel: Record<Milestone["status"], string> = {
  done: "Done",
  in_progress: "In Progress",
  pending: "Pending",
  blocked: "Blocked",
};

export default function App() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">EchoMind Podcast MVP</p>
        <h1>Aodcast</h1>
        <p className="summary">
          A local-first macOS app for turning rough ideas into publishable solo
          podcast scripts and audio through guided interviewing.
        </p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Bootstrap Status</h2>
          <p>
            This screen tracks the bootstrap milestone until the real session
            flow and Python orchestration bridge are wired together.
          </p>
        </div>
        <ul className="milestone-list">
          {milestones.map((item) => (
            <li className="milestone-card" key={item.title}>
              <span className={`status status-${item.status}`}>
                {statusLabel[item.status]}
              </span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.note}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel split-panel">
        <article>
          <h2>MVP Boundaries</h2>
          <ul>
            <li>Text topic input only</li>
            <li>Solo monologue output</li>
            <li>User-configured LLM API</li>
            <li>Remote TTS and local MLX-backed TTS</li>
          </ul>
        </article>
        <article>
          <h2>Current Blocker</h2>
          <p>
            The Rust toolchain is not installed in the current environment, so
            native Tauri boot verification is deferred until `cargo` becomes
            available.
          </p>
        </article>
      </section>
    </main>
  );
}
