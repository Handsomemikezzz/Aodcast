const DEFAULT_HTTP_RUNTIME_BASE_URL = "http://127.0.0.1:8765";

export function resolveAudioFileUrl(path: string): string {
  if (!path) return "";
  const url = new URL("/api/v1/artifacts/audio", DEFAULT_HTTP_RUNTIME_BASE_URL);
  url.searchParams.set("path", path);
  return url.toString();
}
