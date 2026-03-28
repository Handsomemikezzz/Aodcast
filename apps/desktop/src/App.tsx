import { useEffect, useState } from "react";

import { CreateSessionForm } from "./components/CreateSessionForm";
import { ProjectSidebar } from "./components/ProjectSidebar";
import { SessionWorkspace } from "./components/SessionWorkspace";
import { createMockBridge } from "./lib/mockBridge";
import { SessionProject } from "./types";

export default function App() {
  const [bridge] = useState(() => createMockBridge());
  const [projects, setProjects] = useState<SessionProject[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    void bridge.listProjects().then((items) => {
      setProjects(items);
      setSelectedId((current) => current ?? items[0]?.session.session_id ?? null);
    });
  }, [bridge]);

  async function refreshAndSelect(project: SessionProject) {
    const items = await bridge.listProjects();
    setProjects(items);
    setSelectedId(project.session.session_id);
  }

  async function handleCreate(input: { topic: string; creationIntent: string }) {
    const created = await bridge.createSession(input);
    await refreshAndSelect(created);
  }

  const selectedProject =
    projects.find((project) => project.session.session_id === selectedId) ?? null;

  return (
    <main className="app-shell">
      <ProjectSidebar
        projects={projects}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />

      <section className="content-column">
        <section className="hero">
          <div>
            <p className="eyebrow">EchoMind Podcast MVP</p>
            <h1>Desktop Creation Flow</h1>
          </div>
          <p className="summary">
            The desktop shell now mirrors the core workflow: create a session,
            interview for raw material, move into draft generation, and edit the
            script directly. The current bridge is intentionally mock-backed so
            the UI can stabilize before the real Tauri bridge replaces it.
          </p>
        </section>

        <CreateSessionForm onCreate={handleCreate} />
        <SessionWorkspace
          bridge={bridge}
          project={selectedProject}
          onProjectChange={refreshAndSelect}
        />
      </section>
    </main>
  );
}
