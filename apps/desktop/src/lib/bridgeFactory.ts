import { DesktopBridge } from "./desktopBridge";
import { createMockBridge } from "./mockBridge";
import { createTauriBridge } from "./tauriBridge";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function createDesktopBridge(): DesktopBridge {
  if (isTauriRuntime()) {
    return createTauriBridge();
  }
  return createMockBridge();
}
