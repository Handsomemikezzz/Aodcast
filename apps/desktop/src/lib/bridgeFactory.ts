import { DesktopBridge } from "./desktopBridge";
import { createHttpBridge } from "./httpBridge";

export function createDesktopBridge(): DesktopBridge {
  return createHttpBridge();
}
