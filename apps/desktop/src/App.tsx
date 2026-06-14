import { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, NavLink, useNavigate, useLocation, Navigate, useParams } from "react-router-dom";
import { useBridge } from "./lib/BridgeContext";
import { SessionProject } from "./types";
import { cn } from "./lib/utils";

import { ScriptSessionResolve } from "./pages/ScriptSessionResolve";
import { List, Layers, Mic, Package, Settings } from "lucide-react";
import { HTTP_BACKEND_UNAVAILABLE } from "./lib/httpBridge";

const ChatPage = lazy(() => import("./pages/ChatPage").then((module) => ({ default: module.ChatPage })));
const ScriptPage = lazy(() => import("./pages/ScriptPage").then((module) => ({ default: module.ScriptPage })));
const ModelsPage = lazy(() => import("./pages/ModelsPage").then((module) => ({ default: module.ModelsPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const VoiceStudioPage = lazy(() => import("./pages/VoiceStudioPage").then((module) => ({ default: module.VoiceStudioPage })));
const EpisodesPage = lazy(() => import("./pages/EpisodesPage").then((module) => ({ default: module.EpisodesPage })));
const StudioPage = lazy(() => import("./pages/studio/StudioPage").then((module) => ({ default: module.StudioPage })));

function RouteFallback() {
  return <div className="flex h-full items-center justify-center text-secondary text-sm">Loading workspace…</div>;
}

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

// Compatibility redirects for old routes → studio
function RedirectChatToStudio() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  if (sessionId) return <Navigate to={`/studio/${sessionId}?panel=conversation`} replace />;
  return <Navigate to="/episodes" replace />;
}

function RedirectScriptToStudio() {
  const { sessionId, scriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  if (sessionId && scriptId) return <Navigate to={`/studio/${sessionId}/${scriptId}?focus=script`} replace />;
  if (sessionId) return <Navigate to={`/studio/${sessionId}`} replace />;
  return <Navigate to="/episodes" replace />;
}

function RedirectVoiceStudioToStudio() {
  const { sessionId, scriptId } = useParams<{ sessionId?: string; scriptId?: string }>();
  if (sessionId && scriptId) return <Navigate to={`/studio/${sessionId}/${scriptId}?panel=voice`} replace />;
  return <Navigate to="/voice-studio" replace />;
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
    urlSessionId && (pathSegment === "chat" || pathSegment === "script" || pathSegment === "studio")
      ? projects.find((p) => p.session.session_id === urlSessionId)
      : undefined;

  let title = "Aodcast";
  if (pathSegment === "models") title = "Models";
  else if (pathSegment === "settings") title = "Settings";
  else if (pathSegment === "voice-studio") title = "Voice Library";
  else if (pathSegment === "episodes") title = "Episodes";
  else if (pathSegment === "studio" && !urlSessionId) title = "Studio";
  else if (pathSegment === "chat" && !urlSessionId) title = "Chat";
  else if (pathSegment === "script" && !urlSessionId) title = "Script";
  else if (currentProject) title = currentProject.session.topic;

  const navItemClass = (active: boolean) =>
    cn(
      "w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all duration-200 text-[13px] font-medium border border-transparent select-none",
      active
        ? "bg-accent-amber/8 border-accent-amber/25 text-[#f5c669] shadow-[inset_0_1px_0_rgba(255,255,255,0.02),0_4px_12px_rgba(0,0,0,0.15)]"
        : "text-secondary hover:bg-white/5 hover:text-white",
    );

  return (
    <div className="flex h-screen w-full bg-background text-on-surface overflow-hidden selection:bg-accent-amber/30 font-body mac-scrollbar">
      <aside className="w-[240px] flex-shrink-0 flex flex-col bg-[#141416]/90 border-r border-white/5 backdrop-blur-2xl shadow-lg relative">
        {/* Brand spacing accommodating macOS traffic lights */}
        <div className="h-[74px] flex items-end pb-3 px-5 drag-region select-none">
          <div className="flex items-center gap-2.5 text-accent-amber">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-b from-[#f2bf57] to-[#d79b2f] shadow-md shadow-accent-amber/15">
              <Mic className="w-4.5 h-4.5 text-black fill-black" />
            </div>
            <span className="font-headline font-bold text-[16px] tracking-[0.05em] text-white">Aodcast</span>
          </div>
        </div>

        <nav className="px-3.5 py-2.5 space-y-1.5 mt-2">
          <NavLink
            to="/episodes"
            className={({ isActive }) => navItemClass(isActive)}
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <List className="w-4 h-4" />
            </div>
            Episodes
          </NavLink>

          <NavLink
            to="/studio"
            className={({ isActive }) =>
              navItemClass(isActive || location.pathname.startsWith("/studio/"))
            }
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <Layers className="w-4 h-4" />
            </div>
            Studio
          </NavLink>

          <NavLink
            to="/models"
            className={({ isActive }) => navItemClass(isActive)}
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <Package className="w-4 h-4" />
            </div>
            Models
          </NavLink>
        </nav>

        <div className="flex-1 min-h-0" aria-hidden />

        <div className="p-3.5 border-t border-white/5 shrink-0">
          <button
            type="button"
            onClick={() => navigate("/settings")}
            className={navItemClass(pathSegment === "settings")}
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <Settings className="w-4 h-4" />
            </div>
            Settings
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 bg-background relative">
        <header className="h-[74px] flex items-end pb-3 px-6 border-b border-white/5 bg-[rgba(15,15,17,0.85)] backdrop-blur-xl drag-region shrink-0 shadow-[0_1px_0_rgba(255,255,255,0.01)]">
          <div className="flex items-center gap-3 min-w-0">
            <h2 className="font-headline font-semibold text-[15px] tracking-wide text-white truncate">{title}</h2>
            {currentProject && (
              <span className="shrink-0 px-2 py-0.5 rounded-full text-[9px] font-headline font-semibold bg-white/5 border border-white/10 text-accent-amber uppercase tracking-wider">
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
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              {/* Primary destinations */}
              <Route path="/" element={<Navigate to="/episodes" replace />} />
              <Route path="/episodes" element={<EpisodesPage projects={projects} onRefresh={fetchProjects} />} />
              <Route path="/studio" element={<Navigate to="/episodes" replace />} />
              <Route path="/studio/:sessionId" element={<StudioPage onRefresh={fetchProjects} />} />
              <Route path="/studio/:sessionId/:scriptId" element={<StudioPage onRefresh={fetchProjects} />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/voice-studio" element={<VoiceStudioPage />} />
              <Route path="/voice-studio/:sessionId/:scriptId" element={<VoiceStudioPage />} />
              <Route path="/settings" element={<SettingsPage />} />

              {/* Legacy routes kept as compatibility redirects */}
              <Route path="/history" element={<Navigate to="/episodes" replace />} />
              <Route path="/chat" element={<RedirectChatToStudio />} />
              <Route path="/chat/:sessionId" element={<RedirectChatToStudio />} />
              <Route path="/script" element={<Navigate to="/episodes" replace />} />
              <Route path="/script/:sessionId/:scriptId" element={<RedirectScriptToStudio />} />
              <Route path="/script/:sessionId" element={<ScriptSessionResolve />} />
              <Route path="/interview" element={<RedirectInterviewToChat />} />
              <Route path="/interview/:sessionId" element={<RedirectInterviewToChat />} />
              <Route path="/voice" element={<RedirectVoiceOrExportToScript />} />
              <Route path="/voice/:sessionId" element={<RedirectVoiceOrExportToScript />} />
              <Route path="/export" element={<RedirectVoiceOrExportToScript />} />
              <Route path="/export/:sessionId" element={<RedirectVoiceOrExportToScript />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  );
}
