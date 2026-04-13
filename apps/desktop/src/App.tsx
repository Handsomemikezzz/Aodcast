import { useEffect, useState } from "react";
import { Routes, Route, NavLink, useNavigate, useLocation, Navigate, useParams } from "react-router-dom";
import { useBridge } from "./lib/BridgeContext";
import { SessionProject } from "./types";
import { cn } from "./lib/utils";

import { ChatPage } from "./pages/ChatPage";
import { ScriptPage } from "./pages/ScriptPage";
import { ModelsPage } from "./pages/ModelsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { MessageSquare, Edit3, Mic, Package, Settings } from "lucide-react";
import { HTTP_BACKEND_UNAVAILABLE } from "./lib/httpBridge";

function RedirectInterviewToChat() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  if (sessionId) return <Navigate to={`/chat/${sessionId}`} replace />;
  return <Navigate to="/chat" replace />;
}

function RedirectVoiceOrExportToScript() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  if (sessionId) return <Navigate to={`/script/${sessionId}`} replace />;
  return <Navigate to="/script" replace />;
}

export default function App() {
  const bridge = useBridge();
  const navigate = useNavigate();
  const location = useLocation();
  const [projects, setProjects] = useState<SessionProject[]>([]);
  const [bridgeError, setBridgeError] = useState<string | null>(null);

  const fetchProjects = async () => {
    try {
      const items = await bridge.listProjects();
      setProjects(items);
      setBridgeError(null);
    } catch (err) {
      setProjects([]);
      setBridgeError(err instanceof Error ? err.message : HTTP_BACKEND_UNAVAILABLE);
    }
  };

  useEffect(() => {
    void fetchProjects();
  }, [bridge]);

  const pathParts = location.pathname.split("/").filter(Boolean);
  const pathSegment = pathParts[0] ?? "";
  const urlSessionId = pathParts.length >= 2 ? pathParts[1] : null;

  const currentProject =
    urlSessionId && (pathSegment === "chat" || pathSegment === "script")
      ? projects.find((p) => p.session.session_id === urlSessionId)
      : undefined;

  let title = "Aodcast";
  if (pathSegment === "models") title = "Models";
  else if (pathSegment === "settings") title = "Settings";
  else if (pathSegment === "chat" && !urlSessionId) title = "Chat";
  else if (pathSegment === "script" && !urlSessionId) title = "Script";
  else if (currentProject) title = currentProject.session.topic;

  return (
    <div className="flex h-screen w-full bg-background text-on-surface overflow-hidden selection:bg-accent-amber/30 font-body mac-scrollbar">
      <aside className="w-[240px] flex-shrink-0 flex flex-col bg-surface border-r border-outline">
        <div className="h-[52px] flex items-center px-4 drag-region">
          <div className="flex items-center gap-2 text-accent-amber pt-2">
            <Mic className="w-5 h-5 fill-accent-amber text-accent-amber" />
            <span className="font-headline font-bold text-[15px] tracking-wide text-primary">Aodcast</span>
          </div>
        </div>

        <nav className="px-3 py-2 space-y-1 mt-2">
          <NavLink
            to="/chat"
            end
            className={({ isActive }) =>
              cn(
                "w-full flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors text-[13px] font-medium",
                isActive || location.pathname.startsWith("/chat/")
                  ? "bg-primary/10 text-primary"
                  : "text-secondary hover:bg-surface-container-high hover:text-primary",
              )
            }
          >
            <div className="w-6 h-6 flex items-center justify-center">
              <MessageSquare className="w-4 h-4" />
            </div>
            Chat
          </NavLink>

          <NavLink
            to="/script"
            end
            className={({ isActive }) =>
              cn(
                "w-full flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors text-[13px] font-medium",
                isActive || location.pathname.startsWith("/script/")
                  ? "bg-primary/10 text-primary"
                  : "text-secondary hover:bg-surface-container-high hover:text-primary",
              )
            }
          >
            <div className="w-6 h-6 flex items-center justify-center">
              <Edit3 className="w-4 h-4" />
            </div>
            Script
          </NavLink>

          <NavLink
            to="/models"
            className={({ isActive }) =>
              cn(
                "w-full flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors text-[13px] font-medium",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-secondary hover:bg-surface-container-high hover:text-primary",
              )
            }
          >
            <div className="w-6 h-6 flex items-center justify-center">
              <Package className="w-4 h-4" />
            </div>
            Models
          </NavLink>
        </nav>

        <div className="flex-1 min-h-0" aria-hidden />

        <div className="p-3 border-t border-outline shrink-0">
          <button
            type="button"
            onClick={() => navigate("/settings")}
            className={cn(
              "w-full flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors text-[13px] font-medium",
              pathSegment === "settings"
                ? "bg-primary/10 text-primary"
                : "text-secondary hover:bg-surface-container-high hover:text-primary",
            )}
          >
            <div className="w-6 h-6 flex items-center justify-center">
              <Settings className="w-4 h-4" />
            </div>
            Settings
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 bg-background relative">
        <header className="h-[52px] flex items-center justify-between px-4 border-b border-outline bg-background/80 backdrop-blur-md drag-region shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <h2 className="font-headline font-semibold text-[14px] text-primary truncate">{title}</h2>
            {currentProject && (
              <span className="shrink-0 px-2 py-0.5 rounded text-[10px] font-medium bg-surface-container border border-outline text-secondary uppercase tracking-wider">
                {currentProject.session.state.replace(/_/g, " ")}
              </span>
            )}
          </div>
        </header>

        {bridgeError ? (
          <div className="shrink-0 px-4 py-2.5 text-[13px] leading-snug bg-amber-500/15 border-b border-amber-500/25 text-amber-100">
            {bridgeError}
          </div>
        ) : null}

        <div className="flex-1 overflow-hidden relative">
          <Routes>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="/history" element={<Navigate to="/chat" replace />} />
            <Route
              path="/chat"
              element={<ChatPage onRefresh={fetchProjects} />}
            />
            <Route
              path="/chat/:sessionId"
              element={<ChatPage onRefresh={fetchProjects} />}
            />
            <Route path="/script" element={<ScriptPage projects={projects} onRefresh={fetchProjects} />} />
            <Route
              path="/script/:sessionId"
              element={<ScriptPage projects={projects} onRefresh={fetchProjects} />}
            />
            <Route path="/models" element={<ModelsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/interview" element={<RedirectInterviewToChat />} />
            <Route path="/interview/:sessionId" element={<RedirectInterviewToChat />} />
            <Route path="/voice" element={<RedirectVoiceOrExportToScript />} />
            <Route path="/voice/:sessionId" element={<RedirectVoiceOrExportToScript />} />
            <Route path="/export" element={<RedirectVoiceOrExportToScript />} />
            <Route path="/export/:sessionId" element={<RedirectVoiceOrExportToScript />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
