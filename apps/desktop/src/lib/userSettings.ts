const STORAGE_KEY = "aodcast-user-settings-v1";

export type LlmProviderId = "openai" | "gemini" | "anthropic" | "custom";

export type UserAppSettings = {
  llmProvider: LlmProviderId;
  llmApiKey: string;
  llmBaseUrl: string;
  llmModel: string;
  ttsProvider: string;
  ttsApiKey: string;
};

const defaults: UserAppSettings = {
  llmProvider: "openai",
  llmApiKey: "",
  llmBaseUrl: "",
  llmModel: "",
  ttsProvider: "",
  ttsApiKey: "",
};

export function loadUserSettings(): UserAppSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...defaults };
    const parsed = JSON.parse(raw) as Partial<UserAppSettings>;
    return { ...defaults, ...parsed };
  } catch {
    return { ...defaults };
  }
}

export function saveUserSettings(next: UserAppSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}
