import { RequestState } from "../types";

export function asRequestState(value: unknown): RequestState | null {
  if (typeof value !== "object" || value === null) return null;
  const candidate = value as Partial<RequestState>;
  if (
    typeof candidate.operation !== "string"
    || typeof candidate.phase !== "string"
    || typeof candidate.progress_percent !== "number"
    || typeof candidate.message !== "string"
  ) {
    return null;
  }
  if (candidate.phase !== "running" && candidate.phase !== "succeeded" && candidate.phase !== "failed") {
    return null;
  }
  return candidate as RequestState;
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export function getErrorRequestState(error: unknown): RequestState | null {
  if (typeof error !== "object" || error === null) return null;
  const candidate = error as { requestState?: unknown };
  return asRequestState(candidate.requestState);
}

export function buildRequestState(
  operation: string,
  phase: RequestState["phase"],
  message: string,
  progressPercent?: number,
): RequestState {
  const defaultProgress = phase === "succeeded" ? 100 : 0;
  return {
    operation,
    phase,
    progress_percent: progressPercent ?? defaultProgress,
    message,
  };
}

export function withRequestStateFallback(
  state: RequestState | null | undefined,
  fallback: RequestState,
): RequestState {
  return state ?? fallback;
}
