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
