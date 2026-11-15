let runtimeBaseUrl: string = import.meta.env.VITE_AODCAST_RUNTIME_URL ?? "http://127.0.0.1:8765";

/** The desktop shell picks a free runtime port at launch; the bridge reports it here. */
export function setAudioRuntimeBaseUrl(baseUrl: string): void {
  runtimeBaseUrl = baseUrl;
}

export function resolveAudioFileUrl(path: string): string {
  if (!path) return "";
  const url = new URL("/api/v1/artifacts/audio", runtimeBaseUrl);
  url.searchParams.set("path", path);
  return url.toString();
}
