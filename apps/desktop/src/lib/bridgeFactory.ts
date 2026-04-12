import { DesktopBridge } from "./desktopBridge";
import { createTauriBridge } from "./tauriBridge";
import { createWebBackendUnavailableBridge } from "./webBackendUnavailableBridge";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function createDesktopBridge(): DesktopBridge {
  if (isTauriRuntime()) {
    return createTauriBridge();
  }
  return createWebBackendUnavailableBridge();
}
