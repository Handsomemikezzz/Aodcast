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
