export type AppTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "aodcast-theme";

export function readStoredTheme(): AppTheme {
  if (typeof window === "undefined") return "light";
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "dark" ? "dark" : "light";
}

export function applyTheme(theme: AppTheme): void {
  const root = document.documentElement;
  const isDark = theme === "dark";

  root.classList.toggle("dark-theme", isDark);
  document.body.classList.toggle("dark-theme", isDark);
  root.style.colorScheme = theme;

  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  void syncNativeWindowTheme(theme);
}

async function syncNativeWindowTheme(theme: AppTheme): Promise<void> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return;

  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().setTheme(theme);
  } catch {
    // Native theme sync is best-effort when permissions are unavailable.
  }
}

export function accentRangeBackground(percent: number): string {
  const clamped = Math.max(0, Math.min(100, percent));
  return `linear-gradient(to right, var(--color-accent-amber) 0%, var(--color-accent-amber) ${clamped}%, var(--slider-track) ${clamped}%, var(--slider-track) 100%)`;
}

export function initTheme(): AppTheme {
  const theme = readStoredTheme();
  applyTheme(theme);
  return theme;
}
