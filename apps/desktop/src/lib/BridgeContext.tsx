import { createContext, useContext, useState, ReactNode } from "react";
import { createDesktopBridge } from "./bridgeFactory";
import { DesktopBridge } from "./desktopBridge";

const BridgeContext = createContext<DesktopBridge | null>(null);

export function BridgeProvider({ children }: { children: ReactNode }) {
  const [bridge] = useState(() => createDesktopBridge());

  return (
    <BridgeContext.Provider value={bridge}>
      {children}
    </BridgeContext.Provider>
  );
}

export function useBridge() {
  const context = useContext(BridgeContext);
  if (!context) {
    throw new Error("useBridge must be used within BridgeProvider");
  }
  return context;
}
