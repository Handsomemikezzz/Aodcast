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
  if (
    candidate.phase !== "running"
    && candidate.phase !== "cancelling"
    && candidate.phase !== "succeeded"
    && candidate.phase !== "failed"
    && candidate.phase !== "cancelled"
  ) {
    return null;
  }
  if (!Number.isFinite(candidate.progress_percent)) {
    return null;
  }
  if (candidate.progress_percent < 0 || candidate.progress_percent > 100) {
    return null;
  }
  const normalized: RequestState = {
    operation: candidate.operation,
    phase: candidate.phase,
    progress_percent: candidate.progress_percent,
    message: candidate.message,
  };
  if (typeof candidate.run_token === "string" && candidate.run_token.length > 0) {
    normalized.run_token = candidate.run_token;
  }
  return normalized;
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

export function isActiveRequestState(state: RequestState | null | undefined): boolean {
  return state?.phase === "running" || state?.phase === "cancelling";
}

export function isTerminalRequestState(state: RequestState | null | undefined): boolean {
  return state?.phase === "succeeded" || state?.phase === "failed" || state?.phase === "cancelled";
}
