import { convertFileSrc } from "@tauri-apps/api/core";

const DEFAULT_HTTP_RUNTIME_BASE_URL = "http://127.0.0.1:8765";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function resolveAudioFileUrl(path: string): string {
  if (!path) return "";
  if (isTauriRuntime()) {
    try {
      return convertFileSrc(path);
    } catch {
      // Fall through to the HTTP runtime URL used by the browser dev shell.
    }
  }
  const url = new URL("/api/v1/artifacts/audio", DEFAULT_HTTP_RUNTIME_BASE_URL);
  url.searchParams.set("path", path);
  return url.toString();
}
