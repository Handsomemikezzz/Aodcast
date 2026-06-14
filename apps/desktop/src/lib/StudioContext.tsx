import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { useBridge } from "./BridgeContext";
import type { SessionProject } from "../types";

type StudioContextValue = {
  project: SessionProject | null;
  setProject: (p: SessionProject | null) => void;
  reload: (sessionId: string, scriptId?: string) => Promise<void>;
};

const StudioContext = createContext<StudioContextValue | null>(null);

export function StudioProvider({
  children,
  initialProject,
}: {
  children: ReactNode;
  initialProject?: SessionProject | null;
}) {
  const bridge = useBridge();
  const [project, setProject] = useState<SessionProject | null>(initialProject ?? null);

  const reload = useCallback(
    async (sessionId: string, scriptId?: string) => {
      if (scriptId) {
        const p = await bridge.showScript(sessionId, scriptId);
        setProject(p);
      } else {
        const p = await bridge.showSession(sessionId);
        setProject(p);
      }
    },
    [bridge],
  );

  return (
    <StudioContext.Provider value={{ project, setProject, reload }}>
      {children}
    </StudioContext.Provider>
  );
}

export function useStudio(): StudioContextValue {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("useStudio must be used inside StudioProvider");
  return ctx;
}
