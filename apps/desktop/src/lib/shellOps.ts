import { invoke } from "@tauri-apps/api/core";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function revealInFinder(path: string): Promise<void> {
  if (!path) return;
  if (!isTauriRuntime()) {
    throw new Error("Reveal in Finder is only available inside the desktop shell.");
  }
  await invoke("reveal_in_finder", { path });
}

export async function pickDirectory(title?: string): Promise<string | null> {
  if (!isTauriRuntime()) {
    throw new Error("Directory picking is only available inside the desktop shell.");
  }
  const result = await invoke<{ path?: string | null }>("pick_directory", { title });
  const path = typeof result?.path === "string" ? result.path.trim() : "";
  return path || null;
}

export async function openExternalUrl(url: string): Promise<void> {
  if (!url) return;
  if (!isTauriRuntime()) {
    const opened = window.open(url, "_blank", "noopener,noreferrer");
    if (!opened) throw new Error("The browser blocked the ChatGPT login window.");
    return;
  }
  await invoke("open_external_url", { url });
}
