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

  const pathSegment = location.pathname.split("/").filter(Boolean)[0] ?? "";

  const navItemClass = (active: boolean) =>
    cn(
      "w-full flex items-center gap-2.5 px-2.5 h-9 rounded-lg transition-colors text-[13px] font-medium select-none",
      active
        ? "bg-primary/[0.06] text-primary"
        : "text-secondary hover:bg-primary/[0.04] hover:text-primary",
    );

  const navItems = [
    {
      to: "/episodes",
      label: "Episodes",
      icon: List,
      active: pathSegment === "episodes" || pathSegment === "studio",
    },
    { to: "/voice-studio", label: "Voice", icon: AudioLines, active: pathSegment === "voice-studio" },
    { to: "/models", label: "Models", icon: Package, active: pathSegment === "models" },
    { to: "/memory", label: "Memory", icon: Brain, active: pathSegment === "memory" },
  ];

  return (
    <div className="flex h-screen w-full bg-background text-on-surface overflow-hidden selection:bg-accent-amber/30 font-body mac-scrollbar">
      <aside className="flex w-[60px] lg:w-[200px] flex-shrink-0 flex-col border-r border-outline bg-surface-container-low">
        <div className="h-14 flex items-center px-4 drag-region select-none">
          <div className="flex items-center gap-2 text-primary">
            <Mic className="w-4.5 h-4.5 text-accent-amber" />
            <span className="hidden lg:inline font-headline font-semibold text-[15px]">Aodcast</span>
          </div>
        </div>

        <nav className="px-2.5 space-y-0.5">
          {navItems.map(({ to, label, icon: Icon, active }) => (
            <NavLink key={to} to={to} title={label} className={navItemClass(active)}>
              <Icon className="w-4 h-4 shrink-0" />
              <span className="hidden lg:inline">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="flex-1 min-h-0" aria-hidden />

        <div className="p-2.5 shrink-0 flex flex-col lg:flex-row items-center gap-1">
          <button
            type="button"
            onClick={() => navigate("/settings")}
            className={cn(navItemClass(pathSegment === "settings"), "lg:flex-1")}
            title="Settings"
          >
            <Settings className="w-4 h-4 shrink-0" />
            <span className="hidden lg:inline">Settings</span>
          </button>

          <button
            type="button"
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
            className="h-9 w-9 inline-flex items-center justify-center rounded-lg text-secondary hover:bg-primary/[0.04] hover:text-primary transition-colors shrink-0"
            title={theme === "light" ? "Switch to Dark Mode" : "Switch to Light Mode"}
            aria-label={theme === "light" ? "Switch to Dark Mode" : "Switch to Light Mode"}
          >
            {theme === "light" ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 bg-background relative">
        {bridgeError ? (
          <div className="shrink-0 px-4 py-2.5 text-[13px] leading-snug bg-amber-500/15 border-b border-amber-500/25 text-primary">
            {bridgeError}
          </div>
        ) : null}

        <div className="flex-1 overflow-hidden relative">
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<Navigate to="/episodes" replace />} />
              <Route path="/episodes" element={<EpisodesPage projects={projects} onRefresh={fetchProjects} />} />
              <Route path="/episodes/new" element={<ChatPage onRefresh={fetchProjects} />} />
              <Route path="/episodes/new/markdown" element={<NewEpisodePage onRefresh={fetchProjects} />} />
              <Route path="/studio/:sessionId" element={<StudioPage projects={projects} onRefresh={fetchProjects} />} />
              <Route path="/studio/:sessionId/:scriptId" element={<StudioPage projects={projects} onRefresh={fetchProjects} />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/memory" element={<MemoryPage />} />
              <Route path="/voice-studio" element={<VoiceStudioPage />} />
              <Route path="/voice-studio/:sessionId/:scriptId" element={<VoiceStudioPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  );
}
