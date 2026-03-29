import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronRight, Edit3, Mic } from "lucide-react";
import { SessionProject } from "../types";
import { cn } from "../lib/utils";
import { EditPage } from "./EditPage";
import { GeneratePage } from "./GeneratePage";

type TabId = "edit" | "audio";

export function ScriptPage({
  projects,
  onRefresh,
}: {
  projects: SessionProject[];
  onRefresh: () => Promise<void>;
}) {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabId>("edit");

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
              Open a podcast to edit its script or generate speech with TTS.
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
                  onClick={() => navigate(`/script/${p.session.session_id}`)}
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

  return (
    <div className="flex flex-col h-full w-full min-h-0">
      <div className="shrink-0 flex items-center gap-1 px-4 py-2 border-b border-outline bg-background/80">
        <button
          type="button"
          onClick={() => setTab("edit")}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors",
            tab === "edit"
              ? "bg-primary/10 text-primary"
              : "text-secondary hover:bg-surface-container-high hover:text-primary",
          )}
        >
          <Edit3 className="w-3.5 h-3.5" />
          Edit script
        </button>
        <button
          type="button"
          onClick={() => setTab("audio")}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors",
            tab === "audio"
              ? "bg-primary/10 text-primary"
              : "text-secondary hover:bg-surface-container-high hover:text-primary",
          )}
        >
          <Mic className="w-3.5 h-3.5" />
          Text to speech
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === "edit" ? <EditPage onRefresh={onRefresh} /> : <GeneratePage onRefresh={onRefresh} />}
      </div>
    </div>
  );
}
