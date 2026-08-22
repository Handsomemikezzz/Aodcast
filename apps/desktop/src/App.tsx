import { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, NavLink, useNavigate, useLocation, Navigate } from "react-router-dom";
import { useBridge } from "./lib/BridgeContext";
import { SessionProject } from "./types";
import { cn } from "./lib/utils";
import { List, Mic, AudioLines, Package, Settings, Sun, Moon, Brain } from "lucide-react";
import { HTTP_BACKEND_UNAVAILABLE } from "./lib/httpBridge";
import { applyTheme, readStoredTheme, type AppTheme } from "./lib/theme";

const ChatPage = lazy(() => import("./pages/ChatPage").then((module) => ({ default: module.ChatPage })));
const ModelsPage = lazy(() => import("./pages/ModelsPage").then((module) => ({ default: module.ModelsPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const VoiceStudioPage = lazy(() => import("./pages/VoiceStudioPage").then((module) => ({ default: module.VoiceStudioPage })));
const EpisodesPage = lazy(() => import("./pages/EpisodesPage").then((module) => ({ default: module.EpisodesPage })));
const StudioPage = lazy(() => import("./pages/studio/StudioPage").then((module) => ({ default: module.StudioPage })));
const MemoryPage = lazy(() => import("./pages/MemoryPage").then((module) => ({ default: module.MemoryPage })));
const NewEpisodePage = lazy(() => import("./pages/NewEpisodePage").then((module) => ({ default: module.NewEpisodePage })));

function RouteFallback() {
  return <div className="flex h-full items-center justify-center text-secondary text-sm">Loading workspace…</div>;
}

export default function App() {
  const bridge = useBridge();
  const navigate = useNavigate();
  const location = useLocation();
  const [projects, setProjects] = useState<SessionProject[]>([]);
  const [bridgeError, setBridgeError] = useState<string | null>(null);

  const [theme, setTheme] = useState<AppTheme>(() => readStoredTheme());

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

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

  let title = "Aodcast";
  if (pathSegment === "models") title = "Models";
  else if (pathSegment === "settings") title = "Settings";
  else if (pathSegment === "voice-studio") title = "Voice";
  else if (pathSegment === "memory") title = "Memory";
  else if (pathSegment === "episodes") title = "Episodes";
  else if (pathSegment === "studio") title = "Episode Workspace";
  else if (pathSegment === "chat") title = "New Episode";

  const navItemClass = (active: boolean) =>
    cn(
      "w-full flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all duration-200 text-[13px] font-medium border border-transparent select-none",
      active
        ? "bg-accent-amber/8 border-accent-amber/25 text-accent-amber shadow-[inset_0_1px_0_rgba(255,255,255,0.02),0_4px_12px_rgba(0,0,0,0.15)]"
        : "text-secondary hover:bg-primary/5 hover:text-primary",
    );

  return (
    <div className="flex h-screen w-full bg-background text-on-surface overflow-hidden selection:bg-accent-amber/30 font-body mac-scrollbar">
      <aside className="flex w-[72px] lg:w-[240px] flex-shrink-0 flex-col bg-surface-container-low/95 border-r border-outline backdrop-blur-2xl shadow-lg relative transition-[width] duration-200">
        {/* Brand spacing accommodating macOS traffic lights */}
        <div className="h-[74px] flex items-end pb-3 px-5 drag-region select-none">
          <div className="flex items-center gap-2.5 text-accent-amber">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg theme-accent-gradient shadow-md shadow-accent-amber/15">
              <Mic className="w-4.5 h-4.5 text-on-primary fill-on-primary" />
            </div>
            <span className="hidden lg:inline font-headline font-bold text-[16px] tracking-[0.05em] text-primary">Aodcast</span>
          </div>
        </div>

        <nav className="px-3.5 py-2.5 space-y-1.5 mt-2">
          <NavLink
            to="/episodes"
            title="Episodes"
            className={({ isActive }) => navItemClass(
              isActive || location.pathname.startsWith("/studio/") || location.pathname === "/chat",
            )}
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <List className="w-4 h-4" />
            </div>
            <span className="hidden lg:inline">Episodes</span>
          </NavLink>

          <NavLink
            to="/voice-studio"
            title="Voice"
            className={({ isActive }) =>
              navItemClass(isActive || location.pathname.startsWith("/voice-studio"))
            }
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <AudioLines className="w-4 h-4" />
            </div>
            <span className="hidden lg:inline">Voice</span>
          </NavLink>

          <NavLink
            to="/models"
            title="Models"
            className={({ isActive }) => navItemClass(isActive)}
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <Package className="w-4 h-4" />
            </div>
            <span className="hidden lg:inline">Models</span>
          </NavLink>

          <NavLink
            to="/memory"
            title="Memory"
            className={({ isActive }) => navItemClass(isActive)}
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <Brain className="w-4 h-4" />
            </div>
            <span className="hidden lg:inline">Memory</span>
          </NavLink>
        </nav>

        <div className="flex-1 min-h-0" aria-hidden />

        <div className="p-3.5 border-t border-outline shrink-0 flex flex-col lg:flex-row items-center gap-2">
          <button
            type="button"
            onClick={() => navigate("/settings")}
            className={cn(navItemClass(pathSegment === "settings"), "lg:flex-1")}
            title="Settings"
          >
            <div className="w-5 h-5 flex items-center justify-center shrink-0">
              <Settings className="w-4 h-4" />
            </div>
            <span className="hidden lg:inline">Settings</span>
          </button>

          <button
            type="button"
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
            className="p-2 rounded-xl text-secondary hover:bg-primary/5 hover:text-primary transition-colors cursor-pointer border border-transparent shrink-0"
            title={theme === "light" ? "Switch to Dark Mode" : "Switch to Light Mode"}
          >
            {theme === "light" ? <Moon className="w-4.5 h-4.5" /> : <Sun className="w-4.5 h-4.5" />}
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 bg-background relative">
        <header className="h-[74px] flex items-end pb-3 px-6 border-b border-outline bg-surface-container-low/85 backdrop-blur-xl drag-region shrink-0 shadow-[0_1px_0_var(--color-outline)]">
          <div className="flex items-center gap-3 min-w-0">
            <h2 className="font-headline font-semibold text-[15px] tracking-wide text-primary truncate">{title}</h2>
          </div>
        </header>

        {bridgeError ? (
          <div className="shrink-0 px-4 py-2.5 text-[13px] leading-snug bg-amber-500/15 border-b border-amber-500/25 text-primary">
            {bridgeError}
          </div>
        ) : null}

        <div className="flex-1 overflow-hidden relative">
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              {/* Primary destinations */}
              <Route path="/" element={<Navigate to="/episodes" replace />} />
              <Route path="/episodes" element={<EpisodesPage projects={projects} onRefresh={fetchProjects} />} />
              <Route path="/episodes/new" element={<NewEpisodePage mode="choose" onRefresh={fetchProjects} />} />
              <Route path="/episodes/new/markdown" element={<NewEpisodePage mode="markdown" onRefresh={fetchProjects} />} />
              <Route path="/studio" element={<Navigate to="/episodes" replace />} />
              <Route path="/studio/:sessionId" element={<StudioPage projects={projects} onRefresh={fetchProjects} />} />
              <Route path="/studio/:sessionId/:scriptId" element={<StudioPage projects={projects} onRefresh={fetchProjects} />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/memory" element={<MemoryPage />} />
              <Route path="/voice-studio" element={<VoiceStudioPage />} />
              <Route path="/voice-studio/:sessionId/:scriptId" element={<VoiceStudioPage />} />
              <Route path="/settings" element={<SettingsPage />} />

              <Route path="/chat" element={<ChatPage onRefresh={fetchProjects} />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  );
}
