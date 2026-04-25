import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { SessionProject } from "../types";
import { useBridge } from "../lib/BridgeContext";
import { ScriptWorkbench } from "./ScriptWorkbench";

export function ScriptPage({
  projects,
  onRefresh,
}: {
  projects: SessionProject[];
  onRefresh: () => Promise<void>;
}) {
  const { sessionId, scriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  const navigate = useNavigate();
  const bridge = useBridge();
  const handleOpenLatestScript = async (targetSessionId: string) => {
    try {
      const project = await bridge.showLatestScript(targetSessionId);
      if (project.script?.script_id) {
        navigate(`/script/${targetSessionId}/${project.script.script_id}`);
        return;
      }
    } catch {
      // Fall through to the session-level route when no latest script is available.
    }
    navigate(`/script/${targetSessionId}`);
  };

  const sorted = [...projects].sort((a, b) =>
    b.session.updated_at.localeCompare(a.session.updated_at),
  );

  if (!sessionId) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col h-full w-full overflow-y-auto px-6 lg:px-12 py-8"
      >
        <div className="max-w-2xl mx-auto w-full">
          <div className="mb-8 border-b border-outline pb-6">
            <h1 className="text-2xl font-headline font-bold text-primary mb-2">Script</h1>
            <p className="text-secondary text-sm">
              Open a podcast to edit the script and render audio inside one workspace.
            </p>
          </div>
          <div className="rounded-xl border border-outline bg-surface-container-low overflow-hidden divide-y divide-outline-variant">
            {sorted.length === 0 ? (
              <div className="p-8 text-center text-secondary text-sm">
                No sessions yet. Start a chat to create one.
              </div>
            ) : (
              sorted.map((p) => (
                <button
                  key={p.session.session_id}
                  type="button"
                  onClick={() => void handleOpenLatestScript(p.session.session_id)}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-container transition-colors"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-[14px] text-primary truncate">
                      {p.session.topic || "Untitled"}
                    </p>
                    <p className="text-[12px] text-secondary truncate">{p.session.state.replace(/_/g, " ")}</p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-outline shrink-0" />
                </button>
              ))
            )}
          </div>
        </div>
      </motion.div>
    );
  }

  if (!scriptId) {
    return (
      <div className="flex h-full items-center justify-center text-secondary text-sm">
        Missing script id. Use the script list or open from chat.
      </div>
    );
  }

  return <ScriptWorkbench key={`${sessionId}-${scriptId}`} sessionId={sessionId} scriptId={scriptId} onRefresh={onRefresh} />;
}
