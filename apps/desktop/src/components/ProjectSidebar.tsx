import { formatTimestamp } from "../lib/time";
import { SessionProject } from "../types";
import { StatusBadge } from "./StatusBadge";

type Props = {
  projects: SessionProject[];
  selectedId: string | null;
  onSelect: (sessionId: string) => void;
};

export function ProjectSidebar({ projects, selectedId, onSelect }: Props) {
  return (
    <aside className="sidebar panel">
      <div className="sidebar-header">
        <div>
          <p className="eyebrow">Workspace</p>
          <h2>Sessions</h2>
        </div>
        <p>{projects.length} tracked</p>
      </div>
      <div className="session-list">
        {projects.map((project) => (
          <button
            className={`session-card${selectedId === project.session.session_id ? " session-card-active" : ""}`}
            key={project.session.session_id}
            onClick={() => onSelect(project.session.session_id)}
            type="button"
          >
            <div className="session-card-row">
              <h3>{project.session.topic}</h3>
              <StatusBadge state={project.session.state} />
            </div>
            <p>{project.session.creation_intent}</p>
            <span>Updated {formatTimestamp(project.session.updated_at)}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
